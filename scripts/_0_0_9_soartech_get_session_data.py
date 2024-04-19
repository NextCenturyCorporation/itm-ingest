from decouple import config
import requests, json
import pandas as pd
import os
from pandas import ExcelWriter
from pandas import json_normalize
from datetime import datetime
ST_URL = config('ST_URL')

def omnibus_history(omnibus):
    url = f"{ST_URL}/api/v1/new_session?user_id=default_user"
    start_session = requests.post(url)
    if start_session.status_code == 201:
        session_id = start_session.json()
        for scenario_id, probes in omnibus.items():
            for probe_id, choices in probes.items():
                if isinstance(choices, list):
                    #for choice_id in choices:
                    send_response(scenario_id, probe_id, choices[0], session_id)
                else:
                    send_response(scenario_id, probe_id, choices, session_id)
        return get_session_data(session_id)


def send_response(scenario_id, probe_id, choice_id, session_id):
    response_url = f"{ST_URL}/api/v1/response"
    response_payload = {
        "response": {
            "choice": choice_id,
            "justification": "justification",
            "probe_id": probe_id,
            "scenario_id": scenario_id,
        },
        "session_id": session_id
    }
    try:
        response = requests.post(response_url, json=response_payload)
        if response.status_code != 201:
            print(f"Failed to post response for probe ID {probe_id} choice ID {choice_id} scenario_id {scenario_id}. Status code: {response.status_code}")
    except requests.RequestException as e:
        print("ERROR: Network or request error occurred", e)

def get_session_data(session_id):
        session_data_url = f'{ST_URL}/api/v1/session-data?session_id={session_id}'
        response = requests.get(session_data_url)
        return response.json() if response.status_code == 200 else None

def run_delegation_dms():
    omnibus_a_collective_decisions = {
        'submarine-1': {
            'probe-1.1': 'choice-0',
            'probe-1.2': ['choice-0', 'choice-1'],
            'probe-2.2': ['choice-0', 'choice-1'],
            'probe-3.1': 'choice-2',
            'probe-3.2': 'choice-2'
        },
        'jungle-1': {
            'probe-5.1': 'choice-0',
            'probe-5.2': ['choice-0', 'choice-1'],
            'probe-5.3': 'choice-0',
            'probe-6.2': 'choice-0',
        },
        'desert-1': {
            'probe-1.1': 'choice-0',
            'probe-1.2': ['choice-0', 'choice-1'],
            'probe-1.3': 'choice-0',
            'probe-2.2': ['choice-0', 'choice-1'],
        },
        'urban-1': {
            'probe-5.1': 'choice-0',
            'probe-5.2': ['choice-0', 'choice-1'],
            'probe-5.3': 'choice-0',
            'probe-6.2': 'choice-0',
        }
    }

    omnibus_b_collective_decisions = {
        'submarine-1': {
            'probe-1.1': 'choice-3',
            'probe-1.2': 'choice-2',
            'probe-2.3': 'choice-1',
            'probe-3.1': 'choice-2',
            'probe-3.2': 'choice-1'
        },
        'jungle-1': {
            'probe-5.1': 'choice-3',
            'probe-5.2': 'choice-3',
            'probe-6.2': 'choice-2',
        },
        'desert-1': {
            'probe-1.1': 'choice-4',
            'probe-1.3': 'choice-2',
        },
        'urban-1': {
            'probe-5.1': 'choice-3',
            'probe-5.2': 'choice-3',
            'probe-6.2': 'choice-3',
        }
    }

    omnibus_a_history = omnibus_history(omnibus_a_collective_decisions)
    omnibus_b_history = omnibus_history(omnibus_b_collective_decisions)

    return [omnibus_a_history, omnibus_b_history]

def get_st_sessions_data(mongo_db):
    user_scenario_results_collection = mongo_db['userScenarioResults']
    user_scenario_results = user_scenario_results_collection.find({"title": {"$regex": "SoarTech", "$options": "i"}})
    history = []
    for result in user_scenario_results:
        session_id = result['serverSessionId']
        response = get_session_data(session_id)
        response.append('Participant ID: ' + result['participantID'])
        history.append(response)
    return history
        

def get_all_session_data(mongo_db):
    human_data = get_st_sessions_data(mongo_db)
    delegation_data = run_delegation_dms()

    print("Human Data ")
    print(json.dumps(human_data, indent=2))
    print('Delegation Data')
    print(json.dumps(delegation_data, indent=2))

    save_to_excel(human_data, delegation_data)

def save_to_excel(human_data, delegation_data):
    current_date = datetime.now().strftime("%Y-%m-%d")
    filename = f"{current_date}.xlsx"
    full_path = os.path.join('session-data-history', filename)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    human_df = pd.DataFrame(human_data)
    delegation_df = pd.DataFrame(delegation_data)

    with ExcelWriter(full_path) as writer:
        human_df.to_excel(writer, sheet_name='Human Data', index=False)
        delegation_df.to_excel(writer, sheet_name='Delegation Data', index=False)
