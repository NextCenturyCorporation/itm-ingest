import requests

from pymongo import MongoClient
from decouple import config

MONGO_URL = config('MONGO_URL')

# PROD TA1 outside AWS
# ADEPT_URL = "https://darpaitm.caci.com/adept/"
# ST_URL = "https://darpaitm.caci.com/soartech/" 

#DEV
ADEPT_URL="http://localhost:8081/"
# ST_URL="http://localhost:8084/"


# PROD TA1 inside AWS
# ADEPT_URL="http://10.216.38.101:8080/"
# ST_URL="http://10.216.38.125:8084"


def update_adept_text_adm_sessions(mongoDB):
    text_scenario_collection = mongoDB['userScenarioResults']
    text_scenario_to_update = text_scenario_collection.find({"evalNumber": 4})
    adm_collection = mongoDB["test"]
    adms_to_update = adm_collection.find({"evalNumber": 4})

    # Add text sessions to Adept Server
    sessions_by_pid = {}
    for entry in text_scenario_to_update:
        scenario_id = entry.get('scenario_id')
        session_id = entry.get('combinedSessionId', entry.get('serverSessionId'))
        data_id = entry.get('_id')
        pid = entry.get('participantID')
        kdmas = requests.get(f'{ADEPT_URL}api/v1/computed_kdma_profile?session_id={session_id}').json()
        
        # ADEPT's server lost our first week's worth of data, so we have to re-send probes
        new_id = None
        if 'DryRun' in scenario_id and 'value' not in kdmas:
            if pid in sessions_by_pid:
                new_id = sessions_by_pid[pid]['sid']
                sessions_by_pid[pid]['_ids'].append(data_id)
            else:
                adept_sid = requests.post(f'{ADEPT_URL}/api/v1/new_session').text.replace('"', '').strip()
                sessions_by_pid[pid] = {'sid': adept_sid, '_ids': [data_id]}
                new_id = adept_sid
            # collect probes
            probes = []
            for k in entry:
                if isinstance(entry[k], dict) and 'questions' in entry[k]:
                    if 'probe ' + k in entry[k]['questions'] and 'response' in entry[k]['questions']['probe ' + k] and 'question_mapping' in entry[k]['questions']['probe ' + k]:
                        response = entry[k]['questions']['probe ' + k]['response']
                        mapping = entry[k]['questions']['probe ' + k]['question_mapping']
                        if response in mapping:
                            probes.append({'probe': {'choice': mapping[response]['choice'], 'probe_id': mapping[response]['probe_id']}})
            send_probes(f'{ADEPT_URL}/api/v1/response', probes, new_id, scenario_id)
            print("Created text session with probes in Adept for: " + str(new_id))

        updates = {}
        if new_id is not None:
            # only applies to ADEPT, ST did not lose data
            updates['combinedSessionId'] = new_id
            # if new_id exists, we need to update the session id for all adept that this participant completed (we never know when it will be the last one)
            for data_id in sessions_by_pid[pid]['_ids']:
                text_scenario_collection.update_one({'_id': data_id}, {'$set': updates})        


    # Add ADM sessions to Adept Server
    for adm in adms_to_update:            
        # get new adm session
        probe_responses = []
        skip_adm = False
        for x in adm['history']:
            if x['command'] == 'Respond to TA1 Probe':
                if not any(substring in x['parameters']['scenario_id'] for substring in ["vol", "qol"]):
                    probe_responses.append(x['parameters'])
                else:
                    skip_adm = True
                    break
        if not skip_adm:
            adept_sid = update_adm_run(adm_collection, adm, probe_responses)
            print("ADM Session Added for : " + adept_sid)

def send_probes(probe_url, probes, sid, scenario):
    '''
    Sends the probes to the server
    '''
    for x in probes:
        if 'probe' in x and 'choice' in x['probe']:
            resp = requests.post(probe_url, json={
                "response": {
                    "choice": x['probe']['choice'],
                    "justification": "justification",
                    "probe_id": x['probe']['probe_id'],
                    "scenario_id": scenario,
                },
                "session_id": sid
            })
        
    


def update_adm_run(collection, adm, probes):
    adept_sid = requests.post(f'{ADEPT_URL}/api/v1/new_session').text.replace('"', "").strip()
    # send probes to server 
    for x in probes:
        requests.post(f'{ADEPT_URL}/api/v1/response', json={
            "response": {
                "choice": x['choice'],
                "justification": x["justification"],
                "probe_id": x['probe_id'],
                "scenario_id": x['scenario_id'],
            },
            "session_id": adept_sid
        })
    adm['history'][-1]['parameters']['session_id'] = adept_sid
    collection.update_one({'_id': adm['_id']}, {"$set": {"history": adm['history']}})   

    return adept_sid



def main():
    client = MongoClient(MONGO_URL)
    mongoDB = client['dashboard']
    update_adept_text_adm_sessions(mongoDB)


if __name__ == "__main__":
    main()