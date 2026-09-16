'''
Repopulates the observed adm runs so their session ids can be used to generate comparison scores. 
Then generate those comparison scores
'''
from scripts._1_5_5_june2025_check import get_probe_responses
from scripts._0_8_3_June_Collab_Comparison_Generation import main as gen_comp
import utils.db_utils as db_utils
from decouple import config
import requests

ADEPT_URL = config('ADEPT_URL')

def main(mongo_db):
    survey = mongo_db['delegationConfig'].find_one({'_id': 'delegation_v13.0'})

    #iterating over the observed adms in the survey
    for page in survey['survey']['pages']:
        if 'Medic' not in page['name']:
            continue

        #find matching adm run
        adm = mongo_db['admTargetRuns'].find_one({
            'alignment_target': page['target'],
            'scenario': page['scenarioIndex'],
            'evaluation.adm_name': page['admName']
        })

        if not adm:
            print(f"Error ADM not found for {page}")

        # i already wrote code for pulling out all of the probe responses
        probes, scenario_id = get_probe_responses(adm)
        if not probes:
            print(f'WARNING: no probe responses found for {adm.get("adm_name")} 'f'- {adm.get("scenario")} - skipping')
            continue

        # make new session and send probes
        adept_sid = requests.post(f'{ADEPT_URL}api/v1/new_session').text.replace('"', '').strip()
        db_utils.send_probes(f'{ADEPT_URL}api/v1/response', probes, adept_sid, scenario_id)

        # update session id on file (will be used in script 083 to gen comp scores)
        mongo_db['admTargetRuns'].update_one(
            {'_id': adm['_id']},
            {'$set': {'results.ta1_session_id': adept_sid}}
        )

        print(f'Updated {adm.get("adm_name")} - {adm.get("scenario")} -> session {adept_sid}')

    # generates the comparison scores for eval 18 (this needs to be edited to 19 for when we do the UK version)
    gen_comp(mongo_db, 18)