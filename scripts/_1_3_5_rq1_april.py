'''
Runs oracle adms through TA1 server so session id's are available for rq1 comparisons
'''
import requests
from decouple import config
import utils.db_utils as db_utils
ADEPT_URL = config('ADEPT_URL')

def main(mongo_db):
    run_obs(mongo_db)
    gen_comp(mongo_db)

def run_obs(mongo_db):
    medics = mongo_db['admMedics']
    observed_oracles = list(medics.find({'evalNumber': 16}))

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
    text_scenario_collection = mongo_db['userScenarioResults']
    delegation_collection = mongo_db['surveyResults']
    comparison_collection = mongo_db['humanToADMComparison']

    comparison_collection.delete_many({"evalNumber": EVAL_NUMBER})
    medic_collection = mongo_db['admMedics']

    data_to_use = list(text_scenario_collection.find(
        {"evalNumber": EVAL_NUMBER}
    ))

    total_text_scenarios = len(data_to_use)
    current_text_scenario = 0

    for entry in data_to_use:
        current_text_scenario += 1
        print(f"Currently processing {current_text_scenario} of {total_text_scenarios} total text scenarios Evaluation {EVAL_NUMBER}.")

        scenario_id = entry.get('scenario_id')
        pid = entry.get('participantID')

        survey = list(delegation_collection.find({"results.pid": pid, "results.evalNumber": EVAL_NUMBER}))
        if len(survey) == 0:
            print(f"No survey found for {pid}")
            continue
        survey = survey[-1]

        # PS document has all three session ids I need, so just grab that
        ps2_doc = text_scenario_collection.find_one({
            'participantID': pid,
            'evalNumber': EVAL_NUMBER,
            'scenario_id': {'$regex': 'PS'}
        })

        if not ps2_doc:
            print(f"No PS document found for {pid}")
            continue

        subpop_doc = text_scenario_collection.find_one({
            'participantID': pid,
            'evalNumber': 16,
            'scenario_id': {'$regex': 'subpopulation'}
        })

        if not subpop_doc:
            print(f"No subpop document found for {pid}")
            continue

        participant_subpop = subpop_doc.get('subPopResult')

        for page in survey['results']:
            if 'Medic' not in page or ' vs ' in page:
                continue

            page_data = survey['results'][page]
            page_scenario = page_data.get('scenarioIndex')
            if not page_scenario:
                continue

            # figure out what session id to use 
            if 'MF-PS' in page_scenario:
                session_id = ps2_doc.get('MF-PS_sessionId')
            elif 'AF-PS' in page_scenario:
                session_id = ps2_doc.get('AF-PS_sessionId')
            elif 'MF-observe' in page_scenario or 'AF-observe' in page_scenario:
                session_id = ps2_doc.get('combinedSessionId')
            else:
                #shouldnt happen
                print(f"Couldnt match page_scenario of {page_scenario}")
                continue

            if not session_id:
                print(f"No session ID found for {pid} page {page} scenario {page_scenario}")
                continue

            # Match text scenario attribute to medic scenario attribute
            scenario_attribute = next((x for x in ['MF', 'SS', 'PS', 'AF'] if x in scenario_id), None)
            if scenario_attribute is None or scenario_attribute not in page_scenario:
                continue

            medic = medic_collection.find_one({'evalNumber': EVAL_NUMBER, 'name': page})
            if not medic:
                print(f"No medic found for {page}")
                continue

            adm_session = medic.get('admSessionId')
            if not adm_session:
                print(f"No admSessionId for medic {page}")
                continue

            base_url = f'{ADEPT_URL}api/v1/alignment/compare_sessions'

            query_params = {
                'session_id_1': session_id,
                'session_id_2': adm_session,
            }

            # Only add optional params if they exist
            if medic['admName'] == 'Oracle':
                if participant_subpop:
                    query_params['enable_subpop'] = participant_subpop

                query_params['kdma_filter'] = (
                    'affiliation' if 'AF' in medic['scenarioIndex'] else 'merit'
                )

            response = requests.get(base_url, params=query_params)

            if response.status_code != 200:
                print(f"Request failed: {response.status_code} - {response.text}")
                continue

            try:
                res = response.json()
            except Exception:
                print(f"Invalid JSON response: {response.text}")
                continue

            if res is not None and 'score' in res:
                document = {
                    'pid': pid,
                    'score': res['score'],
                    'text_scenario': scenario_id,
                    'text_session_id': session_id.replace('"', '').strip(),
                    'adm_scenario': page_scenario,
                    'adm_session_id': adm_session,
                    'adm_alignment_target': page_data.get('admTarget'),
                    'evalNumber': EVAL_NUMBER,
                }

                if medic['admName'] == 'Oracle':
                    document['subpop'] = participant_subpop

                send_document_to_mongo(comparison_collection, document)
            else:
                print(f'Error getting comparison for {scenario_id} and {page_scenario} with text session {session_id} and adm session {adm_session}', res)

    print("Human to ADM comparison values added to database.")


def send_document_to_mongo(comparison_collection, document):
    # do not send duplicate documents, make sure if one already exists, we just replace it
    found_docs = comparison_collection.find({'pid': document['pid'], 'text_scenario': document['text_scenario'], 'adm_scenario': document['adm_scenario'], 'evalNumber': document['evalNumber'],
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