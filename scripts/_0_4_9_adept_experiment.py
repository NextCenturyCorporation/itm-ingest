from decouple import config 
import requests, csv
from scripts._0_4_4_adept_human_adm_compare_DRE_PH1_Server import main as dre_to_ph1
from adept_repop_ph1 import main as repop_ph1, SCENARIO_MAP
import utils.db_utils as db_utils
from scripts._0_2_8_human_to_adm_comparison import main as compare_probes

PH1_URL = config("ADEPT_URL")
DRE_URL = config("ADEPT_DRE_URL")

def main(db):
    refill_PH1_sessions = 'http:' in PH1_URL # if ph1 server is local, refill sessions

    comparisons = db['humanToADMComparison']

    comparison_file = open('ph1_server_old_comparison_vs_new.csv', 'w', encoding='utf-8')
    comparison_writer = csv.writer(comparison_file)
    comparison_writer.writerow(['PID', 'Eval_Number', 'Text_Session', 'ADM_Session', 'Text_Scenario', 'ADM_Scenario', 'ADM_Author', 'ADM_Type', 'ADM_Alignment_Target', 'Old_Endpoint_Score', 'New_Endpoint_Score'])

    # all PH1 sessions should be in PH1 server
    if refill_PH1_sessions:
        print("Repopulating Phase 1 server with Phase 1 data")
        repop_ph1(db)
        compare_probes(db, 5, False, True)
    # Run old comparison endpoint on PH1 sessions in PH1 server
    ph1_comparisons = comparisons.find({'evalNumber': 5, 'dre_server': {'$exists': False}, 'adm_scenario': {'$exists': True}})
    for comp in ph1_comparisons:
        res = requests.get(f'{PH1_URL}api/v1/alignment/compare_sessions?session_id_1={comp['text_session_id']}&session_id_2={comp['adm_session_id']}').json()
        comparison_writer.writerow([comp['pid'], 5, comp['text_session_id'], comp['adm_session_id'], comp['text_scenario'], comp['adm_scenario'], comp['adm_author'], comp['adm_type'], comp['adm_alignment_target'], comp['score'], res['score']])

    # all DRE sessions should be in PH1 server
    if refill_PH1_sessions:
        print("Repopulating Phase 1 server with DRE data")
        dre_to_ph1(db)
    # Run old comparison endpoint on DRE sessions in PH1 server
    dre_comparisons = comparisons.find({'evalNumber': 4, 'ph1_server': True, 'adm_scenario': {'$exists': True}})
    for comp in dre_comparisons:
        res = requests.get(f'{PH1_URL}api/v1/alignment/compare_sessions?session_id_1={comp['text_session_id']}&session_id_2={comp['adm_session_id']}').json()
        comparison_writer.writerow([comp['pid'], 4, comp['text_session_id'], comp['adm_session_id'], comp['text_scenario'], comp['adm_scenario'], comp['adm_author'], comp['adm_type'], comp['adm_alignment_target'], comp['score'], res['score']])
    comparison_file.close()


    dre_server_with_ph1_data = open('dre_server_ph1_data.csv', 'w', encoding='utf-8')
    dre_ph1_writer = csv.writer(dre_server_with_ph1_data)
    dre_ph1_writer.writerow(['PID', 'Attribute', 'Scenario', 'TA2_Name', 'ADM_Type', 'ADM_Aligned_Status (Baseline/Misaligned/Aligned)', 'Target', 'PH1_ADM|Target', 'DRE_ADM|Target', 
                             'PH1_Delegator|Target', 'DRE_Delegator|Target', 'PH1_Delegator|ObservedADM', 'DRE_Delegator|ObservedADM', 'PH1_ADM_loading', 'DRE_ADM_loading'])

    surveys = db['surveyResults']
    ph1_surveys = surveys.find({'results.evalNumber': 5})
    plog = db['participantLog']

    # PH1 sessions are not in DRE server!
    # send all PH1 sessions to DRE server (my local DRE server was populated with no redacted files, and just one set of ph1 unredacted files)
    print("Populating DRE server with Phase 1 data")
    send_PH1_to_DRE(db)

    for res in ph1_surveys:
        pid = res.get('results', {}).get('Participant ID Page', {}).get('questions', {}).get('Participant ID', {}).get('response')
        if not pid:
            continue
        try:
            in_plog = plog.count_documents({'ParticipantID': int(pid)})
            if in_plog == 0:
                continue
        except:
            continue
        for pageName in res['results']:
            if 'Medic' in pageName and ' vs ' not in pageName:
                page = res['results'][pageName]
                target = page['admTarget']
                if 'ADEPT' not in target:
                    continue

                # find comparison values from ph1 server and dre server from database
                ph1_comparison = comparisons.find_one({'dre_server': {'$exists': False}, 'evalNumber': 5, 'adm_type': page['admAlignment'], 'pid': pid, 'adm_author': page['admAuthor'], 'adm_scenario': page['scenarioIndex']})
                dre_comparison = comparisons.find_one({'dre_server': True, 'evalNumber': 5, 'adm_type': page['admAlignment'], 'pid': pid, 'adm_author': page['admAuthor'], 'adm_scenario': page['scenarioIndex']})
                if not ph1_comparison:
                    print('could not find ph1_comparison with parameters', {'dre_server': {'$exists': False}, 'evalNumber': 5, 'adm_type': page['admAlignment'], 'pid': pid, 'adm_author': page['admAuthor'], 'adm_scenario': page['scenarioIndex']})
                    continue
                if not dre_comparison:
                    print('could not find dre_comparison with parameters', {'dre_server': True, 'evalNumber': 5, 'adm_type': page['admAlignment'], 'pid': pid, 'adm_author': page['admAuthor'], 'adm_scenario': page['scenarioIndex']})
                    continue

                # get ph1 server text alignment
                ph1_txt_id = ph1_comparison['text_session_id']
                if 'Moral' in target:
                    targets = requests.get(f'{PH1_URL}api/v1/get_ordered_alignment?session_id={ph1_txt_id}&population=false&kdma_id=Moral%20judgement').json()
                else:
                    targets = requests.get(f'{PH1_URL}api/v1/get_ordered_alignment?session_id={ph1_txt_id}&population=false&kdma_id=Ingroup%20Bias').json()
                ph1_txt_alignment = None
                for t in targets:
                    if target in t:
                        ph1_txt_alignment = t[target]
                
                # get dre server text alignment
                dre_txt_id = dre_comparison['text_session_id']
                dre_txt_alignment = requests.get(f'{DRE_URL}api/v1/alignment/session?session_id={dre_txt_id}&target_id={target}&population=false').json()

                # find ph1 server adm alignment
                medic_collection = db['admMedics']
                adm_collection = db["test"]
                adm = db_utils.find_adm_from_medic(5, medic_collection, adm_collection, pageName, page['scenarioIndex'].replace('IO', 'MJ'), res)
                if adm is None:
                    print('Could not find adm')
                    continue
                ph1_adm_score = adm['history'][-1]['response']['score']

                # send all adm probes to the dre server
                # get new adm session
                probe_responses = []
                for x in adm['history']:
                    if x['command'] == 'Respond to TA1 Probe':
                        probe_responses.append(x['parameters'])
                adept_sid = send_adm_probes(DRE_URL, probe_responses)

                # with that new session, get the dre server adm alignment score
                dre_adm_alignment = requests.get(f'{DRE_URL}api/v1/alignment/session?session_id={adept_sid}&target_id={target}&population=false').json()

                # grab adm-choosing process for phase 1 server
                ph1_process = 'normal' if page['admAlignment'] == 'baseline' else ('normal' if page.get('admChoiceProcess') in ['least aligned', 'most aligned'] else 'exemption')

                # calculate adm-choosing process for dre server
                targets = ['ADEPT-DryRun-Moral judgement-0.2',  'ADEPT-DryRun-Moral judgement-0.3',  'ADEPT-DryRun-Moral judgement-0.4', 'ADEPT-DryRun-Moral judgement-0.5',  
                           'ADEPT-DryRun-Moral judgement-0.6',  'ADEPT-DryRun-Moral judgement-0.7',  'ADEPT-DryRun-Moral judgement-0.8'] if 'MJ' in target else ['ADEPT-DryRun-Ingroup Bias-0.2',
                            'ADEPT-DryRun-Ingroup Bias-0.3', 'ADEPT-DryRun-Ingroup Bias-0.4', 'ADEPT-DryRun-Ingroup Bias-0.5', 'ADEPT-DryRun-Ingroup Bias-0.6', 'ADEPT-DryRun-Ingroup Bias-0.7', 'ADEPT-DryRun-Ingroup Bias-0.8']
                alignments = {}
                for t in targets:
                    alignments[t] = requests.get(f'{DRE_URL}api/v1/alignment/session?session_id={dre_txt_id}&target_id={t}&population=false').json().get('score')
                max_target = max(alignments, key=alignments.get)
                min_target = min(alignments, key=alignments.get)
                dre_process = 'normal'
                if (page['admAlignment'] == 'aligned' and target != max_target) or (page['admAlignment'] == 'misaligned' and target != min_target):
                    dre_process = 'exemption'

                # add data to csv
                dre_ph1_writer.writerow([pid, 'IO' if 'IO' in page['scenarioIndex'] else 'MJ', page['scenarioIndex'].replace('IO', 'MJ'), page['admAuthor'], 
                                         'baseline' if page['admAlignment'] == 'baseline' else 'aligned', page['admAlignment'], target, ph1_adm_score, dre_adm_alignment.get('score', None), 
                                         ph1_txt_alignment, dre_txt_alignment.get('score', None), ph1_comparison.get('score', None), dre_comparison.get('score', None), ph1_process, dre_process])
        
    dre_server_with_ph1_data.close()


def send_adm_probes(server, probes):
    # get a new session id for adms
    adept_sid = requests.post(f'{server}api/v1/new_session').text.replace('"', "").strip()
    # send probes to server 
    for x in probes:
        requests.post(f'{server}api/v1/response', json={
            "response": {
                "choice": x['choice'],
                "justification": x["justification"],
                "probe_id": x['probe_id'],
                "scenario_id": x['scenario_id'],
            },
            "session_id": adept_sid
        })

    return adept_sid

AD_PROBES = {
    "DryRunEval-IO2-eval": ['Probe 4', 'Probe 8', 'Probe 9', 'Probe 9-B.1', 'Probe 9-A.1', 'Probe 10'],
    "DryRunEval-MJ2-eval": ['Probe 2B-1', 'Probe 2A-1', 'Response 3-B.2-B-gauze-v', 'Response 3-B.2-B-gauze-s', 'Response 3-B.2-A-gauze-v', 'Response 3-B.2-A-gauze-s', 'Probe 5', 'Probe 5-A.1', 'Probe 5-B.1', 'Probe 6', 'Probe 7'],
    "DryRunEval-IO4-eval": ['Probe 6', 'Probe 7', 'Probe 8', 'Probe 10'],
    "DryRunEval-MJ4-eval": ['Probe 1', 'Probe 2 kicker', 'Probe 2 passerby', 'Probe 2-A.1', 'Probe 2-D.1', 'Probe 2-D.1-B.1', 'Probe 3', 'Probe 3-A.1', 'Probe 3-B.1', 'Probe 9', 'Response 10-B', 'Response 10-C', 'Probe 10-A.1'],
    "DryRunEval-IO5-eval": ['Probe 7', 'Probe 8', 'Probe 8-A.1', 'Probe 8-A.1-A.1', 'Probe 9', 'Probe 9-A.1', 'Probe 9-B.1', 'Probe 9-C.1'],
    "DryRunEval-MJ5-eval": ['Probe 1', 'Probe 1-A.1', 'Probe 1-B.1', 'Probe 2', 'Response 2-A.1-B', 'Response 2-B.1-B', 'Response 2-B.1-B-gauze-u', 'Response 2-A.1-B-gauze-sp', 'Probe 2-A.1-A.1', 'Probe 2-B.1-A.1', 'Probe 2-A.1-B.1-A.1', 'Probe 2-B.1-B.1-A.1', 'Probe 3', 'Probe 4']
}

def send_PH1_to_DRE(mongoDB, EVAL_NUMBER=5):
    text_scenario_collection = mongoDB['userScenarioResults']
    delegation_collection = mongoDB['surveyResults']
    comparison_collection = mongoDB['humanToADMComparison']
    comparison_collection.delete_many({"dre_server": True})
    medic_collection = mongoDB['admMedics']
    adm_collection = mongoDB["test"]
    del_adm_runs_collection = mongoDB['delegationADMRuns']
    del_adm_runs_collection.delete_many({"ph1_in_dre_server_run": True})
    # remove ph1 session ids for fresh start
    text_scenario_collection.update_many(
        {"evalNumber": EVAL_NUMBER, "dreSessionId": {"$exists": True}}, {"$set": {"dreSessionId": None}}
    )

    data_to_use = text_scenario_collection.find(
        {"evalNumber": EVAL_NUMBER}
    )

    # start by creating sessions in dre server for phase 1 data
    sessions_by_pid = {}
    for entry in data_to_use:
        scenario_id = entry.get('scenario_id')
        dre_id = entry.get('dreSessionId', None)
        session_id = entry.get('combinedSessionId', entry.get('serverSessionId'))
        data_id = entry.get('_id')
        pid = entry.get('participantID')
        
        new_id = None
        if 'adept' in scenario_id and dre_id is None:
            scenario_id = SCENARIO_MAP[scenario_id]
            if pid in sessions_by_pid:
                new_id = sessions_by_pid[pid]['sid']
                sessions_by_pid[pid]['_ids'].append(data_id)
            else:
                adept_sid = requests.post(f'{DRE_URL}api/v1/new_session').text.replace('"', '').strip()
                sessions_by_pid[pid] = {'sid': adept_sid, '_ids': [data_id]}
                new_id = adept_sid
            # collect probes
            probes = []
            for k in entry:
                if isinstance(entry[k], dict) and 'questions' in entry[k]:
                    for valid_key in [f'probe {k}', f'probe {k}_conditional']:
                        probe_data = entry[k]['questions'].get(valid_key, {})
                        if 'response' in probe_data and 'question_mapping' in probe_data:
                            response = probe_data['response'].replace('.', '')
                            mapping = probe_data['question_mapping']
                            if response in mapping:
                                if isinstance(mapping[response]['choice'], list):
                                    for c in mapping[response]['choice']:
                                        probes.append({'probe': {'choice': c, 'probe_id': mapping[response]['probe_id']}})
                                else:
                                    probes.append({'probe': {'choice': mapping[response]['choice'], 'probe_id': mapping[response]['probe_id']}})
                            else:
                                print('could not find response in mapping!', response, list(mapping.keys()))
            send_probes(f'{DRE_URL}api/v1/response', probes, new_id, scenario_id)

        updates = {}
        if new_id is not None:
            # only applies to ADEPT, ST did not lose data
            updates['dreSessionId'] = new_id
            # if new_id exists, we need to update the session id for all adept that this participant completed (we never know when it will be the last one)
            for data_id in sessions_by_pid[pid]['_ids']:
                text_scenario_collection.update_one({'_id': data_id}, {'$set': updates})        


    # go through text scenarios again, this time finding comparison values
    text_scenario_collection = mongoDB['userScenarioResults']
    data_to_use = text_scenario_collection.find(
        {"evalNumber": EVAL_NUMBER}
    )
    for entry in data_to_use:
        scenario_id = entry.get('scenario_id')
        if 'MJ1' in scenario_id or 'IO1' in scenario_id:
            # ignore test scenarios from adept
            continue
        session_id = entry.get('dreSessionId', None)
        pid = entry.get('participantID')
        survey = list(delegation_collection.find({"results.Participant ID Page.questions.Participant ID.response": pid}))
        if len(survey) == 0:
            print(f"No survey found for {pid}")
            continue
        survey = survey[-1] # get last survey entry for this pid
        # get human to adm comparisons from delegation survey adms
        for page in survey['results']:
            if 'Medic' in page and ' vs ' not in page:
                page_scenario = survey['results'][page]['scenarioIndex']
                # ignore ST 
                if ('qol' in scenario_id and 'qol' in page_scenario) or ('vol' in scenario_id and 'vol' in page_scenario):
                    continue
                elif (('DryRunEval' in scenario_id or 'adept' in scenario_id) and ('DryRunEval' in page_scenario or 'adept' in page_scenario)):
                    adm = db_utils.find_adm_from_medic(EVAL_NUMBER, medic_collection, adm_collection, page, page_scenario.replace('IO', 'MJ'), survey)
                    if adm is None:
                        continue
                    adm_target = adm['history'][len(adm['history'])-1]['parameters']['target_id']
                    found_mini_adm = del_adm_runs_collection.find_one({'ph1_in_dre_server_run': True, 'target': adm_target, 'evalNumber': EVAL_NUMBER, 'scenario': page_scenario.replace('IO', 'MJ'), 'adm_name': survey['results'][page]['admName']})
                    if found_mini_adm is None:
                        # get new adm session
                        probe_ids = AD_PROBES[page_scenario] # this is where IO/MJ comes into play - choosing the probes
                        probe_responses = []
                        for x in adm['history']:
                            if x['command'] == 'Respond to TA1 Probe':
                                if x['parameters']['choice'] in probe_ids or x['parameters']['probe_id'] in probe_ids:
                                    probe_responses.append(x['parameters'])
                        found_mini_adm = db_utils.mini_adm_run(EVAL_NUMBER, del_adm_runs_collection, probe_responses, adm_target, survey['results'][page]['admName'], False, True)
                    # get comparison score
                    res = requests.get(f'{DRE_URL}api/v1/alignment/compare_sessions?session_id_1={session_id}&session_id_2={found_mini_adm["session_id"]}').json()
                    
                    # send document to mongo
                    if res is not None and 'score' in res:
                        document = {
                            'pid': pid,
                            'adm_type': survey['results'][page]['admAlignment'],
                            'score': res['score'],
                            'text_scenario': scenario_id,
                            'text_session_id': session_id.replace('"', "").strip(),
                            'adm_scenario': page_scenario,
                            'adm_session_id': found_mini_adm["session_id"],
                            'adm_author': survey['results'][page]['admAuthor'],
                            'adm_alignment_target': survey['results'][page]['admTarget'],
                            'evalNumber': EVAL_NUMBER,
                            'dre_server': True
                        }
                        send_document_to_mongo(comparison_collection, document)
                    else:
                        print(f'Error getting comparison for scenarios {scenario_id} and {page_scenario} with text session {session_id} and adm session {found_mini_adm["session_id"]}', res)


    print("Human to ADM comparison values added to database.")


def send_probes(probe_url, probes, sid, scenario):
    '''
    Sends the probes to the server
    '''
    for x in probes:
        if 'probe' in x and 'choice' in x['probe']:
            requests.post(probe_url, json={
                "response": {
                    "choice": x['probe']['choice'],
                    "justification": "justification",
                    "probe_id": x['probe']['probe_id'],
                    "scenario_id": scenario,
                },
                "session_id": sid
            })
        

def send_document_to_mongo(comparison_collection, document):
    # do not send duplicate documents, make sure if one already exists, we just replace it
    found_docs = comparison_collection.find({'dre_server': document['dre_server'], 'pid': document['pid'], 'adm_type': document['adm_type'], 'text_scenario': document['text_scenario'], 'adm_scenario': document['adm_scenario'], 'evalNumber': document['evalNumber'],
                                            'text_session_id': document['text_session_id'], 'adm_session_id': document['adm_session_id'], 'adm_author': document['adm_author'], 'adm_alignment_target': document['adm_alignment_target']})
    doc_found = False
    obj_id = ''
    for doc in found_docs:
        doc_found = True
        obj_id = doc['_id']
        break
    if doc_found:
        comparison_collection.update_one({'_id': obj_id}, {'$set': document})
    else:
        comparison_collection.insert_one(document)



if __name__ == '__main__':
    from pymongo import MongoClient
    MONGO_URL = config('MONGO_URL')
    client = MongoClient(MONGO_URL)
    mongoDB = client['dashboard']
    main(mongoDB)