import requests
from decouple import config
from bson import ObjectId
ADEPT = config('ADEPT_URL')

# spurious text documents ids that need to be deleted
delete_ids = ['69dd5c0acbb59a657e5a14b1', '69d93502cbb59a6f505a03f7', '69d72e2bcbb59afc5259faac', '69d66ad2cbb59a810c59f9e0']

def main(mongo_db):
    text_results = list(mongo_db['userScenarioResults'].find({'evalNumber': 16}))

    # delete spurious
    for id in delete_ids:
        mongo_db['userScenarioResults'].delete_one({
            '_id': ObjectId(id)
        })
    
    by_pid = {}
    for res in text_results:
        by_pid.setdefault(res['participantID'], []).append(res)
    

    for pid, results in by_pid.items():
        subpop_doc = next((r for r in results if 'subpopulation' in r.get('scenario_id', '')), None)
        if not subpop_doc:
            print(f'No subpop doc found for pid group {pid}')
            continue
        
        sid = subpop_doc['combinedSessionId']
        subpop_res = subpop_doc['subPopResult']
        #use opposite
        sub_to_use = 'A' if subpop_res == 'B' else 'B'

        response = requests.get(
            f'{ADEPT}api/v1/computed_kdma_profile',
            params={'session_id': sid, 'enable_subpop': sub_to_use},
            headers={'accept': 'application/json'},
        )
        if not response.ok or not response.text:
            print(f'Bad response from pid group {pid}', response.status_code, response.text)
            continue

        try:
            payload = response.json()
        except requests.exceptions.JSONDecodeError:
            print(f'Non-JSON response from pid group {pid}', response.status_code, repr(response.text[:200]))
            continue

        other_docs = [r for r in results if 'subpop' not in r.get('scenario_id', '')]
        for doc in other_docs:
            mongo_db['userScenarioResults'].update_one(
                {'_id': doc['_id']},
                {'$set': {'otherSubKDMA': payload}}
            )
            