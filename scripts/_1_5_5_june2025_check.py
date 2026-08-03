'''
Designed to rescore JULY 2025 adm subset runs using server version 4.5.2
'''
import requests
from decouple import config

import utils.db_utils as db_utils

ADEPT_URL = config("ADEPT_URL")


def get_probe_responses(adm):
    probes = []
    scenario_id = None
    for entry in adm.get('history', []):
        if entry.get('command') == 'Respond to TA1 Probe':
            params = entry['parameters']
            scenario_id = params['scenario_id']
            probes.append({
                'probe': {
                    'choice': params['choice'],
                    'probe_id': params['probe_id'],
                }
            })
    return probes, scenario_id


def main(mongo_db):
    adm_collection = mongo_db['admTargetRuns']
    adms = list(adm_collection.find({'evalNumber': 9, 'adm_name': {'$regex': '_7_23'}}))

    for adm in adms:
        probes, scenario_id = get_probe_responses(adm)
        if not probes:
            print(f'WARNING: no probe responses found for {adm.get("adm_name")} '
                  f'- {adm.get("scenario")} - skipping')
            continue

        adept_sid = requests.post(f'{ADEPT_URL}api/v1/new_session').text.replace('"', '').strip()
        db_utils.send_probes(f'{ADEPT_URL}api/v1/response', probes, adept_sid, scenario_id)

        kdmas = requests.get(
            f'{ADEPT_URL}api/v1/computed_kdma_profile?session_id={adept_sid}'
        ).json()

        # overwrite the run's kdmas and session id with new stuff
        adm_collection.update_one(
            {'_id': adm['_id']},
            {'$set': {
                'results.kdmas': kdmas,
                'results.ta1_session_id': adept_sid,
            }}
        )

        print(f'Updated {adm.get("adm_name")} - {adm.get("scenario")} '
              f'-> session {adept_sid}, kdmas {kdmas}')