import requests
import utils.db_utils as db_utils
from decouple import config 

# compares the text responses for adept from DRE using the Phase 1 server
# first, we have to recreate all of the adept sessions for ADEPT DRE text on the Phase 1 server
# then, we have to create the "mini-adms" on the phase 1 server
# finally, we can compare

ADEPT_URL = config("ADEPT_URL")

AD_PROBES = {
    "DryRunEval-IO2-eval": ['Probe 4', 'Probe 8', 'Probe 9', 'Probe 9-B.1', 'Probe 9-A.1', 'Probe 10'],
    "DryRunEval-MJ2-eval": ['Probe 2B-1', 'Probe 2A-1', 'Response 3-B.2-B-gauze-v', 'Response 3-B.2-B-gauze-s', 'Response 3-B.2-A-gauze-v', 'Response 3-B.2-A-gauze-s', 'Probe 5', 'Probe 5-A.1', 'Probe 5-B.1', 'Probe 6', 'Probe 7'],
    "DryRunEval-IO4-eval": ['Probe 6', 'Probe 7', 'Probe 8', 'Probe 10'],
    "DryRunEval-MJ4-eval": ['Probe 1', 'Probe 2 kicker', 'Probe 2 passerby', 'Probe 2-A.1', 'Probe 2-D.1', 'Probe 2-D.1-B.1', 'Probe 3', 'Probe 3-A.1', 'Probe 3-B.1', 'Probe 9', 'Response 10-B', 'Response 10-C', 'Probe 10-A.1'],
    "DryRunEval-IO5-eval": ['Probe 7', 'Probe 8', 'Probe 8-A.1', 'Probe 8-A.1-A.1', 'Probe 9', 'Probe 9-A.1', 'Probe 9-B.1', 'Probe 9-C.1'],
    "DryRunEval-MJ5-eval": ['Probe 1', 'Probe 1-A.1', 'Probe 1-B.1', 'Probe 2', 'Response 2-A.1-B', 'Response 2-B.1-B', 'Response 2-B.1-B-gauze-u', 'Response 2-A.1-B-gauze-sp', 'Probe 2-A.1-A.1', 'Probe 2-B.1-A.1', 'Probe 2-A.1-B.1-A.1', 'Probe 2-B.1-B.1-A.1', 'Probe 3', 'Probe 4']
}

def main(mongoDB, EVAL_NUMBER=4):
    text_scenario_collection = mongoDB['userScenarioResults']
    delegation_collection = mongoDB['surveyResults']
    comparison_collection = mongoDB['humanToADMComparison']
    comparison_collection.delete_many({"ph1_server": True})
    medic_collection = mongoDB['admMedics']
    adm_collection = mongoDB["test"]
    del_adm_runs_collection = mongoDB['delegationADMRuns']
    del_adm_runs_collection.delete_many({"dre_ph1_run": True})
    # remove ph1 session ids for fresh start
    text_scenario_collection.update_many(
        {"evalNumber": EVAL_NUMBER, "ph1SessionId": {"$exists": True}}, {"$set": {"ph1SessionId": None}}
    )

    data_to_use = text_scenario_collection.find(
        {"evalNumber": EVAL_NUMBER}
    )

    # start by creating sessions in phase 1 server for dre data
    sessions_by_pid = {}
    for entry in data_to_use:
        scenario_id = entry.get('scenario_id')
        ph1_id = entry.get('ph1SessionId', None)
        session_id = entry.get('combinedSessionId', entry.get('serverSessionId'))
        data_id = entry.get('_id')
        pid = entry.get('participantID')
        
        new_id = None
        if 'DryRun' in scenario_id and ph1_id is None:
            if pid in sessions_by_pid:
                new_id = sessions_by_pid[pid]['sid']
                sessions_by_pid[pid]['_ids'].append(data_id)
            else:
                adept_sid = requests.post(f'{ADEPT_URL}api/v1/new_session').text.replace('"', '').strip()
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
            db_utils.send_probes(f'{ADEPT_URL}api/v1/response', probes, new_id, scenario_id)

        updates = {}
        if new_id is not None:
            # only applies to ADEPT, ST did not lose data
            updates['ph1SessionId'] = new_id
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
        session_id = entry.get('ph1SessionId', None)
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
                    found_mini_adm = del_adm_runs_collection.find_one({'dre_ph1_run': True, 'target': adm_target, 'evalNumber': EVAL_NUMBER, 'scenario': page_scenario.replace('IO', 'MJ'), 'adm_name': survey['results'][page]['admName']})
                    if found_mini_adm is None:
                        # get new adm session
                        probe_ids = AD_PROBES[page_scenario] # this is where IO/MJ comes into play - choosing the probes
                        probe_responses = []
                        for x in adm['history']:
                            if x['command'] == 'Respond to TA1 Probe':
                                if x['parameters']['choice'] in probe_ids or x['parameters']['probe_id'] in probe_ids:
                                    probe_responses.append(x['parameters'])
                        found_mini_adm = db_utils.mini_adm_run(EVAL_NUMBER, del_adm_runs_collection, probe_responses, adm_target, survey['results'][page]['admName'], True)
                    
                    # get comparison score
                    if 'Moral' in survey['results'][page]['admTarget']:
                        res = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions_population?session_id_1_or_target_id={session_id}&session_id_2_or_target_id={found_mini_adm["session_id"]}&target_pop_id=ADEPT-DryRun-Moral%20judgement-Population-All').json()
                    else:
                        res = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions_population?session_id_1_or_target_id={session_id}&session_id_2_or_target_id={found_mini_adm["session_id"]}&target_pop_id=ADEPT-DryRun-Ingroup%20Bias-Population-All').json()

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
                            'ph1_server': True
                        }
                        send_document_to_mongo(comparison_collection, document)
                    else:
                        print(f'Error getting comparison for scenarios {scenario_id} and {page_scenario} with text session {session_id} and adm session {found_mini_adm["session_id"]}', res)


    print("Human to ADM comparison values added to database.")


def send_document_to_mongo(comparison_collection, document):
    # do not send duplicate documents, make sure if one already exists, we just replace it
    found_docs = comparison_collection.find({'ph1_server': document['ph1_server'], 'pid': document['pid'], 'adm_type': document['adm_type'], 'text_scenario': document['text_scenario'], 'adm_scenario': document['adm_scenario'], 'evalNumber': document['evalNumber'],
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