from decouple import config 
import requests


DRE_URL = config("ADEPT_DRE_URL")

def main(mongoDB):
    '''Populates the DRE server with ALL ADEPT adms'''
    all_adms = mongoDB['test']
    adept_adms = all_adms.find({'evalNumber': 5, 'scenario': {'$regex': 'DryRunEval'}})

    for adm in adept_adms:
        # start new adept session
        adept_sid = requests.post(f'{DRE_URL}api/v1/new_session').text.replace('"', '').strip()
        probe_responses = []
        for x in adm['history']:
            if x['command'] == 'Respond to TA1 Probe':
                probe_responses.append(x['parameters'])
        send_probes(probe_responses, adept_sid)
        history = adm['history']
        history[-1]['parameters']['dreSessionId'] = adept_sid
        all_adms.update_one({'_id': adm['_id']}, {'$set': {'history': history}})


    print("All Phase 1 ADMs sent to ADEPT DRE server - dreSessionIds added.")
        
def send_probes(probe_responses, adept_sid):
    for x in probe_responses:
        requests.post(f'{DRE_URL}api/v1/response', json={
            "response": {
                "choice": x['choice'],
                "justification": x["justification"],
                "probe_id": x['probe_id'],
                "scenario_id": x['scenario_id'],
            },
            "session_id": adept_sid
        })