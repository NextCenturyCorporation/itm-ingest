import requests
from decouple import config 

ADEPT_URL = config("ADEPT_DRE_URL")
ST_URL = config("ST_DRE_URL")

def main(mongoDB):
    text_scenario_collection = mongoDB['userScenarioResults']

    data_to_update = text_scenario_collection.find(
        {"evalNumber": 4}
    )
    for entry in data_to_update:
        scenario_id = entry.get('scenario_id')
        session_id = entry.get('combinedSessionId', entry.get('serverSessionId'))
        data_id = entry.get('_id')
        kdmas = requests.get(f'{ST_URL if "qol" in scenario_id or "vol" in scenario_id else ADEPT_URL}api/v1/computed_kdma_profile?session_id={session_id}').json()


        # create object to add/update in database
        updates = {'kdmas': kdmas}
        text_scenario_collection.update_one({'_id': data_id}, {'$set': updates})

    print("KDMAs added to text scenarios.")

