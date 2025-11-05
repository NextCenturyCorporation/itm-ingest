"""
This script will generate the scores needed to populate the RQ134 data for the UK experiment.
Re-run the necessary phase 1 Observed ADMs since they do not appear to be present in the ADEPT production server
Iterate over participant results to generate comparison scores between the participants and their observed ADMs
"""

from decouple import config
from utils.db_utils import send_probes
from utils.soartech_utils import get_all_new_alignments
from scripts._0_9_7_fix_test_log import main as fix_log
import requests

ADEPT_URL = config("ADEPT_PH1_URL")
ST_URL = config("ST_URL")


def main(mongo_db):
    survey_results = mongo_db["surveyResults"].find({"results.evalNumber": 12})
    text_scenarios = mongo_db["userScenarioResults"]
    comparison_collec = mongo_db["humanToADMComparison"]
    adm_delegation_runs = mongo_db["delegationADMRuns"]
    target_runs = mongo_db["admTargetRuns"]
    sim_results = mongo_db["humanSimulator"]

    # pids where text scenarios do no match survey
    special_case_pids = {
        "202510153": "202510155",
        "202510152": "202510131",
        "202510127": "202510129",
    }

    for key, value in special_case_pids.items():
        # fix participant log collection to have pid not marked as test
        fix_log(mongo_db, value)
        # delete the text scenarios that were NOT from the participant, these were from Jennifer
        text_scenarios.delete_many({"participantID": value})
        # update text scenario pids from participants to match survey the took
        text_scenarios.update_many(
            {"participantID": key}, {"$set": {"participantID": value}}
        )

        vol_scenario = text_scenarios.find_one({
            "participantID": value,
            "scenario_id": {"$regex": "vol"}
        })

        # run st scenario through server (2/3 have an unscored doc)
        if vol_scenario:
            st_sid = requests.post(f"{ST_URL}api/v1/new_session?user_id=default_user").text.replace('"', "").strip()
            probes = []
            for k in vol_scenario:
                if k.startswith('id-') and isinstance(vol_scenario[k], dict):
                    questions = vol_scenario[k].get('questions', {})
                    probe_key = f"probe {k}"
                    
                    if probe_key in questions:
                        probe_data = questions[probe_key]
                        response = probe_data.get('response', '').replace('.', '')
                        mapping = probe_data.get('question_mapping', {})
                        
                        if response in mapping:
                            probes.append({
                                'probe': {
                                    'choice': mapping[response]['choice'],
                                    'probe_id': mapping[response]['probe_id']
                                }
                            })
            send_probes(f"{ST_URL}api/v1/response", probes, st_sid, 'vol-ph1-eval-2')
            mostLeast = requests.get(f"{ST_URL}api/v1/get_ordered_alignment?session_id={st_sid}&kdma_id=PerceivedQuantityOfLivesSaved").json()
            kdma = requests.get(f"{ST_URL}api/v1/api/v1/computed_kdma_profile?session_id={st_sid}").json()

            text_scenarios.update_one(
                {"_id": vol_scenario["_id"]},
                {"$set": {
                    "serverSessionId": st_sid,
                    "mostLeastAligned": mostLeast,
                    "kdmas": kdma
                }}
            )

    st_adm_session_mapping = {}

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
        sid = requests.post(f"{ST_URL}api/v1/new_session?user_id=default_user").text.replace('"', "").strip()
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
        
        st_adm_session_mapping[(doc['adm_name'], doc['alignment_target'])] = {
            'new_session_id': sid,
            'probe_responses': probe_responses
        }

        target_runs.update_one(
            {'_id': doc['_id']},
            {'$set': {'session_id': sid}}
        )

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
                        # three previous pages need admAlignment and admTarget
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
        

        survey = mongo_db['surveyResults'].find_one({'_id': survey['_id']})
        results = survey.get('results', {})
        
        participant_vol_res = text_scenarios.find_one({
            'participantID': pid,
            'scenario_id': {'$regex': 'vol-ph1-eval'}
        })
        
        if participant_vol_res:
            text_probes = []
            for k in participant_vol_res:
                if isinstance(participant_vol_res[k], dict) and 'questions' in participant_vol_res[k]:
                    if 'probe ' + k in participant_vol_res[k]['questions'] and 'response' in participant_vol_res[k]['questions']['probe ' + k]:
                        if 'question_mapping' in participant_vol_res[k]['questions']['probe ' + k]:
                            response = participant_vol_res[k]['questions']['probe ' + k]['response'].replace('.', '')
                            mapping = participant_vol_res[k]['questions']['probe ' + k]['question_mapping']
                            if response in mapping:
                                text_probes.append({'probe': {'choice': mapping[response]['choice'], 
                                                             'probe_id': mapping[response]['probe_id']}})
            
            for page_key, page_data in results.items():
                if isinstance(page_data, dict) and page_data.get('scenarioIndex') and 'vol' in page_data.get('scenarioIndex', ''):
                    if page_data.get('pageType') != 'comparison' and 'vs' not in page_key:
                        adm_name = page_data.get('admName')
                        adm_target = page_data.get('admTarget')
                        adm_scenario = page_data.get('scenarioIndex')
                        
                        mapping_key = (adm_name, adm_target)
                        if mapping_key in st_adm_session_mapping:
                            adm_info = st_adm_session_mapping[mapping_key]
                            
                            # Calculate calibration scores
                            calibration_scores = get_all_new_alignments(
                                text_probes,
                                participant_vol_res['scenario_id'],
                                adm_info['probe_responses'],
                                'vol-ph1-eval-3'
                            )
                            
                            # Update existing comparison documents with calibration scores
                            comparison_collec.update_many(
                                {
                                    'evalNumber': 12,
                                    'pid': pid,
                                    'text_scenario': participant_vol_res['scenario_id'],
                                    'adm_scenario': adm_scenario,
                                    'adm_alignment_target': adm_target
                                },
                                {
                                    '$set': {
                                        'calibration_scores': calibration_scores,
                                        'adm_session_id': adm_info['new_session_id'],
                                        'text_session_id': participant_vol_res['serverSessionId'],
                                        'adm_type': page_data['admAlignment']
                                    }
                                },
                                upsert=True
                            )
        
        for page_key, page_data in results.items():
            if 'vs' in page_key and isinstance(page_data, dict):
                scenario_index = page_data.get('scenarioIndex')
                baseline_target = page_data.get('baselineTarget')
                aligned_target = page_data.get('alignedTarget')
                misaligned_target = page_data.get('misalignedTarget')

                if scenario_index and baseline_target and aligned_target and misaligned_target:
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
                            break
                        adms[adm_type] = adm
                    
                    if len(adms) != 3:
                        continue
                    
                    
                    scenario_pattern = 'IO' if filt == 'Ingroup%20Bias' else 'MJ'
                    participant_res = text_scenarios.find_one({
                        'participantID': pid,
                        'scenario_id': {'$regex': scenario_pattern}
                    })
                    
                    if not participant_res:
                        print(f"No participant text scenario found for pid: {pid}, pattern: {scenario_pattern}")
                        continue

                    participant_sid = participant_res['combinedSessionId']
                    
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
                    
                    sim_doc = sim_results.find_one({
                        'pid': pid,
                        'evalNumber': 12,
                        'scenario_id': "DryRunEval-MJ4-eval"
                    })
                    
                    if sim_doc:
                        sim_sid = sim_doc['data']['alignment']['sid']
                        
                        sim_comparison_docs = []
                        for adm_type, adm in adms.items():
                            sim_comp = requests.get(
                                f'{ADEPT_URL}api/v1/alignment/compare_sessions?'
                                f'session_id_1={adm["session_id"]}&session_id_2={sim_sid}&kdma_filter={filt}'
                            ).json()

                            score = sim_comp.get('score') if isinstance(sim_comp, dict) else None
                            
                            sim_comparison_docs.append({
                                'evalNumber': 12,
                                'pid': pid,
                                'adm_type': adm_type,
                                'adm_alignment_target': adm['target'],
                                'distance_based_score': score,
                                'adm_author': 'kitware',
                                'adm_scenario': adm['scenario'],
                                'sim_session_id': sim_sid,
                                'adm_session_id': adm['session_id'],
                                'sim_scenario': sim_doc['scenario_id'],
                                'source': 'humanSimulator'
                            })
                        
                        comparison_collec.insert_many(sim_comparison_docs)
                    else:
                        print(f"No humanSimulator document found for pid: {pid}")
                        
