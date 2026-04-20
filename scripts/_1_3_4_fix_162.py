import requests
from decouple import config

ADEPT_URL = config('ADEPT_URL')

def main(mongo_db):
    collection = mongo_db['userScenarioResults']

    subpop_doc = collection.find_one({
        'participantID': '202604162',
        'scenario_id': 'April2026-subpopulation'
    })

    session_id = subpop_doc['combinedSessionId']
    subpop_value = subpop_doc['subPopResult']

    params = {
        'session_id': session_id,
        'kdma_id': 'merit',
        'enable_subpop': subpop_value
    }

    resp = requests.get(f"{ADEPT_URL}/api/v1/get_ordered_alignment", params=params)
    resp.raise_for_status()
    merit_entry = {'target': 'merit', 'response': resp.json()}

    result = collection.update_many(
        {'participantID': '202604162', 'combinedMostLeastAligned': {'$exists': True}},
        {'$push': {'combinedMostLeastAligned': merit_entry}}
    )

    print(f"Updated {result.modified_count} documents")