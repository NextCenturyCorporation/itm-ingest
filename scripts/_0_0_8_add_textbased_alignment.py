import os, json, requests
from decouple import config
# Constants
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'metrics-textbased-configs')
ADEPT_URL = config('ADEPT_URL')
ST_URL = config('ST_URL')
def load_scenario_config(scenario_name):
    """ Load JSON configuration for a given scenario name """
    config_file = f"{CONFIG_PATH}/{scenario_name}Config.json"
    try:
        with open(config_file, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"Configuration file not found: {config_file}")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON from the file: {config_file}")
        return None
    
scenarioMappings = {
    "SoarTech Jungle": load_scenario_config('stJungle'),
    "SoarTech Urban": load_scenario_config('stUrban'),
    "SoarTech Desert": load_scenario_config('stDesert'),
    "SoarTech Submarine": load_scenario_config('stSub'),
    "Adept Jungle": load_scenario_config('adeptJungle'),
    "Adept Urban": load_scenario_config('adeptUrban'),
    "Adept Desert": load_scenario_config('adeptDesert'),
    "Adept Submarine": load_scenario_config('adeptSub')
}

scenarioNameToID = {
    "Adept Submarine": "MetricsEval.MD6-Submarine",
    "Adept Desert": "MetricsEval.MD5-Desert",
    "Adept Urban": "MetricsEval.MD1-Urban",
    "Adept Jungle": "MetricsEval.MD4-Jungle",
    "SoarTech Urban": "urban-1",
    "SoarTech Submarine": "submarine-1",
    "SoarTech Desert": "desert-1",
    "SoarTech Jungle": "jungle-1"
}

def map_answers(scenario, scenario_mappings):
    if not scenario.get('participantID'):
        return
    scenario_title = scenario['title'].replace(' Scenario', '')
    scenario_config = scenario_mappings.get(scenario_title)
    if scenario_config is None:
        return
    for field_name, field_value in scenario.items():
        if field_value and isinstance(field_value, dict) and 'questions' in field_value:
            for question_name, question in field_value['questions'].items():
                if question and isinstance(question, dict) and 'probe' in question:
                    page = next((p for p in scenario_config['pages'] if p['name'] == field_name), None)
                    if page:
                        page_question = next((e for e in page['elements'] if e['name'] == question_name), None)
                        if page_question:
                            try:
                                index_of_answer = page_question['choices'].index(question['response'])
                                if scenario_title.startswith("Adept"):
                                    choice = f"{question['probe']}.{chr(65 + index_of_answer)}"
                                else:
                                    choice = f"choice-{index_of_answer}"
                                question['choice'] = choice
                            except ValueError:
                                continue


def add_probe_ids(scenario, scenario_mappings):
    if not scenario.get('participantID'):
        return
    scenario_title = scenario['title'].replace(' Scenario', '')
    scenario_config = scenario_mappings.get(scenario_title)
    if scenario_config is None:
        return
    for field_name, field_value in scenario.items():
        if field_value and isinstance(field_value, dict) and 'questions' in field_value:
            for question_name, question in field_value['questions'].items():
                if question and 'response' in question and "Follow Up" not in question_name:
                    page = next((p for p in scenario_config['pages'] if p['name'] == field_name), None)
                    if page:
                        page_question = next((e for e in page['elements'] if e['name'] == question_name), None)
                        if page_question:
                            question['probe'] = page_question['probe']


def submit_responses(scenario_results, scenario_id, url_base, session_id):
    responses = []
    if not isinstance(scenario_results, dict):
        return response_promises

    for field_name, field_value in scenario_results.items():
        # Ensure that field_value is a dictionary and has 'questions'
        if not isinstance(field_value, dict) or 'questions' not in field_value:
            continue

        for question_name, question in field_value['questions'].items():
            # Check that question is a dictionary
            if not isinstance(question, dict):
                continue

            # Check for required keys and that 'Follow Up' is not part of the question name
            if question.get('response') and "Follow Up" not in question_name and question.get('probe') and question.get('choice'):
                problem_probe = is_problem_probe(question, scenario_results.get('title'))
                if problem_probe:
                    if not fix_problem_probe(question, problem_probe):
                        continue
                # Construct the response URL and payload
                response_url = f"{url_base}/api/v1/response"
                response_payload = {
                    "response": {
                        "choice": question["choice"],
                        "justification": "justification",
                        "probe_id": question["probe"],
                        "scenario_id": scenario_id,
                    },
                    "session_id": session_id
                }

                try:
                    response = requests.post(response_url, json=response_payload)
                    responses.append(response)
                except requests.RequestException as e:
                    print(f"Failed to send response for {question_name}: {e}")      
    return responses


def get_alignment_data(url_base, session_id, target_id):
    url_alignment = f"{url_base}/api/v1/alignment/session?session_id={session_id}&target_id={target_id}&population=false"
    response = requests.get(url_alignment)
    return response.json() if response.status_code == 200 else None

def get_adept_alignment(scenario_results, scenario_id):
    url = f"{ADEPT_URL}/api/v1/new_session"
    start_session = requests.post(url)
    if start_session.status_code == 200:
        session_id = start_session.json()
        responses = submit_responses(scenario_results, scenario_id, ADEPT_URL, session_id)
        alignment_data = get_alignment_data(ADEPT_URL, session_id, 'ADEPT-metrics_eval-alignment-target-train-HIGH')
        scenario_results['alignmentData'] = alignment_data
        scenario_results['serverSessionId'] = session_id
        print(alignment_data)

def get_soartech_alignment(scenario_results, scenario_id):
    url = f"{ST_URL}/api/v1/new_session?user_id=default_user"
    start_session = requests.post(url)
    if start_session.status_code == 201:
        session_id = start_session.json()
        responses = submit_responses(scenario_results, scenario_id, ST_URL, session_id)
        alignment_data = get_alignment_data(ST_URL, session_id, 'maximization_high')
        scenario_results['alignmentData'] = alignment_data if alignment_data else None
        scenario_results['serverSessionId'] = session_id
        print(scenario_results['alignmentData'])

def load_problem_probes():
    problem_probes_file = os.path.join(CONFIG_PATH, 'problemProbes.json')
    try:
        with open(problem_probes_file, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"Problem probes configuration file not found: {problem_probes_file}")
        return {}
    except json.JSONDecodeError:
        print(f"Error decoding JSON from the file: {problem_probes_file}")
        return {}


def is_problem_probe(question, scenario_title):
    # Check if a probe is a known problem probe and get the mapping if it is.
    # problem probe mappings
    problem_probe_mappings = load_problem_probes()
    # problem probes specific to this scenario
    scenario_problem_probes = problem_probe_mappings.get(scenario_title, {})
    probe_key = question.get('probe')

    return scenario_problem_probes.get(probe_key)

def fix_problem_probe(question, mapping):
    # tries to map user choice on problem probe to valid choice id if possible
    mapped_choice = mapping.get(question['choice'])
    if mapped_choice:
        question['choice'] = mapped_choice
        return True
    return False

def add_textbased_alignments(mongo_db):
    user_scenario_results_collection = mongo_db['userScenarioResults']
    user_scenario_results = user_scenario_results_collection.find({})

    for result in user_scenario_results:
        if not result.get('participantID'):
            continue
        # attach probeID's to results
        add_probe_ids(result, scenarioMappings)
        # attach choiceID's to results
        map_answers(result, scenarioMappings)

        if "Adept" in result.get('title'):
            get_adept_alignment(result, scenarioNameToID.get(result.get('title')))
        elif "SoarTech" in result.get('title'):
            get_soartech_alignment(result, scenarioNameToID.get(result.get('title')))
        else:
            print("Error: unrecognized scenario title")

        user_scenario_results_collection.update_one(
            {'_id': result['_id']},
            {'$set': result}
        )


