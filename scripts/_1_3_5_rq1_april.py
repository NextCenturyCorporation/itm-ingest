'''
Runs oracle adms through TA1 server so session id's are available for rq1 comparisons
'''
import requests
from decouple import config
import utils.db_utils as db_utils
ADEPT_URL = config('ADEPT_URL')

def main(mongo_db):
    run_obs_oracles(mongo_db)
    gen_comp(mongo_db, EVAL_NUMBER=16)

def run_obs_oracles(mongo_db):
    medics = mongo_db['admMedics']
    observed_oracles = list(medics.find({'evalNumber': 16, 'admName': 'Oracle'}))

    for oracle in observed_oracles:
        responses = oracle['elements'][0]['rows']
        scenario_id = responses[0]['scenario_id']

        sid = requests.post(f"{ADEPT_URL}api/v1/new_session").text.replace('"', '').strip()

        probes = [
            {
                'probe': {
                    'choice': response['choice_id'],
                    'probe_id': response['probe_id'],
                }
            }
            for response in responses
        ]

        db_utils.send_probes(f"{ADEPT_URL}api/v1/response", probes, sid, scenario_id)

        kdmas = requests.get(
            f"{ADEPT_URL}api/v1/computed_kdma_profile?session_id={sid}"
        ).json()

        medics.update_one(
            {'_id': oracle['_id']},
            {
                '$set': {
                    'admSessionId': sid,
                    'kdmas': kdmas,
                }
            }
        )

        print(f"Processed {oracle['name']} - {scenario_id} -> session {sid}")

def gen_comp(mongo_db):
    EVAL_NUMBER = 16
    text_scenario_collection = mongoDB['userScenarioResults']
    delegation_collection = mongoDB['surveyResults']
    comparison_collection = mongoDB['humanToADMComparison']

    comparison_collection.delete_many({"evalNumber": EVAL_NUMBER})
    medic_collection = mongoDB['admMedics']

    data_to_use = list(text_scenario_collection.find(
        {"evalNumber": EVAL_NUMBER}
    ))

    total_text_scenarios = text_scenario_collection.count_documents(
        {"evalNumber": EVAL_NUMBER}
    )

    for entry in data_to_use:
        print(f"Currently processing {current_text_scenario} of {total_text_scenarios} total text scenarios Evaluation {EVAL_NUMBER}.")
        current_text_scenario += 1

        scenario_id = entry.get('scenario_id')
        session_id = entry.get('combinedSessionId')
        pid = entry.get('participantID')
        survey = list(delegation_collection.find({"results.pid": pid}))
        if len(survey) == 0:
            print(f"No survey found for {pid}")
            continue
        survey = survey[-1] # get last survey entry for this pid
        # get human to adm comparisons from delegation survey adms
        for page in survey['results']:
            if 'Medic' in page and ' vs ' not in page:
                page_scenario = survey['results'][page]['scenarioIndex']
                scenario_attribute = next((x for x in ['MF', 'SS', 'PS', 'AF'] if x in scenario_id), None)

                medic = medic_collection.find_one({'evalNumber': EVAL_NUMBER, 'name': page})
                adm_session = medic['admSessionId']

                res = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions?session_id_1={session_id}&session_id_2={adm_session}').json()
                # send document to mongo
                if res is not None and 'score' in res:
                    document = {
                        'pid': pid,
                        'adm_type': survey.get('results', {}).get(page, {}).get('admAlignment'),
                        'score': res['score'],
                        'text_scenario': scenario_id,
                        'text_session_id': session_id.replace('"', "").strip(),
                        'adm_scenario': page_scenario,
                        'adm_session_id': adm_session,
                        'adm_alignment_target': survey['results'][page]['admTarget'],
                        'evalNumber': EVAL_NUMBER
                    }
                    send_document_to_mongo(comparison_collection, document)
                else:
                    print(f'Error getting comparison for scenarios {scenario_id} and {page_scenario} with text session {session_id} and adm session {adm_session}', res)


    print("Human to ADM comparison values added to database.")


def send_document_to_mongo(comparison_collection, document):
    # do not send duplicate documents, make sure if one already exists, we just replace it
    found_docs = comparison_collection.find({'pid': document['pid'], 'adm_type': document['adm_type'], 'text_scenario': document['text_scenario'], 'adm_scenario': document['adm_scenario'], 'evalNumber': document['evalNumber'],
                                            'text_session_id': document['text_session_id'], 'adm_session_id': document['adm_session_id'], 'adm_alignment_target': document['adm_alignment_target']})
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