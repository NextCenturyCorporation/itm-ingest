from decouple import config
from scripts._1_5_5_june2025_check import get_probe_responses
import utils.db_utils as db_utils
import requests


ADEPT_URL = config('ADEPT_URL')

scenario_ids = [
        'Feb2026-OW_desert',
        'Feb2026-OW_desert2',
        'April2026-OW_desert',
        'April2026-OW_urban'
]

def main(mongo_db):
    adm_runs = list(mongo_db['admTargetRuns'].find({
        'scenario': {'$in': scenario_ids}
    }))

    for adm in adm_runs:
        probes, scenario_id = get_probe_responses(adm)
        if not probes:
            print(f'WARNING: no probe responses found for {adm.get("adm_name")} 'f'- {adm.get("scenario")} - skipping')
            continue

        adept_sid = requests.post(f'{ADEPT_URL}api/v1/new_session').text.replace('"', '').strip()
        db_utils.send_probes(f'{ADEPT_URL}api/v1/response', probes, adept_sid, scenario_id)

        kdmas = requests.get(
            f'{ADEPT_URL}api/v1/computed_kdma_profile?session_id={adept_sid}'
        ).json()

        # overwrite the run's kdmas and session id with new stuff
        mongo_db['admTargetRuns'].update_one(
            {'_id': adm['_id']},
            {'$set': {
                'results.kdmas': kdmas,
                'results.ta1_session_id': adept_sid,
            }}
        )

        print(f'Updated {adm.get("adm_name")} - {adm.get("scenario")} '
              f'-> session {adept_sid}, kdmas {kdmas}')