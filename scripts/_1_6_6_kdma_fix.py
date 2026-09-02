from decouple import config
from scripts._1_4_9_rq1_june26 import main as rerun_script
import requests


ADEPT_URL = config('ADEPT_URL')

def main(mongo_db):
    rerun_script(mongo_db)
    adm_runs = list(mongo_db['admMedics'].find({'evalNumber': 17}))

    for adm in adm_runs:
        session_id = adm['admSessionId']

        kdmas = requests.get(
            f'{ADEPT_URL}api/v1/computed_kdma_profile?session_id={session_id}'
        ).json()

        mongo_db['admMedics'].update_one(
            {'_id': adm['_id']},
            {'$set': {
                'kdmas': kdmas,
            }}
        )

        mongo_db['admTargetRuns'].update_one(
            {'results.ta1_session_id': session_id},
            {'$set': {
                'results.kdmas': kdmas,
            }}
        )

        print(f'Updated {adm.get("admName")} - {adm.get("scenarioName")} -> session {session_id}, kdmas {kdmas}')