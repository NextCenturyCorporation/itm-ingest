import yaml, argparse, json, os, csv, requests
from logger import LogLevel, Logger
from pymongo import MongoClient
from datetime import datetime
from decouple import config
from typing import Tuple
from dateutil import parser as dateparser

SEND_TO_MONGO = True # send all raw and calculated data to the mongo db if true
CALC_KDMAS = True # send data to servers to calculate KDMA values if true
RUN_ALL = True  # run all files in the input directory, even if they have already been run/analyzed, if true
RERUN_SESSIONS = False # rerun sessions only to get new session ids
EVAL_NUM = 8
EVAL_NAME = 'June 2025 Collaboration'
EVAL_PREFIX = 'june2025'
VERBOSE = False


ADEPT_URL = config("ADEPT_URL")

SCENE_MAP = {
    "June 2025 OW Desert": f"{EVAL_PREFIX}-desert-openworld.yaml",
    "June 2025 OW Urban": f"{EVAL_PREFIX}-urban-openworld.yaml"
}

KDMA_MAP = {
    'affiliation': 'AF',
    'merit': 'MF',
    'personal_safety': 'PS',
    'search': 'SS'
}

ACTION_TRANSLATION = {
    "TREAT_PATIENT": "Treatment",
    'END_SCENE': 'Wait',
    "SEARCH": "Search"
}

mongo_collection_matches = None
mongo_collection_raw = None
participant_log_collection = None
text_scenario_collection = None
ENVIRONMENTS_BY_PID = {} # Currently unused


class ProbeMatcher:
    logger = Logger("probeMatcher")
    ow_yaml = None
    json_filename = None
    json_data = None
    output_ow = None
    participantId = ''
    environment = ''
    csv_file = None
    timestamp = None
    analyze = True
    pid_in_log = False


    def __init__(self, json_path):
        '''
        Load in the file and parse the yaml
        '''
        # Get environment from json to choose correct desert/urban yamls
        with open(json_path, 'r', encoding='utf-8') as json_file:
            self.json_data = json.load(json_file)
            self.json_filename = json_file.name
        if (self.json_data['configData']['teleportPointOverride'] == 'Tutorial'):
            self.logger.log(LogLevel.CRITICAL_INFO, "Tutorial level, not processing data")
            return
        if (len(self.json_data['actionList']) <= 1):
            self.logger.log(LogLevel.WARN, "No actions taken")
            return

        str_time = self.json_data['actionList'][0]['timestamp']
        try:
            self.timestamp = datetime.strptime(str_time, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()*1000
        except:
            self.logger.log(LogLevel.WARN, f"Could not convert {str_time} to timestamp. Please check that your json file is a valid format. Continuing anyways...")
            self.timestamp = None

        pid = self.json_data['participantId']
        pid = pid if pid != '' else self.json_data['sessionId']
        self.participantId = pid
        self.pid_in_log = participant_log_collection.count_documents({"ParticipantID": int(pid)}) > 0
        env = SCENE_MAP.get(self.json_data["configData"]["narrative"]["narrativeDescription"], '')
        if env == '':
            self.logger.log(LogLevel.WARN, f'Skipping narrative {self.json_data["configData"]["narrative"]["narrativeDescription"]}.')
            return
        self.environment = env
        if EVAL_PREFIX not in self.environment:
            self.logger.log(LogLevel.INFO, f"Skipping file that is not a June 2025 Open World scenario.")
            return
        print(f'Environment: {self.environment}')

        if pid in ENVIRONMENTS_BY_PID:
            ENVIRONMENTS_BY_PID[pid].append(self.environment)
        else:
            ENVIRONMENTS_BY_PID[pid] = [self.environment]
        # Create output files
        try:
            os.makedirs(f'output_{EVAL_PREFIX}', exist_ok=True)
        except:
            self.logger.log(LogLevel.ERROR, f"Could not create output directory {f'output_{EVAL_PREFIX}'}.")

        filename = os.path.join(f'output_{EVAL_PREFIX}', env.split('.yaml')[0] + f'{pid}.json')
        if VERBOSE:
            print(f"This is where we would determine if we should run {filename}.")
        #if not self.should_file_run(filename):
        #    return
        if VERBOSE:
            print(f"Create output file {filename}.")
        self.output_ow = open(filename, 'w', encoding='utf-8')
        try:
            # Get yaml file
            yaml_filename = os.path.join(os.path.join('phase2', EVAL_PREFIX), env)
            if VERBOSE:
                print(f"Opening {yaml_filename}.")
            ow_file = open(yaml_filename, 'r', encoding='utf-8')
            if VERBOSE:
                print(f"Loading {yaml_filename}.")
            self.ow_yaml = yaml.load(ow_file, Loader=yaml.CLoader)
        except Exception as e:
            self.logger.log(LogLevel.ERROR, "Error while loading in open world yaml file. Please ensure the file is a valid yaml format and try again.\n\n" + str(e) + "\n")
        if (ow_file):
            ow_file.close()
        self.clean_json()

    def __del__(self):
        '''
        Basic cleanup: closing the output file
        '''
        self.logger.log(LogLevel.DEBUG, "Program closing...")
        if (self.output_ow):
            self.output_ow.close()


    """
    I don't *think* we're going to need this for phase 2.  There's no 'alignment'.  But *maybe* we'd want this
    for recalculating the KDMAs for the OW scenario.  So keeping this here as a starting point for that.
    """
    def should_file_run(self, filename):
        '''
        If RUN_ALL is False, looks to see if the input file already has a matching output file. If it does and:
            1. We are not calculating KDMAs OR
            2. We are calculating KDMAs but KDMAs have already been calculated for this file
        then return False in order to skip the analysis of this file.
        '''
        run_this_file = True
        mongo_id =  self.participantId + f'_{EVAL_PREFIX}_open_world'
        found = list(mongo_collection_matches.find({'_id': mongo_id}))
        if not RUN_ALL and ((SEND_TO_MONGO and len(found) > 0 and os.path.exists(filename)) or (not SEND_TO_MONGO and os.path.exists(filename))):
            if RERUN_SESSIONS:
                return run_this_file
            if not CALC_KDMAS:
                run_this_file = False
            if CALC_KDMAS:
                if not SEND_TO_MONGO:
                    f = open(filename, 'r', encoding='utf-8')
                    data = json.load(f)
                    if len(list(data.get('alignment', {}).keys())) > 1 and 'sid' in data.get('alignment', {}):
                        run_this_file = False
                else:
                    if len(list(found[0].get('data', {}).get('alignment', {}).keys())) > 1 and 'sid' in found[0].get('data', {}).get('alignment', {}):
                        run_this_file = False
        if not run_this_file:
            self.logger.log(LogLevel.CRITICAL_INFO, "File has already been analyzed, skipping analysis...")
            self.analyze = False
        return run_this_file


    def clean_json(self):
        '''
        Cleans the json file from close-by duplicate breathing/pulse checks
        '''
        actions = self.json_data['actionList']
        new_actions = []
        for i in range(len(actions)-1):
            if actions[i]['actionType'] in ['Breathing', 'Pulse']:
                if actions[i+1]['actionType'] == actions[i]['actionType'] and actions[i+1]['casualty'] == actions[i]['casualty']:
                    continue
                else:
                    new_actions.append(actions[i])
            else:
                new_actions.append(actions[i])
        new_actions.append(actions[len(actions)-1])
        self.json_data['actionList'] = new_actions


    def match_probes(self):
        if EVAL_PREFIX in self.environment:
            env = 'Desert' if 'desert' in self.environment else 'Urban' if 'urban' in self.environment else None
            if not env:
                self.logger.log(LogLevel.WARN, f"Skipping unknown environment {env}")
                return
            self.match_ow_probes(env) # disable probe matching for now, as this isn't yet implemented for june2025
            self.analyze_openworld(env)
        else:
            self.logger.log(LogLevel.WARN, f"No function available to probe match for environment {self.environment}")


    def analyze_openworld(self, env: str):

        results = {
            'pid': self.participantId,
            f'{env}_assess_patient': 0,
            f'{env}_assess_total': 0,
            f'{env}_treat_patient': 0,
            f'{env}_treat_total': 0,
            f'{env}_triage_time': 0,
            f'{env}_triage_time_patient': 0,
            f'{env}_engage_patient': 0,
            f'{env}_tag_acc': 0,
            f'{env}_tag_expectant': False
        }

        ow_csv = open(self.json_filename.replace('.json', '.csv'), 'r', encoding='utf-8')
        reader = csv.reader(ow_csv)
        header = next(reader)
        data = []
        for line in reader:
            data.append(line)
        if ow_csv:
            ow_csv.close()

        def timestamp_to_milliseconds(timestamp):
            return datetime.fromisoformat(str(dateparser.parse(timestamp))).timestamp()

        def find_patients_engaged():
            '''
            returns the number of patients engaged and the number of patients treated during the scenario.
            also counts the number of times each patient was engaged
            '''
            engagement_order = []
            treated = []
            for x in data:
                if x[0] in ['TOOL_APPLIED', 'TAG_APPLIED', 'SP_O2_TAKEN', 'BREATHING_CHECKED', 'PULSE_TAKEN']:
                    engagement_order.append(x[header.index('PatientID')].split(' Root')[0])
                    if x[0] == 'TOOL_APPLIED':
                        treated.append(x[header.index('PatientID')].split(' Root')[0])
            # remove in-order duplicates from list
            simple_order = []
            for x in engagement_order:
                if len(simple_order) > 0 and x == simple_order[-1]:
                    continue
                simple_order.append(x)
            return {'engaged': len(list(set(engagement_order))), 'treated': len(list(set(treated))), 'order': simple_order}

        engaged_counts = find_patients_engaged()
        patients_engaged = engaged_counts['engaged']
        patients_treated = engaged_counts['treated']
        patient_order_engaged = engaged_counts['order']
        engagement_times = list({item: patient_order_engaged.count(item) for item in set(patient_order_engaged)}.values())
        results[f'{env}_engage_patient'] = sum(engagement_times) / max(1, len(engagement_times))


        def count_assessment_actions():
            '''returns the total count of assessment actions during the scenario'''
            assessment_actions = ['SP_O2_TAKEN', 'BREATHING_CHECKED', 'PULSE_TAKEN']
            count = 0
            last_done = {}
            per_patient = {}
            for x in data:
                # only count actions that are more than 5 seconds apart from the last of the same type of action
                if x[0] in assessment_actions:
                    if (x[0] not in last_done or (timestamp_to_milliseconds(x[2]) - last_done[x[0]]) > 5):
                        last_done[x[0]] = timestamp_to_milliseconds(x[2])
                        count += 1
                        patient = x[header.index('PatientID')].split(' Root')[0]
                        if patient not in per_patient:
                            #if VERBOSE:
                            #    print(f"Adding patient {patient} to assessments")
                            per_patient[patient] = 0
                        per_patient[patient] += 1
            return {'count': count, 'per_patient': per_patient}

        assessments = count_assessment_actions()
        if VERBOSE:
            print(f"Assessments: {assessments}")
        results[f'{env}_assess_total'] = assessments['count']
        results[f'{env}_assess_patient'] = results[f'{env}_assess_total'] / max(1, patients_engaged)

        def count_treatment_actions():
            '''returns the total count of treatment actions during the scenario'''
            count = 0
            per_patient = {}
            for x in data:
                if x[0] == 'TOOL_APPLIED' and 'Pulse Oximeter' not in x:
                    count += 1
                    patient = x[header.index('PatientID')].split(' Root')[0]
                    if patient not in per_patient:
                        per_patient[patient] = 0
                    per_patient[patient] += 1
            return {'count': count, 'per_patient': per_patient}

        treatments = count_treatment_actions()
        results[f'{env}_treat_total'] = treatments['count']
        results[f'{env}_treat_patient'] = results[f'{env}_treat_total'] / max(1, patients_treated)

        def get_triage_time():
            '''gets the time from start to finish (in seconds) to complete the scenario'''
            if len(data) > 0:
                start = float(data[0][1])
                end = float(data[len(data)-2][1])
                return ((end-start))/1000

        results[f'{env}_triage_time'] = get_triage_time()

        def get_tags():
            if env == 'Desert':
                tags = {
                    'US Military 1': 'gray',
                    'Civilian 1': 'red',
                    'Attacker 1': 'yellow_orange',
                    'US Military 2': 'red',
                    'Civilian 2': 'red',
                    'Attacker 2': 'yellow_orange',
                    'Civilian 3': 'yellow_orange',
                    'US Military 3': 'red',
                    'US Military 4': 'green'
                }
            elif env == 'Urban':
                tags = {
                    'US Military 1': 'yellow_orange',
                    'US Military 2': 'red',
                    'Civilian 1': 'green',
                    'Shooter 1': 'yellow_orange',
                    'US Military 3': 'yellow_orange',
                    'Civilian 2': 'gray',
                    'Civilian 3': 'red',
                    'US Military 4': 'red'
                }

            # by default gets the last tag applied to each patient
            tags_applied = {}
            for x in data:
                if x[0] == 'TAG_APPLIED':
                    tags_applied[x[header.index('PatientID')].split(' Root')[0]] = x[header.index('TagType')]
            correct = 0
            count = 0
            for x in tags_applied:
                if tags[x] == tags_applied[x]:
                    correct += 1
                count += 1
            return {'correct': correct, 'count': count, 'tags': tags_applied}

        tag_counts = get_tags()
        results[f'{env}_tag_acc'] = tag_counts['correct'] / tag_counts['count']
        results[f'{env}_tag_expectant'] = 'Yes' if tag_counts['tags'].get('US Soldier 3') == 'gray' else 'No'

        def find_time_per_patient():
            '''
            Looks through each participant's interaction with each patient
            to see how much time total the engagement took
            '''
            interactions = {}
            cur_p = None
            start_time = 0
            last_time = 0
            for x in data:
                # find every interaction with the patient
                p = None
                t = float(x[1])
                if x[0] in ['TOOL_APPLIED', 'TAG_APPLIED', 'SP_O2_TAKEN', 'BREATHING_CHECKED', 'PULSE_TAKEN']:
                    p = x[header.index('PatientID')].split(' Root')[0]
                if p is None or 'Level Core' in p or 'Simulation' in p or 'Player' in p:
                    continue
                if p not in interactions:
                    interactions[p] = []
                # iniitalize cur_p
                if cur_p is None:
                    cur_p = p
                    start_time = last_time if last_time != 0 else t
                # new patient interaction!
                if cur_p != p:
                    # save start/end interaction times for previous patient
                    if start_time != last_time:
                        interactions[cur_p].append((start_time, last_time))
                    elif len(interactions[cur_p]) == 0:
                        interactions[cur_p].append((start_time, t))
                    # set start time for new patient
                    start_time = t
                    last_time = t
                    cur_p = p
                else:
                    last_time = t
            # save the last interaction set!
            interactions[cur_p].append((start_time, last_time))

            total_time = 0
            for p in interactions:
                patient_time = 0
                for x in interactions[p]:
                    patient_time += x[1] - x[0]
                total_time += patient_time
                interactions[p] = patient_time/1000

            return {'interactions': interactions, 'total': total_time/1000}

        triage_times = find_time_per_patient()
        results[f'{env}_triage_time_patient'] = triage_times['total'] / max(1, patients_engaged)

        def get_evaced_patients():
            answers = []
            if env == 'Desert':
                answer_map = {
                    "Mil Chest Puncture": 'US Military 1',
                    "Civilian Shin Amputation": 'Civilian 1',
                    "Attacker Wrist Amputation": 'Attacker 1',
                    "Mil Stomach Puncture": 'US Military 2',
                    "Civilian Stomach Puncture": 'Civilian 2',
                    "Attacker Shoulder Puncture": 'Attacker 2',
                    "Civilian Thigh Laceration": 'Civilian 3',
                    "Mil Burns": 'US Military 3',
                    "Mil Wrist Broken": 'US Military 4'
                }
            elif env == 'Urban':
                answer_map = {
                    "Mil Bicep Puncture": 'US Military 1',
                    "Mil Discharged Weapon Stomach Puncture": 'US Military 2',
                    "Civilian Broken Wrist": 'Civilian 1',
                    "Shooter Shoulder Puncture": 'Shooter 1',
                    "Mil Thigh Puncture": 'US Military 3',
                    "Civilian Chest Puncture": 'Civilian 2',
                    "Civilian Stomach Puncture": 'Civilian 3',
                    "Mil Stomach Puncture": 'US Military 4'
                }
            for action in self.json_data['actionList']:
                if action['actionType'] == 'Question' and 'evacuate' in action['question']:
                    answers.append(answer_map[action['answer']])
            return answers

        evaced = get_evaced_patients()

        def get_ps_ss():
            search1 = None
            search2 = None
            answer_map = {
                "Stay": 0,
                "Search": 1
            }
            ps1 = 0
            for action in self.json_data['actionList']:
                if action['actionType'] == 'Question':
                    if 'search' in action['question']:
                        try:
                            if search1 is None:
                                search1 = answer_map[action['answer']]
                            elif search2 is None:
                                search2 = answer_map[action['answer']]
                            else:
                                self.logger.log(LogLevel.WARN, "More than two 'search' answers; ignoring extras.")
                                continue
                        except KeyError:
                            self.logger.log(LogLevel.WARN, f"Ignoring unexpected Search answer, '{action['answer']}'")
                elif action['actionType'] == 'MovedBeforeClearedByCommand':
                    if action['movedBeforeClearedByCommand'] is True:
                        ps1 = 1 # If any MovedBeforeClearedByCommand is true, then they moved

            return search1, search2, ps1

        search1, search2, ps1 = get_ps_ss()
        results[f'{env}_search1'] = search1
        results[f'{env}_search2'] = search2
        results[f'{env}_personal_safety'] = ps1

        if env == 'Desert':
            patients_in_order = ['US Military 1', 'Civilian 1', 'Attacker 1', 'US Military 2', 'Civilian 2', 'Attacker 2', 'Civilian 3', 'US Military 3', 'US Military 4']
        elif env == 'Urban':
            patients_in_order = ['US Military 1', 'US Military 2', 'Civilian 1', 'Shooter 1', 'US Military 3', 'Civilian 2', 'Civilian 3', 'US Military 4']
        clean_patient_order_engaged = []
        for x in patient_order_engaged:
            if x not in clean_patient_order_engaged:
                clean_patient_order_engaged.append(x)
        for i in range(len(patients_in_order)):
            name = f'patient{i+1}'
            sim_name = patients_in_order[i]
            triage_time = triage_times['interactions'].get(sim_name, 0)
            results[f'{env}_{name}_time'] = triage_time
            try:
                results[f'{env}_{name}_order'] = clean_patient_order_engaged.index(sim_name) + 1
            except:
                results[f'{env}_{name}_order'] = 'N/A'
            results[f'{env}_{name}_evac'] = 'Yes' if sim_name in evaced else 'No'
            results[f'{env}_{name}_assess'] = assessments['per_patient'].get(sim_name, 0)
            results[f'{env}_{name}_treat'] = treatments['per_patient'].get(sim_name, 0)
            results[f'{env}_{name}_tag'] = tag_counts['tags'].get(sim_name, 'N/A')

        text_response = text_scenario_collection.find_one({"evalNumber": EVAL_NUM, 'participantID': self.participantId})
        text_kdma_results = {}
        if text_response is None:
            self.logger.log(LogLevel.WARN, f"Error getting text KDMAs for pid {self.participantId}.")
            for kdma in KDMA_MAP.values():
                text_kdma_results[f"Participant Text {kdma} KDMA"] = ''
        else:
            kdmas = text_response['kdmas']
            for kdma in kdmas:
                text_kdma_results[f"Participant Text {KDMA_MAP[kdma['kdma']]} KDMA"] = kdma.get('value', '')

        if VERBOSE:
            print(f"{env} Results: {results}")
        if SEND_TO_MONGO:
            mongo_id = self.participantId + f'_{EVAL_PREFIX}_open_world'
            try:
                mongo_collection_raw.insert_one({'openWorld': True, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': self.json_data, 'pid': self.participantId, '_id': self.participantId + '_' + self.environment.replace('.yaml', '')})
            except:
                mongo_collection_raw.update_one({'_id': self.participantId + '_' + self.environment.replace(' ', '-')}, {'$set': {'openWorld': True, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': self.json_data, 'pid': self.participantId}})
            try:
                mongo_collection_matches.insert_one({'scenario_id': 'eval_open_world', 'timestamp': self.timestamp, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, f'{env}_data': results, 'openWorld': True, 'env': self.environment.split('.yaml')[0], 'text_kdmas': text_kdma_results, 'pid': self.participantId, '_id': mongo_id})
            except:
                mongo_collection_matches.update_one({'_id': mongo_id}, {'$set': {'scenario_id': 'eval_open_world', 'timestamp': self.timestamp, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, f'{env}_data': results, 'openWorld': True, 'env': self.environment.split('.yaml')[0], 'text_kdmas': text_kdma_results, 'pid': self.participantId, '_id': mongo_id}})
            if self.pid_in_log:
                num_sim_found = mongo_collection_raw.count_documents({"pid": str(self.participantId)})
                participant_log_collection.update_one({'_id': participant_log_collection.find_one({"ParticipantID": int(self.participantId)})['_id']},
                                                      {'$set': {'claimed': True, "simEntryCount": num_sim_found}})


    """
        Create a ta1 session; respond to the probes; get kdma values
    """
    def get_ta1_calculations(self, scenario_id: str, probes: list) -> Tuple[str, list]:
        if len(probes) == 0:
            return None, None
        try:
            session_id = requests.post(f'{ADEPT_URL}api/v1/new_session').text.replace('"', '').strip()
            #if VERBOSE:
            print(f"Sending probes: {probes}")
            for probe in probes:
                requests.post(f'{ADEPT_URL}api/v1/response', json={
                    "response": {
                        "probe_id": probe['probe_id'],
                        "choice": probe['choice'],
                        "justification": "justification",
                        "scenario_id": scenario_id,
                    },
                    "session_id": session_id
                })
            kdmas = requests.get(f'{ADEPT_URL}api/v1/computed_kdma_profile?session_id={session_id}').json()
        except:
            self.logger.log(LogLevel.WARN, "TA1 Server Get Request failed; no KDMAs generated.")
            return None, None
        return session_id, kdmas


    """
    OpenWorld scenarios are fairly straightforward.  Each probe is a choice between treating Patient A and Patient B.
    We parse the YAML file to generate a list of probe ids mapped to a map of patient ids to choice ids.
    Then for each probe, we iterate through the sim json output to see which patient was engaged first, noting the mapped choice.
    Finally, we send these probes (with their choices) to TA1 to get OW KDMA values for AF and MF.
    """
    def match_ow_probes(self, env: str):
        # TODO: parse the YAML file to generate a list of probe ids mapped to a map of patient ids to choice ids.
        ow_scenes = self.ow_yaml['scenes']
        probe_map = [] # a map of probe_ids to a map of sim patient names to choice ids
        for scene in ow_scenes:
            for mapping in scene['action_mapping']:
                pass # Add a map from the sim patient name to the associated choice id

        # But for now, we are hard-coding the probe_map
        desert_probe_map = {
            'June2025-AF-OW-desert.Probe 1':  {'US Military 1': 'Response 1-A',  'Civilian 1':    'Response 1-B' },
            'June2025-AF-OW-desert.Probe 2a': {'Civilian 1':    'Response 2a-A', 'Attacker 1':    'Response 2a-B'},
            'June2025-MF-OW-desert.Probe 2b': {'Civilian 1':    'Response 2b-A', 'Attacker 1':    'Response 2b-B'},
            'June2025-AF-OW-desert.Probe 3':  {'Civilian 3':    'Response 3-A' , 'US Military 3': 'Response 3-B' },
            'June2025-AF-OW-desert.Probe 4a': {'Attacker 1':    'Response 4a-A', 'US Military 4': 'Response 4a-B'},
            'June2025-MF-OW-desert.Probe 4b': {'Attacker 1':    'Response 4b-A', 'US Military 4': 'Response 4b-B'},
            'June2025-AF-OW-desert.Probe 5a': {'Attacker 2':    'Response 5a-A', 'US Military 3': 'Response 5a-B'},
            'June2025-MF-OW-desert.Probe 5b': {'Attacker 2':    'Response 5b-A', 'US Military 3': 'Response 5b-B'},
            'June2025-AF-OW-desert.Probe 6':  {'US Military 2': 'Response 6-A' , 'Civilian 2':    'Response 6-B' }
        }
        urban_probe_map = {
            'June2025-MF-OW-urban.Probe 1': {'US Military 1': 'Response 1-A', 'US Military 2': 'Response 1-B'},
            'June2025-MF-OW-urban.Probe 2': {'Civilian 1':    'Response 2-A', 'Shooter 1':     'Response 2-B'},
            'June2025-AF-OW-urban.Probe 3': {'US Military 3': 'Response 3-A', 'Civilian 2':    'Response 3-B'},
            'June2025-AF-OW-urban.Probe 4': {'Civilian 3':    'Response 4-A', 'US Military 4': 'Response 4-B'},
            'June2025-MF-OW-urban.Probe 5': {'Civilian 3':    'Response 5-A', 'Shooter 1':     'Response 5-B'},
            'June2025-AF-OW-urban.Probe 6': {'US Military 3': 'Response 6-A', 'Civilian 1':    'Response 6-B'}
        }
        probe_map = desert_probe_map if env == 'Desert' else urban_probe_map

        # For each probe, we iterate through the sim json output to see which patient was engaged first, noting the mapped choice.
        engagement_actions = ['Pulse', 'Treatment', 'Tag']
        action_list: list = [action for action in self.json_data['actionList'] if action['actionType'] in engagement_actions]

        def first_engaged(characters: list):
            for action in action_list:
                for character in characters:
                    if action['casualty'] == character:
                        return character
            return None # None of the characters was engaged

        # Generate the list of probes to send to TA1
        probes: list = []
        match_data = []
        for probe_id, response_map in probe_map.items():
            first_char = first_engaged(response_map.keys())
            if first_char:
                probes.append({'probe_id': probe_id, 'choice': response_map[first_char]})
            else:
                self.logger.log(LogLevel.WARN, f"Skipping unmatched probe {probe_id}.")
            # TODO later; not needed for RQ8, and possibly not at all
            match_data.append({'scene_id': probe_id, 'probe_id': probe_id, 'found_match': True if first_char else False, 'probe': {}, 'user_action': {}})
        print(f"Found {len(probes)} out of {len(probe_map)} probes.")

        # Send these probes (with their choices) to TA1 to get OW KDMA values for AF and MF
        ow_align = {}
        if CALC_KDMAS:
            ow_align['sid'], ow_align['kdmas'] = self.get_ta1_calculations(self.ow_yaml['id'], probes)
        match_data = {'alignment': ow_align, 'data': match_data}
        if VERBOSE:
            print(f"Match data: {match_data}")
        if SEND_TO_MONGO:
            mongo_id = self.participantId + '_ow_' + self.environment.split('.yaml')[0]
            try:
                mongo_collection_matches.insert_one({'scenario_id': self.ow_yaml['id'], 'timestamp': self.timestamp, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': match_data, 'ta1': 'ow', 'env': self.environment.split('.yaml')[0], 'pid': self.participantId, '_id': mongo_id})
            except:
                mongo_collection_matches.update_one({'_id': mongo_id}, {'$set': {'scenario_id': self.ow_yaml['id'], 'timestamp': self.timestamp, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': match_data, 'ta1': 'ow', 'env': self.environment.split('.yaml')[0], 'pid': self.participantId, '_id': mongo_id}})
        json.dump(match_data, self.output_ow, indent=4)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=f"ITM - {EVAL_NAME} Probe Matcher", usage='probe_matcher.py [-h] -i [-w] [-e] PATH')

    parser.add_argument('-i', '--input_dir', dest='input_dir', type=str, help='The path to the directory where all participant files are. Required.')
    parser.add_argument('-w', '--weekly', action='store_true', dest='is_weekly', help='A flag to determine if this is a weekly run. If weekly, global variables change.')
    parser.add_argument('-e', '--eval_num', dest='eval_num', type=int, help="The eval number to use during runtime")
    parser.add_argument('-n', '--no_output', action='store_true', dest='no_output', help="Do not send to mongo")
    parser.add_argument('-v', '--verbose', action='store_true', dest='is_verbose', help="Verbose command line output")
    args = parser.parse_args()
    removed = []
    if not args.input_dir:
        print("Input directory (-i PATH) is required to run the probe matcher.")
        exit(1)
    if args.is_weekly:
        # Should only run new files, and run alignment for those missing it
        SEND_TO_MONGO = True
        CALC_KDMAS = True
        RUN_ALL = False
        RERUN_SESSIONS = True
    if args.no_output:
        SEND_TO_MONGO = False
    if args.is_verbose:
        VERBOSE = True
    if args.eval_num:
        if args.eval_num == 8:
            EVAL_NAME = 'Phase 2 June 2025 Collaboration'
            EVAL_NUM = 8
        else:
            print(f"Evaluation #{args.eval_num} is not supported at this time.")
            exit(1)
    # Instantiate mongo client
    client = MongoClient(config('MONGO_URL'))
    db = client.dashboard
    if SEND_TO_MONGO:
        # create new collection for simulation runs
        mongo_collection_matches = db['humanSimulatorNew']
        mongo_collection_raw = db['humanSimulatorRawNew']
    participant_log_collection = db['participantLog']
    text_scenario_collection = db['userScenarioResults']

    # Go through the input directory and find all sub directories
    sub_dirs = [name for name in os.listdir(args.input_dir) if os.path.isdir(os.path.join(args.input_dir, name))]
    # For each subdirectory, see if a json file exists
    for dir in sub_dirs:
        parent = os.path.join(args.input_dir, dir)
        # Get date of sim
        csv_file = open(os.path.join(parent, dir+'.csv'), 'r', encoding='utf-8')
        reader = csv.reader(csv_file)
        next(reader)
        line2 = next(reader)
        sim_date = datetime.strptime(line2[2], "%m/%d/%Y %I:%M:%S %p")
        ph2_date = datetime(2025, 6, 2)
        # If date is after 6/2, we are good! This is part of phase 2
        valid_date = sim_date > ph2_date
        # Remove files that have invalid pids
        pid = dir.split('_')[-1]
        try:
            pid = int(pid)
        except:
            if VERBOSE:
                print(f"Trying to remove pid {pid}, parent file {os.path.join(parent)}.")
            #os.system(f'rm -rf {os.path.join(parent)}')
            removed.append(parent)
            continue
        pid_in_log = participant_log_collection.count_documents({"ParticipantID": int(pid)}) > 0

        if not pid_in_log or not valid_date:
            if VERBOSE:
                print(f"Trying to remove pid {pid}, parent directory {parent}.")
            #os.system(f'rm -rf {parent}')
            removed.append(parent)
            continue

        if os.path.isdir(parent):
            for f in os.listdir(parent):
                if '.json' in f:
                    print(f"\n** Processing {f} **")
                    # json found! Grab matching csv and send to the probe matcher
                    try:
                        matcher = ProbeMatcher(os.path.join(parent, f))
                        # matcher = ProbeMatcher(os.path.join(parent, f), None, None) # use this for basic matching testing when SSL is not working
                        if matcher.environment != '' and matcher.analyze:
                            matcher.match_probes()
                        matcher.__del__()
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        exit()
                elif '.html' in f or '.jpg' in f:
                    os.remove(os.path.join(parent, f))
    if VERBOSE:
        print()
        print('Removed:', removed)
