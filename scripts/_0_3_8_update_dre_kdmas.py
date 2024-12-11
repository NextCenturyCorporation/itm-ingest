import requests
from decouple import config 
ST_URL = config("ST_DRE_SCALAR_URL")
UPDATE_DATABASE = True # Update the mongo database tables for text, sim, and adm
VERBOSE_OUTPUT = True # If True, displays scalar KDMA values for each entry
DISPLAY_CSV = False # If True, writes csv-like output for text and sim kdma data
txt_and_sim_data = {}

"""
    For text scenarios, human sim output, and ADM runs for Evaluation 4 (DRE):
      Look for only SoarTech sessions
      Get probe responses
      Create TA1 session
      Send probes to modified SoarTech server (exp/scalar-kdma branch)
      Call computed_kdma_profile to get scalar KDMA values
      If enabled, update database with new kdma scalar value
    If enabled, print csv-like output for text and sim kdma data:  PID, Text-QOL, Text-VOL, Sim-QOL, Sim-VOL
"""
def main(mongo_db):
    """
    Update DRE SoarTech Text, Sim, and ADM KDMA values with a scalar value.
    """

    print("Processing SoarTech Text KDMAs...")
    update_text_kdmas(mongo_db)
    if VERBOSE_OUTPUT:
        print("-----")
    print("Processing SoarTech Sim KDMAs...")
    update_sim_kdmas(mongo_db)
    if VERBOSE_OUTPUT:
        print("-----")
    print("Processing SoarTech ADM KDMAs...")
    update_adm_kdmas(mongo_db)

    if DISPLAY_CSV:
        if VERBOSE_OUTPUT:
            print("-----")
        # Supplement with some manually added kdmas derived from YAML files.
        txt_and_sim_data['202409111']['SIM_PerceivedQuantityOfLivesSaved'] = 0.62
        txt_and_sim_data['202409112'] = {'SIM_QualityOfLife': 0.3909090909, 'SIM_PerceivedQuantityOfLivesSaved': 0.53636363636}
        print("CSV-style output:")
        print("PID,Text-QOL,Text-VOL,Sim-QOL,Sim-VOL")
        for row in txt_and_sim_data:
            print(f"{row}, {txt_and_sim_data[row].get('TXT_QualityOfLife', 'n/a')}, {txt_and_sim_data[row].get('TXT_PerceivedQuantityOfLivesSaved', 'n/a')}, {txt_and_sim_data[row].get('SIM_QualityOfLife', 'n/a')}, {txt_and_sim_data[row].get('SIM_PerceivedQuantityOfLivesSaved', 'n/a')}")

    print("Done.")


def update_text_kdmas(mongoDB):
    text_scenario_collection = mongoDB['userScenarioResults']
    text_scenario_to_update = text_scenario_collection.find({"evalNumber": 4})
    for entry in text_scenario_to_update:
        scenario_id = entry.get('scenario_id')
        data_id = entry.get('_id')
        pid = entry.get('participantID')

        # Get SoarTech QOL and VOL probe responses
        if ('qol-dre' in scenario_id or 'vol-dre' in scenario_id):
            probes = []
            for k in entry:
                if isinstance(entry[k], dict) and 'questions' in entry[k]:
                    if 'probe ' + k in entry[k]['questions'] and 'response' in entry[k]['questions']['probe ' + k] and 'question_mapping' in entry[k]['questions']['probe ' + k]:
                        response = entry[k]['questions']['probe ' + k]['response'].replace('.', '')
                        mapping = entry[k]['questions']['probe ' + k]['question_mapping']
                        if response in mapping:
                            probes.append({'probe': {'choice': mapping[response]['choice'], 'probe_id': mapping[response]['probe_id']}})
                        else:
                            print('Could not find response in mapping!', response, list(mapping.keys()))
            session_id = requests.post(f'{ST_URL}api/v1/new_session').text.replace('"', '').strip()
            send_probes(f'{ST_URL}api/v1/response', probes, session_id, scenario_id)
            kdmas = requests.get(f'{ST_URL}api/v1/computed_kdma_profile?session_id={session_id}').json()
            if kdmas.get('computed_kdma_profile'):
                profile = kdmas['computed_kdma_profile'][0]
                kdma_name = profile['kdma']
                value = profile['value']
                if VERBOSE_OUTPUT:
                    print(f'PID={pid}, KDMA = {kdma_name}, value = {value}')
                if DISPLAY_CSV:
                    if txt_and_sim_data.get(pid):
                        txt_and_sim_data.get(pid)['TXT_' + kdma_name] = value
                    else:
                        txt_and_sim_data[pid] = {'TXT_' + kdma_name: value}
                if UPDATE_DATABASE:
                    entry['kdmas']['computed_kdma_profile'][0]['value'] = value
                    entry['kdmas']['computed_kdma_profile'][0]['scores'] = profile['scores']
                    text_scenario_collection.update_one({'_id': data_id}, {"$set": {"kdmas": entry['kdmas']}})
            else:
                print(f'No profile for PID={pid}, Scenario={scenario_id}')
                if VERBOSE_OUTPUT:
                    print("  TXT PROBES: " + str(probes))


def update_sim_kdmas(mongoDB):
    sim_scenario_collection = mongoDB['humanSimulator']
    sim_scenario_to_update = sim_scenario_collection.find({"evalNumber": 4})
    for entry in sim_scenario_to_update:
        scenario_id = entry.get('scenario_id')
        data_id = entry.get('_id')
        pid = entry.get('pid')
        data = entry.get('data').get('data')

        # Get SoarTech QOL and VOL probe responses
        if ('qol-dre' in scenario_id or 'vol-dre' in scenario_id):
            probes = []
            for k in data:
                if isinstance(k, dict) and k['found_match']:
                    probes.append({'probe': {'choice': k['probe']['choice'], 'probe_id': k['probe']['probe_id']}})
                else:
                    print('Skipping data with no found match.')
            session_id = requests.post(f'{ST_URL}api/v1/new_session').text.replace('"', '').strip()
            send_probes(f'{ST_URL}api/v1/response', probes, session_id, scenario_id)
            kdmas = requests.get(f'{ST_URL}api/v1/computed_kdma_profile?session_id={session_id}').json()
            if kdmas.get('computed_kdma_profile'):
                profile = kdmas['computed_kdma_profile'][0]
                kdma_name = profile['kdma']
                value = profile['value']
                if VERBOSE_OUTPUT:
                    print(f'PID={pid}, KDMA = {kdma_name}, value = {value}')
                if DISPLAY_CSV:
                    if txt_and_sim_data.get(pid):
                        txt_and_sim_data[pid]['SIM_' + kdma_name] = value
                    else:
                        txt_and_sim_data[pid] = {'SIM_' + kdma_name: value}
                if UPDATE_DATABASE:
                    entry['data']['alignment']['kdmas']['computed_kdma_profile'][0]['value'] = value
                    entry['data']['alignment']['kdmas']['computed_kdma_profile'][0]['scores'] = profile['scores']
                    sim_scenario_collection.update_one({'_id': data_id}, {"$set": {"data": entry['data']}})
            else:
                print(f'No profile for PID={pid}, Scenario={scenario_id}')
                if VERBOSE_OUTPUT:
                    print("  SIM PROBES: " + str(probes))
                if UPDATE_DATABASE:
                    print('->  Updating with manual data.')
                    # Supplement with some manually added kdmas derived from YAML files.
                    if pid == '202409111':
                        entry['data']['alignment']['kdmas']['computed_kdma_profile'][0]['value'] = 0.62
                    elif pid == '202409112':
                        if 'vol' in scenario_id:
                            entry['data']['alignment']['kdmas']['computed_kdma_profile'][0]['value'] = 0.53636363636
                        else:
                            entry['data']['alignment']['kdmas']['computed_kdma_profile'][0]['value'] = 0.3909090909
                    else:
                        print('->  Unexpected missing profile data; no scalar kdma added.')
                    sim_scenario_collection.update_one({'_id': data_id}, {"$set": {"data": entry['data']}})


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


def update_adm_kdmas(mongoDB):
    adm_collection = mongoDB["test"]
    adms_to_update = adm_collection.find({"evalNumber": 4})

    for adm in adms_to_update:
        # Get ADM name
        adm_name = adm['history'][0].get('parameters', {}).get('adm_name', None)
        if adm_name is None:
            adm_name = adm['history'][1].get('parameters', {}).get('adm_name', None)
        if adm_name is None:
            print(f"Could not get adm name for {adm['_id']}; skipping.")
            continue

        # Get new ADM session
        probe_responses = []
        skip_adm = False
        # Get SoarTech QOL and VOL probe responses
        for x in adm['history']:
            if x['command'] == 'Respond to TA1 Probe':
                if any(substring in x['parameters']['scenario_id'] for substring in ["vol", "qol"]):
                    probe_responses.append(x['parameters'])
                else:
                    # Not a SoarTech scenario, so skip
                    skip_adm = True
                    break
        if not skip_adm:
            # Get scalar kdma scores and optionally store in DB
            update_adm_run(adm_collection, adm, adm_name, probe_responses)


def update_adm_run(collection, adm, adm_name, probes):
    session_id = requests.post(f'{ST_URL}api/v1/new_session?user_id=default_use').text.replace('"', "").strip()
    # Send probes to TA1 server
    for probe in probes:
        requests.post(f'{ST_URL}api/v1/response', json={
            "response": {
                "choice": probe['choice'],
                "justification": probe["justification"],
                "probe_id": probe['probe_id'],
                "scenario_id": probe['scenario_id'],
            },
            "session_id": session_id
        })
    kdmas = requests.get(f'{ST_URL}api/v1/computed_kdma_profile?session_id={session_id}').json()
    if kdmas.get('computed_kdma_profile'):
        profile = kdmas['computed_kdma_profile'][0]
        kdma_name = profile['kdma']
        value = profile['value']
        if VERBOSE_OUTPUT:
            print(f"ADM ID={adm['_id']}, ADM name = {adm_name}, KDMA = {kdma_name}, value = {value}")
        if UPDATE_DATABASE:
            adm['history'][-1]['response']['kdma_values'][0]['value'] = value
            adm['history'][-1]['response']['kdma_values'][0]['scores'] = profile['scores']
            collection.update_one({'_id': adm['_id']}, {"$set": {"history": adm['history']}})
    else:
        print(f"No profile for ADM ID={adm['_id']}, ADM name={adm_name}")
