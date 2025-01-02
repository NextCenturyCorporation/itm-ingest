import requests
from decouple import config
import json

ST_URL = config("ST_URL")

stQOL = [
        "qol-human-8022671-SplitLowMulti-ph1",
        "qol-human-6403274-SplitHighBinary-ph1",
        "qol-human-3043871-SplitHighBinary-ph1",
        "qol-human-5032922-SplitLowMulti-ph1",
        "qol-human-0000001-SplitEvenMulti-ph1",
        "qol-human-7040555-SplitHighMulti-ph1",
        "qol-synth-LowExtreme-ph1",
        "qol-synth-HighExtreme-ph1",
        "qol-synth-HighCluster-ph1",
        "qol-synth-LowCluster-ph1"
    ]

def submit_responses(scenario_data, scenario_id, url, session_id):
    response_url = f"{url}/api/v1/response"
    
    # Iterate through each page in the scenario data
    for field_name, field_value in scenario_data.items():
        if not isinstance(field_value, dict) or 'questions' not in field_value:
            continue
            
        for question_name, question in field_value['questions'].items():
            if not isinstance(question, dict):
                continue
                
            if question.get('response') and not "Follow Up" in question_name:
                mapping = question['question_mapping'].get(question['response'])
                if not mapping:
                    continue
                    
                choices = mapping['choice'] if isinstance(mapping['choice'], list) else [mapping['choice']]
                
                for choice in choices:
                    response_payload = {
                        "response": {
                            "choice": choice,
                            "justification": "justification",
                            "probe_id": mapping['probe_id'],
                            "scenario_id": scenario_id,
                        },
                        "session_id": session_id
                    }
                    
                    try:
                        response = requests.post(response_url, json=response_payload)
                        response.raise_for_status()
                    except requests.exceptions.RequestException as e:
                        print(f"Error submitting response: {e}")
                        continue

def get_alignment_data(target_id, url, session_id):
    alignment_endpoint = '/api/v1/alignment/session'
    
    try:
        response = requests.get(
            f"{url}{alignment_endpoint}",
            params={
                "session_id": session_id,
                "target_id": target_id
            }
        )
        response.raise_for_status()
        
        result = response.json() if isinstance(response.json(), dict) else json.loads(
            response.text.replace('NaN', 'null')
        )
        
        return {
            "target": target_id,
            "score": result.get('score')
        }
    except requests.exceptions.RequestException as e:
        print(f"Error getting alignment data: {e}")
        return None

def get_most_least_aligned(session_id, scenario, url):
    endpoint = '/api/v1/get_ordered_alignment'
    targets = ['QualityOfLife'] if 'qol' in scenario['scenario_id'] else ['PerceivedQuantityOfLivesSaved']
    
    responses = []
    try:
        for target in targets:
            response = requests.get(
                f"{url}{endpoint}",
                params={
                    "session_id": session_id,
                    "kdma_id": target
                }
            )
            response.raise_for_status()
            
            filtered_data = [
                obj for obj in response.json()
                if not any(key.lower().find('-group-') != -1 for key in obj.keys())
            ]
            
            responses.append({
                'target': target,
                'response': filtered_data
            })
            
    except requests.exceptions.RequestException as e:
        print(f"Error getting ordered alignment: {e}")
        
    return responses

def get_kdma_value(session_id, url):
    endpoint = '/api/v1/computed_kdma_profile'
    try:
        response = requests.get(f"{url}{endpoint}", params={"session_id": session_id})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error getting KDMAs: {e}")
        return None

def main(mongo_db):
    text_results = mongo_db['userScenarioResults']
    
    # Get the specific entry we want to recalculate
    text_entry = text_results.find_one({
        'participantID': '202411369',
        'scenario_id': 'qol-ph1-eval-2'
    })
    
    if not text_entry:
        print("Entry not found")
        return
        
    session_endpoint = '/api/v1/new_session?user_id=default_user'
    try:
        response = requests.post(f'{ST_URL}{session_endpoint}')
        response.raise_for_status()
        soartech_sid = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error creating session: {e}")
        return

    submit_responses(text_entry, text_entry['scenario_id'], ST_URL, soartech_sid)
    
    alignment_data = []
    for target_id in stQOL:
        result = get_alignment_data(target_id, ST_URL, soartech_sid)
        if result:
            alignment_data.append(result)

    alignment_data.sort(key=lambda x: x['score'] if x['score'] is not None else float('-inf'), reverse=True)

    most_least_aligned = get_most_least_aligned(soartech_sid, text_entry, ST_URL)
    
    kdma_data = get_kdma_value(soartech_sid, ST_URL)
    
    update_data = {
        'alignmentData': alignment_data,
        'mostLeastAligned': most_least_aligned,
        'kdmas': kdma_data,
        'serverSessionId': soartech_sid
    }
    
    try:
        text_results.update_one(
            {'_id': text_entry['_id']},
            {'$set': update_data}
        )
        print("Successfully updated entry with new calculations")
    except Exception as e:
        print(f"Error updating database: {e}")