import requests
from decouple import config
from scripts._0_3_0_percent_matching_probes import main as find_matching_probe_percentage


MONGO_URL = config('MONGO_URL')
ADEPT_URL = config("ADEPT_URL")


SCENARIO_MAP = {
    "phase1-adept-eval-MJ2": "DryRunEval-MJ2-eval",
    "phase1-adept-eval-MJ4": "DryRunEval-MJ4-eval",
    "phase1-adept-eval-MJ5": "DryRunEval-MJ5-eval",
    "phase1-adept-train-MJ1": "DryRunEval.MJ1",
    "phase1-adept-train-IO1": "DryRunEval.IO1"
}

SURVEY_UPDATES = {
    "202411534": {
        "aligned": "most aligned"
    },
    "202411546": {
        "misaligned": "adept recalculation exception",
        "aligned": "adept recalculation exception"
    },
    "202411557": {
        "aligned": "adept recalculation exception"
    },
    "202411564": {
        "misaligned": "adept recalculation exception",
        "aligned": "adept recalculation exception"
    },
    "202411354": {
        "misaligned": "adept recalculation exception"
    },
    "202411353": {
        "misaligned": "adept recalculation exception",
        "aligned": "adept recalculation exception"
    },
    "202411359": {
        "misaligned": "adept recalculation exception",
        "aligned": "adept recalculation exception"
    },
    "202411360": {
        "misaligned": "adept recalculation exception",
    },
    "202411569": {
        "misaligned": "adept recalculation exception",
        "aligned": "adept recalculation exception"
    },
    "202411570": {
        "misaligned": "adept recalculation exception",
    }
}


def main(mongoDB, run_adms=True):
    """ 
    Repopulates Phase 1 ADEPT Sessions.
    
    ADEPT doesn't persist Phase 1 session information.
    
    This needs to run whenever the ADEPT server is restarted.
    """

    print("Repopulating ADEPT Text/ADM Sessions")
    text_scenario_collection = mongoDB['userScenarioResults']
    text_scenario_to_update = text_scenario_collection.find({"evalNumber": 5})
    survey_collection = mongoDB['surveyResults']
    adm_collection = mongoDB["test"]
    adms_to_update = adm_collection.find({"evalNumber": 5})
    mini_adms = mongoDB['delegationADMRuns']
    mini_adms.delete_many({"evalNumber": 5})
    comparison_db = mongoDB['humanToADMComparison']
    comparison_db.delete_many({"text_scenario" : {"$regex" : "DryRunEval"}, "evalNumber": 5})

    # Add text sessions to Adept Server
    sessions_by_pid = {}
    mj5s = {}
    for entry in text_scenario_to_update:
        scenario_id = entry.get('scenario_id')
        session_id = entry.get('combinedSessionId', entry.get('serverSessionId'))
        data_id = entry.get('_id')
        pid = entry.get('participantID')
        
        # ADEPT's server loses data when we restart it, so we have to re-send probes
        new_id = None
        if 'adept' in scenario_id:
            scenario_id = SCENARIO_MAP[scenario_id]
            if pid in sessions_by_pid:
                new_id = sessions_by_pid[pid]['sid']
                sessions_by_pid[pid]['_ids'].append(data_id)
            else:
                adept_sid = requests.post(f'{ADEPT_URL}api/v1/new_session').text.replace('"', '').strip()
                sessions_by_pid[pid] = {'sid': adept_sid, '_ids': [data_id]}
                new_id = adept_sid
            if 'MJ5' in scenario_id:
                mj5s[pid] = new_id
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
                    
            send_probes(f'{ADEPT_URL}api/v1/response', probes, new_id, scenario_id)
            print("Created text session with probes in Adept for: " + str(new_id))
            print("-----")

        updates = {}
        if new_id is not None:
            updates['combinedSessionId'] = new_id
            # if this is one of the MJ5 scenarios, we will need to update alignment values
            if pid in mj5s:
                kdmas = requests.get(f"{ADEPT_URL}api/v1/computed_kdma_profile?session_id={mj5s[pid]}").json()
                mj = requests.get(f"{ADEPT_URL}api/v1/get_ordered_alignment?session_id={mj5s[pid]}&kdma_id=Moral%20judgement").json()
                io = requests.get(f"{ADEPT_URL}api/v1/get_ordered_alignment?session_id={mj5s[pid]}&kdma_id=Ingroup%20Bias").json()
                updates['mostLeastAligned'] = [
                    {'target': 'Moral judgement', 'response': mj},
                    {'target': 'Ingroup Bias', 'response': io}
                ]
                updates['kdmas'] = kdmas
            # if new_id exists, we need to update the session id for all adept that this participant completed (we never know when it will be the last one)
            # we do NOT need to recalculate alignment, just update the session id
            for data_id in sessions_by_pid[pid]['_ids']:
                text_scenario_collection.update_one({'_id': data_id}, {'$set': updates})     
            comparison_db.update_many({'text_session_id': session_id}, {'$set': {'text_session_id': new_id}})   
   
    # update survey entries with incorrect adm calculations
    for pid in SURVEY_UPDATES:
        res = survey_collection.find_one({"results.evalNumber": 5, 'results.Participant ID Page.questions.Participant ID.response': pid})
        if not res:
            print(f"Could not find survey for {pid}")
            continue
        for k in res['results']:
            if 'Medic' in k and ' vs ' not in k:
                page = res['results'][k]
                if 'DryRunEval' in page['scenarioIndex'] and page['admAlignment'] != 'baseline':
                        target = page['admTarget']
                        target = f"{('MJ' if 'Moral' in target else 'IO')}{target[-1]}"
                        if "IO" in target:
                            continue
                        if page['admAlignment'] in SURVEY_UPDATES[pid]:
                            res['results'][k]['admChoiceProcess'] = SURVEY_UPDATES[pid][page['admAlignment']]
        survey_collection.update_one({'_id': res['_id']}, {'$set': res})     

    # Add ADM sessions to Adept Server
    if run_adms:
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
                adept_sid = update_adm_run(adm_collection, adm, probe_responses, mini_adms, comparison_db)
                print("ADM Session Added for : " + adept_sid)
                print("-----")

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
        
        
def update_adm_run(collection, adm, probes, mini_adms, comparison_db):
    # get a new session id for adms
    adept_sid = requests.post(f'{ADEPT_URL}api/v1/new_session').text.replace('"', "").strip()
    # send probes to server 
    for x in probes:
        requests.post(f'{ADEPT_URL}api/v1/response', json={
            "response": {
                "choice": x['choice'],
                "justification": x["justification"],
                "probe_id": x['probe_id'],
                "scenario_id": x['scenario_id'],
            },
            "session_id": adept_sid
        })
    prev_session_id = adm['history'][-1]['parameters']['session_id']
    mini_adms.update_many({'session_id': prev_session_id}, {"$set": {"session_id": adept_sid}})
    comparison_db.update_many({'adm_session_id': prev_session_id}, {"$set": {"adm_session_id": adept_sid}})
    adm['history'][-1]['parameters']['session_id'] = adept_sid
    collection.update_one({'_id': adm['_id']}, {"$set": {"history": adm['history']}})   

    return adept_sid

if __name__ == "__main__":
    main()