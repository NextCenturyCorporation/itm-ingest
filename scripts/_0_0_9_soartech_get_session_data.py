from decouple import config
import requests, json
import os

ST_URL = config('ST_URL')

def omnibus_history(omnibus):
    url = f"{ST_URL}/api/v1/new_session?user_id=default_user"
    start_session = requests.post(url)
    if start_session.status_code == 201:
        session_id = start_session.json()
        for scenario_id, probes in omnibus.items():
            for probe_id, choices in probes.items():
                if isinstance(choices, list):
                    send_response(scenario_id, probe_id, choices[0], session_id)
                else:
                    send_response(scenario_id, probe_id, choices, session_id)

        # Retrieve alignment information
        #high_alignment, low_alignment = get_alignment(session_id)

        # Retrieve session data
        session_data = get_session_data(session_id)

        # Ensure that alignment data is parsed from JSON
        #high_alignment_data = high_alignment.json() if high_alignment.status_code == 200 else {}
        #low_alignment_data = low_alignment.json() if low_alignment.status_code == 200 else {}

        # Append alignment data as a new dictionary at the end of the session_data list
        '''
        if isinstance(session_data, list):
            alignment_summary = {
                'high_alignment': high_alignment_data,
                'low_alignment': low_alignment_data
            }
            session_data.append(alignment_summary)  # Append the alignment data as a single dictionary at the end of the list
        '''

        return session_data




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

def get_alignment(session_id):
    high_url_alignment = f"{ST_URL}/api/v1/alignment/session?session_id={session_id}&target_id=maximization_high&population=false"
    low_url_alignment = f"{ST_URL}/api/v1/alignment/session?session_id={session_id}&target_id=maximization_low&population=false"
    high_response = requests.get(high_url_alignment)
    low_response = requests.get(low_url_alignment)
    return high_response, low_response

def get_session_data(session_id):
    session_data_url = f'{ST_URL}/api/v1/session-data?session_id={session_id}'
    response = requests.get(session_data_url)
    return response.json()

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
    omnibus_a_history.append({'Participant ID': 'ST High'})
    omnibus_b_history = omnibus_history(omnibus_b_collective_decisions)
    omnibus_b_history.append({'Participant ID': 'ST Low'})


    return [omnibus_a_history, omnibus_b_history]

def get_st_sessions_textbased_data(mongo_db):
    user_scenario_results_collection = mongo_db['userScenarioResults']
    user_scenario_results = user_scenario_results_collection.find({"title": {"$regex": "SoarTech", "$options": "i"}, "participantID": {"$regex": "^(2024|2021)", "$options": "i"}})
    history = []
    for result in user_scenario_results:
        session_id = result['serverSessionId']
        response = get_session_data(session_id)
        response.append({'Participant ID': result['participantID']})
        history.append(response)
    return history

def get_st_sim_data(mongo_db):
    user_sim_results_collection = mongo_db['humanSimulator']
    regex_query = {"_id": {"$regex": "st", "$options": "i"}} 
    user_sim_results = user_sim_results_collection.find(regex_query)
    history = []
    for result in user_sim_results:
        session_id = result['serverSessionId']
        response = get_session_data(session_id)
        response.append({'Participant ID': result['pid']})
        history.append(response)
    return history
        

def get_all_session_data(mongo_db):
    human_data = get_st_sessions_textbased_data(mongo_db)
    delegation_data = run_delegation_dms()
    human_sim_data = get_st_sim_data(mongo_db)
    
    # Determine the base directory path
    base_path = os.path.join(os.path.dirname(__file__), '../soartech-history')
    
    # Paths for the subdirectories
    human_data_path = os.path.join(base_path, 'human_data')
    delegation_data_path = os.path.join(base_path, 'delegation_data')
    
    # Create directories if they do not exist
    os.makedirs(human_data_path, exist_ok=True)
    os.makedirs(delegation_data_path, exist_ok=True)
    
    # Function to generate unique file path
    def generate_unique_path(directory, file_name):
        base_name, ext = os.path.splitext(file_name)
        counter = 1
        new_file_path = os.path.join(directory, file_name)
        while os.path.exists(new_file_path):
            new_file_path = os.path.join(directory, f"{base_name}_{counter}{ext}")
            counter += 1
        return new_file_path

    # Write human_data to JSON files using Participant ID as the file name
    for entry_list in human_data:
        if isinstance(entry_list, list) and entry_list:
            participant_id = entry_list[-1].get('Participant ID', 'Unknown_Participant')  # Assumes last element is a dict
            file_name = f'{participant_id}.json'
            file_path = generate_unique_path(human_data_path, file_name)
            with open(file_path, 'w') as file:
                json.dump(entry_list, file, indent=2)  # Writing the entire list
    
    for entry_list in human_sim_data:
        if isinstance(entry_list, list) and entry_list:
            participant_id = entry_list[-1].get('Participant ID', 'Unknown_Participant')  # Assumes last element is a dict
            file_name = f'{participant_id}.json'
            file_path = generate_unique_path(human_data_path, file_name)
            with open(file_path, 'w') as file:
                json.dump(entry_list, file, indent=2)  # Writing the entire list
    
    # Write delegation_data to JSON files using Participant ID as the file name
    for entry_list in delegation_data:
        if isinstance(entry_list, list) and entry_list:
            participant_id = entry_list[-1].get('Participant ID', 'Unknown_Participant')  # Assumes last element is a dict
            file_name = f'{participant_id}.json'
            file_path = generate_unique_path(delegation_data_path, file_name)
            with open(file_path, 'w') as file:
                json.dump(entry_list, file, indent=2)  # Writing the entire list

    print(f"Data has been saved in '{base_path}' directory.")