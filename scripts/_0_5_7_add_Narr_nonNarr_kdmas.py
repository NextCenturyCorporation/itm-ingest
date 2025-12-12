import requests
from decouple import config

ADEPT_URL = config("ADEPT_URL")

edge_case_map = {
    'Probe 4-B.1-B.1-A': 'Response 4-B.1-B.1-A',
    'Probe 4-B.1-B.1-B': 'Response 4-B.1-B.1-B',
    'Response 3-B.2-A-gauze-v': 'Response 3-B.2-B-gauze-v',
    'Response 3-B.2-B-gauze-s' : 'Response 3-B.2-A-gauze-s'
}

def submit_responses(scenario_data, scenario_id, session_id, url_base):
    for field_name, field_value in scenario_data.items():
        if not isinstance(field_value, dict) or 'questions' not in field_value:
            continue
            
        for question_name, question in field_value['questions'].items():
            if not isinstance(question, dict) or not question.get('response') or 'Follow Up' in question_name:
                continue

            response_no_period = question['response'].replace('.', '')
            mapping = question['question_mapping'].get(response_no_period)
            if not mapping:
                continue
                
            response_url = f"{url_base}/api/v1/response"
            
            choices = mapping['choice'] if isinstance(mapping['choice'], list) else [mapping['choice']]
            for choice in choices:
                # fix to mj2 probes edge case
                if 'MJ2' in scenario_id:
                    choice = edge_case_map.get(choice, choice)
                response_payload = {
                    "response": {
                        "choice": choice,
                        "justification": "justification",
                        "probe_id": mapping['probe_id'],
                        "scenario_id": scenario_id,
                    },
                    "session_id": session_id
                }
                requests.post(response_url, json=response_payload)

def get_kdma_value(session_id, url):
    endpoint = '/api/v1/computed_kdma_profile'
    response = requests.get(f"{url}{endpoint}", params={"session_id": session_id})
    data = response.json()
    
    if isinstance(data, dict) and data.get('status') == 500:
        return None
    return data

def start_session(url):
    response = requests.post(f"{url}/api/v1/new_session")
    return response.text

def process_adept_scenario(doc):
    adept_scenario_map = {
        'phase1-adept-eval-MJ2': 'DryRunEval-MJ2-eval',
        'phase1-adept-eval-MJ4': 'DryRunEval-MJ4-eval',
        'phase1-adept-eval-MJ5': 'DryRunEval-MJ5-eval',
        'phase1-adept-train-MJ1': 'DryRunEval.MJ1',
        'phase1-adept-train-IO1': 'DryRunEval.IO1'
    }
    
    scenario_id = adept_scenario_map.get(doc['scenario_id'], doc['scenario_id'])
    
    session_id = start_session(ADEPT_URL)
    submit_responses(doc, scenario_id, session_id, ADEPT_URL)
    kdmas = get_kdma_value(session_id, ADEPT_URL)
    
    if kdmas is None:
        return None
        
    return {
        "session_id": session_id,
        "kdmas": kdmas
    }

def main(mongo_db, evalNumber= 4):
    text_based = mongo_db['userScenarioResults']
    
    query = {
        "evalNumber": {"$gte": evalNumber},
        "scenario_id": {"$regex": "DryRun|adept"}
    }
    
    total = text_based.count_documents(query)
    results = text_based.find(query)
    processed = 0
    errors = 0

    for doc in results:
        print(f"Document {processed}/{total}: PID: {doc['participantID']}, {doc['scenario_id']}")
        
        adept_results = process_adept_scenario(doc)
        if not adept_results:
            print(f"Error with document - skipping!")
            errors += 1
            processed += 1
            continue
            
        text_based.update_one(
            {"_id": doc["_id"]},
            {"$set": {
                "individual_kdma": adept_results["kdmas"],
                "individual_session_id": adept_results["session_id"]
            }}
        )
        
        processed += 1
        print(f"completed document {processed}")
    
    print(f"Total: {total}, Processed: {processed}, Errors: {errors}")