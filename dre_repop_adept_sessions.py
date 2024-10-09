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

AD_PROBES = {
    "DryRunEval-IO2-eval": ['Probe 4', 'Probe 8', 'Probe 9', 'Probe 9-B.1', 'Probe 9-A.1', 'Probe 10'],
    "DryRunEval-MJ2-eval": ['Probe 2B-1', 'Probe 2A-1', 'Response 3-B.2-B-gauze-v', 'Response 3-B.2-B-gauze-s', 'Response 3-B.2-A-gauze-v', 'Response 3-B.2-A-gauze-s', 'Probe 5', 'Probe 5-A.1', 'Probe 5-B.1', 'Probe 6', 'Probe 7'],
    "DryRunEval-IO4-eval": ['Probe 6', 'Probe 7', 'Probe 8', 'Probe 10'],
    "DryRunEval-MJ4-eval": ['Probe 1', 'Probe 2 kicker', 'Probe 2 passerby', 'Probe 2-A.1', 'Probe 2-D.1', 'Probe 2-D.1-B.1', 'Probe 3', 'Probe 3-A.1', 'Probe 3-B.1', 'Probe 9', 'Response 10-B', 'Response 10-C', 'Probe 10-A.1'],
    "DryRunEval-IO5-eval": ['Probe 7', 'Probe 8', 'Probe 8-A.1', 'Probe 8-A.1-A.1', 'Probe 9', 'Probe 9-A.1', 'Probe 9-B.1', 'Probe 9-C.1'],
    "DryRunEval-MJ5-eval": ['Probe 1', 'Probe 1-A.1', 'Probe 1-B.1', 'Probe 2', 'Response 2-A.1-B', 'Response 2-B.1-B', 'Response 2-B.1-B-gauze-u', 'Response 2-A.1-B-gauze-sp', 'Probe 2-A.1-A.1', 'Probe 2-B.1-A.1', 'Probe 2-A.1-B.1-A.1', 'Probe 2-B.1-B.1-A.1', 'Probe 3', 'Probe 4']
}

def get_text_scenario_kdmas(mongoDB):
    text_scenario_collection = mongoDB['userScenarioResults']
    text_scenario_to_update = text_scenario_collection.find({"evalNumber": 4})

    delegation_collection = mongoDB['surveyResults']
    del_adm_runs_collection = mongoDB['delegationADMRuns']
    del_adm_runs_collection.drop()

    adm_collection = mongoDB["test"]
    medic_collection = mongoDB['admMedics']

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
            kdmas = requests.get(f'{ADEPT_URL}api/v1/computed_kdma_profile?session_id={new_id}').json()
            print("Created text session with probes in Adept for: " + str(new_id))
            # print(str(kdmas))

        updates = {'kdmas': kdmas}
        if new_id is not None:
            # only applies to ADEPT, ST did not lose data
            updates['combinedSessionId'] = new_id
            # if new_id exists, we need to update the kdmas for all adept that this participant completed (we never know when it will be the last one)
            for data_id in sessions_by_pid[pid]['_ids']:
                text_scenario_collection.update_one({'_id': data_id}, {'$set': updates})
        else:
            text_scenario_collection.update_one({'_id': data_id}, {'$set': updates})            
#######################################

    text_scenario_to_update.rewind()
    for entry in text_scenario_to_update:            
        scenario_id = entry.get('scenario_id')
    
        if 'MJ1' in scenario_id or 'IO1' in scenario_id:
            # ignore test scenarios from adept
            continue

        session_id = entry.get('combinedSessionId', entry.get('serverSessionId')).replace('"', '').strip()
        pid = entry.get('participantID')
        survey = list(delegation_collection.find({"results.Participant ID Page.questions.Participant ID.response": pid}))
        if len(survey) == 0:
            print(f"No survey found for {pid}")
            continue
        survey = survey[-1] # get last survey entry for this pid
        for page in survey['results']:
            if 'Medic' in page and ' vs ' not in page:
                page_scenario = survey['results'][page]['scenarioIndex']
                if 'DryRunEval' in scenario_id and 'DryRunEval' in page_scenario:
                    adm = find_adm(medic_collection, adm_collection, page, page_scenario.replace('IO', 'MJ'), survey)
                    if adm is None:
                        continue
                    adm_target = adm['history'][len(adm['history'])-1]['parameters']['target_id']
                    found_mini_adm = del_adm_runs_collection.find_one({'target': adm_target, 'scenario': page_scenario.replace('IO', 'MJ'), 'adm_name': survey['results'][page]['admName']})
                    if found_mini_adm is None:
                        # get new adm session
                        probe_ids = AD_PROBES[page_scenario] # this is where IO/MJ comes into play - choosing the probes
                        probe_responses = []
                        for x in adm['history']:
                            if x['command'] == 'Respond to TA1 Probe':
                                if x['parameters']['choice'] in probe_ids or x['parameters']['probe_id'] in probe_ids:
                                    probe_responses.append(x['parameters'])
                        found_mini_adm = mini_adm_run(del_adm_runs_collection, probe_responses, adm_target, survey['results'][page]['admName'])

                        print("ADM Session Added for : " + str(found_mini_adm["session_id"])) 
#######################################            

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

def mini_adm_run(collection, probes, target, adm_name):
    adept_sid = requests.post(f'{ADEPT_URL}/api/v1/new_session').text.replace('"', "").strip()
    scenario = None
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
        scenario = x['scenario_id']
    alignment = requests.get(f'{ADEPT_URL}/api/v1/alignment/session?session_id={adept_sid}&target_id={target}&population=false').json()
    doc = {'session_id': adept_sid, 'probes': probes, 'alignment': alignment, 'target': target, 'scenario': scenario, 'adm_name': adm_name, 'evalNumber': 4}
    collection.insert_one(doc)

    return doc

def find_adm(medic_collection, adm_collection, page, page_scenario, survey):
    adm_session = medic_collection.find_one({'evalNumber': 4, 'name': page})['admSession']
    adms = adm_collection.find({'evalNumber': 4, 'history.0.parameters.session_id': adm_session, 'history.0.response.id': page_scenario, 'history.0.parameters.adm_name': survey['results'][page]['admName']})
    adm = None
    for x in adms:
        if x['history'][len(x['history'])-1]['parameters']['target_id'] == survey['results'][page]['admTarget']:
            adm = x
            break
    if adm is None:
        print(f"No matching adm found for scenario {page_scenario} with adm {survey['results'][page]['admName']} (session {adm_session})")
        return None
    return adm

def main():
    client = MongoClient(MONGO_URL)
    mongoDB = client['dashboard']
    print("New db version, execute scripts")

    get_text_scenario_kdmas(mongoDB)


if __name__ == "__main__":
    main()