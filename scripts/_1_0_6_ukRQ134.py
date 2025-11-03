'''
This script will generate the scores needed to populate the RQ134 data for the UK experiment.
Re-run the necessary phase 1 Observed ADMs since they do not appear to be present in the ADEPT production server
Iterate over participant results to generate comparison scores between the participants and their observed ADMs
'''

from decouple import config
from utils.db_utils import send_probes
import requests
ADEPT_URL = config('ADEPT_DRE_URL')
ST_URL = config('ST_URL')
def main(mongo_db):
    survey_results = mongo_db['surveyResults'].find({'results.evalNumber': 12})
    text_scenarios = mongo_db['userScenarioResults']
    comparison_collec = mongo_db['humanToADMComparison']
    adm_delegation_runs = mongo_db['delegationADMRuns']
    target_runs = mongo_db['admTargetRuns']

    target_runs_query = {
        'evalNumber': 5,
        'scenario': 'vol-ph1-eval-3',
        'adm_name': {'$in': ['TAD-aligned', 'TAD-severity-baseline']}
    }

    target_runs_docs = target_runs.find(target_runs_query)


    q = {
        'evalNumber': 5, 
        'scenario': 'DryRunEval-MJ2-eval', 
        'ph1_in_dre_server_run': {'$exists': False},
        'adm_name': {'$in': ['ALIGN-ADM-OutlinesBaseline', 'ALIGN-ADM-ComparativeRegression-ICL-Template']}
    }
    docs = adm_delegation_runs.find(q)
    
    # clean collection of duplicates
    seen = {}
    duplicates = []
    for doc in docs:
        kdma_value = doc.get('kdmas', [{}])[0].get('value') if doc.get('kdmas') else None
        key = (doc.get('target'), doc.get('scenario'), doc.get('adm_name'), kdma_value)
        if key in seen:
            duplicates.append(doc['_id'])
        else:
            seen[key] = doc['_id']
    
    if duplicates:
        adm_delegation_runs.delete_many({'_id': {'$in': duplicates}})
        print(f"Deleted {len(duplicates)} duplicates")

    # re run observed adept adm runs to be used for comparison scores
    docs = adm_delegation_runs.find(q)
    for doc in docs:
        sid = requests.post(f"{ADEPT_URL}api/v1/new_session").text.replace('"', "").strip()
        probes = [
            {
                "probe": {
                    "choice": x['choice'],
                    "probe_id": x['probe_id']
                }
            }
            for x in doc['probes']
        ]
        send_probes(f"{ADEPT_URL}api/v1/response", probes, sid, doc['scenario'])
        kdma = requests.get(f"{ADEPT_URL}api/v1/computed_kdma_profile?session_id={sid}").json()
        
        # update existing doc so we can use the session id for comparisons
        adm_delegation_runs.update_one(
            {'_id': doc['_id']},
            {'$set': {
                'kdmas': kdma,
                'session_id': sid
            }}
        )

    # re run st adms to be used in scoring 
    for doc in target_runs_docs:
        sid = requests.post(f"{ST_URL}api/v1/new_session").text.replace('"', "").strip()
        probe_responses = []
        for x in doc['history']:
            if x['command'] == 'Respond to TA1 Probe':
                parameters = x['parameters']
                probe_response = {
                    "probe": {
                        "choice": parameters['choice'],
                        "probe_id": parameters['probe_id']
                    }
                }
                probe_responses.append(probe_response)
        send_probes(f"{ST_URL}api/v1/response", probe_responses, sid, 'vol-ph1-eval-3')
        kdma = requests.get(f"{ADEPT_URL}api/v1/computed_kdma_profile?session_id={sid}").json()

    for survey in survey_results:
        results = survey.get('results', {})
        pid = results.get('pid')
    
        for page_key, page_data in results.items():
            if 'vs' in page_key and isinstance(page_data, dict):
                scenario_index = page_data.get('scenarioIndex')
                baseline_target = page_data.get('baselineTarget')
                aligned_target = page_data.get('alignedTarget')
                misaligned_target = page_data.get('misalignedTarget')

                if scenario_index and baseline_target and aligned_target and misaligned_target:
                    page_identifiers = [p.strip() for p in page_key.split(' vs ')]
                
                    if len(page_identifiers) == 3:
                        # Update the three previous pages with admAlignment and admTarget
                        alignment_configs = [
                            (page_identifiers[0], 'baseline', baseline_target),
                            (page_identifiers[1], 'aligned', aligned_target),
                            (page_identifiers[2], 'misaligned', misaligned_target)
                        ]
                        
                        for page_id, alignment_type, target in alignment_configs:
                            mongo_db['surveyResults'].update_one(
                                {
                                    '_id': survey['_id'],
                                    f'results.{page_id}': {'$exists': True}
                                },
                                {
                                    '$set': {
                                        f'results.{page_id}.admAlignment': alignment_type,
                                        f'results.{page_id}.admTarget': target
                                    }
                                }
                            )
                    
                    if 'vol' in baseline_target:
                        continue
                    
                    filt = 'Ingroup%20Bias' if 'Bias' in baseline_target else 'Moral%20judgement'
                    
                    # Find all three ADM runs
                    adm_configs = [
                        ('baseline', baseline_target, 'ALIGN-ADM-OutlinesBaseline'),
                        ('aligned', aligned_target, 'ALIGN-ADM-ComparativeRegression-ICL-Template'),
                        ('misaligned', misaligned_target, 'ALIGN-ADM-ComparativeRegression-ICL-Template')
                    ]
                    
                    adms = {}
                    for adm_type, target, adm_name in adm_configs:
                        adm = adm_delegation_runs.find_one({
                            'scenario': 'DryRunEval-MJ2-eval',
                            'target': target,
                            'evalNumber': 5,
                            'ph1_in_dre_server_run': {'$exists': False},
                            'adm_name': adm_name
                        })
                        if not adm:
                            print(f"No {adm_type} match for {page_key}, target: {target}")
                            break
                        adms[adm_type] = adm
                    
                    if len(adms) != 3:
                        continue
                    
                    # Find participant text scenario
                    scenario_pattern = 'IO' if filt == 'Ingroup%20Bias' else 'MJ'
                    participant_res = text_scenarios.find_one({
                        'participantID': pid,
                        'scenario_id': {'$regex': scenario_pattern}
                    })
                    
                    if not participant_res:
                        print(f"No participant text scenario found for pid: {pid}, pattern: {scenario_pattern}")
                        continue

                    participant_sid = participant_res['combinedSessionId']
                    
                    # Create comparison documents
                    comparison_docs = []
                    for adm_type, adm in adms.items():
                        comp = requests.get(
                            f'{ADEPT_URL}api/v1/alignment/compare_sessions?'
                            f'session_id_1={adm["session_id"]}&session_id_2={participant_sid}&kdma_filter={filt}'
                        ).json()
                        
                        comparison_docs.append({
                            'evalNumber': 12,
                            'pid': pid,
                            'adm_type': adm_type,
                            'adm_alignment_target': adm['target'],
                            'distance_based_score': comp['score'],
                            'adm_author': 'kitware',
                            'adm_scenario': adm['scenario'],
                            'text_session_id': participant_sid,
                            'adm_session_id': adm['session_id'],
                            'text_scenario': participant_res['scenario_id'],
                        })
                    
                    comparison_collec.insert_many(comparison_docs)