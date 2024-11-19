import requests, json

MONGO_URL = "mongodb://simplemongousername:simplemongopassword@localhost:27030/?authSource=dashboard" #config('MONGO_URL')
ST_URL = "https://darpaitm.caci.com/soartech/" #config("ST_URL")


def rerun_soartech_adm_sessions(mongoDB):
    adm_collection = mongoDB["test"]
    adms_to_update = adm_collection.find({"evalNumber": 5})

    # Rerun ST sessions 
    counts = {}
    scores = {}
    for adm in adms_to_update:
        # get adm name
        where_is_name = 0
        adm_name = adm['history'][0].get('parameters', {}).get('adm_name', None)
        if adm_name is None:
            adm_name = adm['history'][1].get('parameters', {}).get('adm_name', None)
            where_is_name = 1
        if adm_name is None:
            print("Could not get adm name for " + adm['_id'])
            continue
        # only keep good adm runs
        good_adm_names = ['ALIGN-ADM-ComparativeRegression-Llama-3.2-3B-Instruct-SoarTech-MatchingChars__5f94293d-a834-4ae7-b3c3-d820a377a6db',
                          'ALIGN-ADM-OutlinesBaseline__9a0c9e90-3140-40fb-8fe6-36f9508ccd36', 
                          'ALIGN-ADM-ComparativeRegression-Mistral-7B-Instruct-v0.2-ADEPT-10Sample__509b769c-34b7-451f-afe4-8ea63b982815',
                          'ALIGN-ADM-OutlinesBaseline__07b34c32-7f75-488d-9ce7-ad31c638fd0b',
                          'ALIGN-ADM-OutlinesBaseline', 
                          'ALIGN-ADM-ComparativeRegression-ICL-Template', 
                          'TAD-aligned', 'TAD-severity-baseline', 'TAD-baseline']

        adm_name_mapping = {
            'ALIGN-ADM-ComparativeRegression-Llama-3.2-3B-Instruct-SoarTech-MatchingChars__5f94293d-a834-4ae7-b3c3-d820a377a6db' : 'ALIGN-ADM-ComparativeRegression-ICL-Template',
            'ALIGN-ADM-OutlinesBaseline__9a0c9e90-3140-40fb-8fe6-36f9508ccd36': 'ALIGN-ADM-OutlinesBaseline', 
            'ALIGN-ADM-ComparativeRegression-Mistral-7B-Instruct-v0.2-ADEPT-10Sample__509b769c-34b7-451f-afe4-8ea63b982815': 'ALIGN-ADM-ComparativeRegression-ICL-Template',
            'ALIGN-ADM-OutlinesBaseline__07b34c32-7f75-488d-9ce7-ad31c638fd0b': 'ALIGN-ADM-OutlinesBaseline'
        }
        # remove unnecessary adms
        if adm_name not in good_adm_names:
            adm_collection.delete_one({'_id': adm['_id']})
            continue
        if adm_name not in counts:
            counts[adm_name] = 0
        counts[adm_name] += 1
        # replace long kitware names with shorter names
        if adm_name in adm_name_mapping:
            adm['history'][where_is_name]['parameters']['adm_name'] = adm_name_mapping[adm_name]
            adm_collection.update_one({'_id': adm['_id']}, {"$set": {"history": adm['history']}})
        
        # get new adm session
        probe_responses = []
        skip_adm = False
        for x in adm['history']:
            if x['command'] == 'Respond to TA1 Probe':
                if any(substring in x['parameters']['scenario_id'] for substring in ["vol", "qol"]):
                    # collect probe responses for st
                    probe_responses.append(x['parameters'])
                else:
                    # not an st scenario - skip!
                    skip_adm = True
                    break
        if not skip_adm:
            # get updated alignment scores and store in db
            adm_score = update_adm_run(adm_collection, adm, probe_responses)
            # prepare printout of alignment scores per adm per target
            if adm_name not in scores:
                scores[adm_name] = []
            scores[adm_name].append(adm_score)

    print(counts)
    clean_scores = {}
    for k in scores:
        if k not in clean_scores:
            clean_scores[k] = {}
        for el in scores[k]:
            for scenario in el:
                if scenario not in clean_scores[k]:
                    clean_scores[k][scenario] = {}
                for target in el[scenario]:
                    if target not in clean_scores[k][scenario]:
                        clean_scores[k][scenario][target] = []
                    clean_scores[k][scenario][target].append(el[scenario][target])
    print(json.dumps(clean_scores, indent=4))
        

def update_adm_run(collection, adm, probes):
    st_sid = requests.post(f'{ST_URL}api/v1/new_session?user_id=default_use').text.replace('"', "").strip()
    scenario = ''
    # send probes to server 
    for x in probes:
        requests.post(f'{ST_URL}api/v1/response', json={
            "response": {
                "choice": x['choice'],
                "justification": x["justification"],
                "probe_id": x['probe_id'],
                "scenario_id": x['scenario_id'],
            },
            "session_id": st_sid
        })
        scenario = x['scenario_id']
    adm['history'][-1]['parameters']['session_id'] = st_sid
    target = adm['history'][-1]['parameters']['target_id']
    alignment = requests.get(f'{ST_URL}api/v1/alignment/session?session_id={st_sid}&target_id={target}').json()
    kdmas = requests.get(f'{ST_URL}api/v1/computed_kdma_profile?session_id={st_sid}').json()
    adm['history'][-1]['response']['score'] = alignment.get('score')
    adm['history'][-1]['response']['kdma_values'] = kdmas
    collection.update_one({'_id': adm['_id']}, {"$set": {"history": adm['history']}})   
    to_return = {}
    to_return[scenario] = {}
    to_return[scenario][target] = alignment.get('score')
    return to_return
