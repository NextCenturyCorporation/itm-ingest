import requests

ADEPT_URL = "https://darpaitm.caci.com/adept/"
ST_URL = "https://darpaitm.caci.com/soartech/" 

def get_text_scenario_kdmas(mongoDB):
    text_scenario_collection = mongoDB['userScenarioResults']

    data_to_update = text_scenario_collection.find(
        {"evalNumber": 4}
    )
    sessions_by_pid = {}
    for entry in data_to_update:
        scenario_id = entry.get('scenario_id')
        session_id = entry.get('combinedSessionId', entry.get('serverSessionId'))
        data_id = entry.get('_id')
        pid = entry.get('participantID')
        kdmas = requests.get(f'{ST_URL if "qol" in scenario_id or "vol" in scenario_id else ADEPT_URL}api/v1/computed_kdma_profile?session_id={session_id}').json()

        # ADEPT's server lost our first week's worth of data, so we have to re-send probes
        new_id = None
        if 'DryRun' in scenario_id and (len(kdmas) == 0 or 'value' not in kdmas[1]):
            print('could not find session id. Recreating session')
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
                        response = entry[k]['questions']['probe ' + k]['response'].replace('.', '')
                        mapping = entry[k]['questions']['probe ' + k]['question_mapping']
                        if response in mapping:
                            probes.append({'probe': {'choice': mapping[response]['choice'], 'probe_id': mapping[response]['probe_id']}})
                        else:
                            print('could not find response in mapping!', response, list(mapping.keys()))
            send_probes(f'{ADEPT_URL}/api/v1/response', probes, new_id, scenario_id)
            # after probes are sent, get kdmas
            kdmas = requests.get(f'{ADEPT_URL}api/v1/computed_kdma_profile?session_id={new_id}').json()


        # create object to add/update in database
        updates = {'kdmas': kdmas}
        if new_id is not None:
            # only applies to ADEPT, ST did not lose data
            updates['combinedSessionId'] = new_id
            # if new_id exists, we need to update the kdmas for all adept that this participant completed (we never know when it will be the last one)
            for data_id in sessions_by_pid[pid]['_ids']:
                text_scenario_collection.update_one({'_id': data_id}, {'$set': updates})
        else:
            text_scenario_collection.update_one({'_id': data_id}, {'$set': updates})

    print("KDMAs added to text scenarios.")

def send_probes(probe_url, probes, sid, scenario):
    '''
    Sends the probes to the server
    '''
    for x in probes:
        if 'probe' in x and 'choice' in x['probe']:
            requests.post(probe_url, json={
                "response": {
                    "choice": x['probe']['choice'],
                    "justification": "justification",
                    "probe_id": x['probe']['probe_id'],
                    "scenario_id": scenario,
                },
                "session_id": sid
            })
