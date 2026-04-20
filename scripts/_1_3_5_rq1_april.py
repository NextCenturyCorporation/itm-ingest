'''
Runs oracle adms through TA1 server so session id's are available for rq1 comparisons
'''
import requests
from decouple import config
import utils.db_utils as db_utils
from scripts._0_8_3_June_Collab_Comparison_Generation import main as gen_comp
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
