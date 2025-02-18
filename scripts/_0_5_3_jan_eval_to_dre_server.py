from decouple import config 
import requests
from adept_repop_ph1 import SCENARIO_MAP
import utils.db_utils as db_utils

PH1_URL = config("ADEPT_URL")
DRE_URL = config("ADEPT_DRE_URL")

def main(db):
    # send all JAN sessions to DRE server
    print("Populating DRE server with JAN Eval data")
    send_JAN_to_DRE(db)

def send_JAN_to_DRE(mongoDB, EVAL_NUMBER=6):
    '''
    Populates the DRE server with PH1 data
    '''
    text_scenario_collection = mongoDB['userScenarioResults']

    data_to_use = text_scenario_collection.find(
        {"evalNumber": EVAL_NUMBER}
    )

    # start by creating sessions in dre server for phase 1 data
    sessions_by_pid = {}
    for entry in data_to_use:
        scenario_id = entry.get('scenario_id')
        dre_id = entry.get('dreSessionId', None)
        data_id = entry.get('_id')
        pid = entry.get('participantID')
        
        new_id = None
        if 'adept' in scenario_id and dre_id is None:
            scenario_id = SCENARIO_MAP[scenario_id]
            if pid in sessions_by_pid:
                new_id = sessions_by_pid[pid]['sid']
                sessions_by_pid[pid]['_ids'].append(data_id)
            else:
                adept_sid = requests.post(f'{DRE_URL}api/v1/new_session').text.replace('"', '').strip()
                sessions_by_pid[pid] = {'sid': adept_sid, '_ids': [data_id]}
                new_id = adept_sid
            # collect probes
            probes = []
            for k in entry:
                if isinstance(entry[k], dict) and 'questions' in entry[k]:
                    for valid_key in [f'probe {k}', f'probe {k}_conditional']:
                        probe_data = entry[k]['questions'].get(valid_key, {})
                        if 'response' in probe_data and 'question_mapping' in probe_data:
                            response = probe_data['response'].replace('.', '')
                            mapping = probe_data['question_mapping']
                            if response in mapping:
                                if isinstance(mapping[response]['choice'], list):
                                    for c in mapping[response]['choice']:
                                        probes.append({'probe': {'choice': c, 'probe_id': mapping[response]['probe_id']}})
                                else:
                                    probes.append({'probe': {'choice': mapping[response]['choice'], 'probe_id': mapping[response]['probe_id']}})
                            else:
                                print('could not find response in mapping!', response, list(mapping.keys()))
            db_utils.send_probes(f'{DRE_URL}api/v1/response', probes, new_id, scenario_id)

        updates = {}
        if new_id is not None:
            updates['dreSessionId'] = new_id
            # if new_id exists, we need to update the session id for all adept that this participant completed (we never know when it will be the last one)
            for data_id in sessions_by_pid[pid]['_ids']:
                text_scenario_collection.update_one({'_id': data_id}, {'$set': updates})        

    print("JAN eval sent to ADEPT DRE server - ids updated.")
        

if __name__ == '__main__':
    from pymongo import MongoClient
    MONGO_URL = config('MONGO_URL')
    client = MongoClient(MONGO_URL)
    mongoDB = client['dashboard']
    main(mongoDB)