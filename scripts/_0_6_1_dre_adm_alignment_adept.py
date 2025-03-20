# _0_5_4 sends all phase 1 adms (ADEPT only) to the DRE server
# this gets the alignment using those session ids and stores it in the db

from decouple import config 
import requests


DRE_URL = config("ADEPT_DRE_URL")

def main(mongoDB):
    '''Populates the DRE server with ALL ADEPT adms'''
    all_adms = mongoDB['admTargetRuns']
    adept_adms = all_adms.find({'evalNumber': 5, 'scenario': {'$regex': 'DryRunEval'}})

    for adm in adept_adms:
        history = adm['history']
        dre_session_id = history[-1]['parameters'].get('dreSessionId')
        target = adm["alignment_target"]
        if dre_session_id is None:
            print(f'Error getting dre session id from {adm["adm_name"]} - {adm["scenario"]} - {target}')
            continue
        
        # dre version of alignment score
        alignment = requests.get(f'{DRE_URL}api/v1/alignment/session?session_id={dre_session_id}&target_id={target}&population=false').json()
        
        history[-1]['response']['dre_alignment'] = alignment
        all_adms.update_one({'_id': adm['_id']}, {'$set': {'history': history}})


    print("ADEPT Phase 1 ADMs now have DRE alignment score attached.")
        