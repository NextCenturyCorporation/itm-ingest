import yaml, argparse, json, os, csv, requests, copy
from logger import LogLevel, Logger
from pymongo import MongoClient
from datetime import datetime
from decouple import config
from typing import Tuple
from dateutil import parser as dateparser

SEND_TO_MONGO = True # send all raw and calculated data to the mongo db if true
CALC_KDMAS = True # send data to servers to calculate KDMA values if true
RUN_ALL = True  # run all files in the input directory, even if they have already been run/analyzed, if true
DEFAULT_EVAL_NUM = 8
EVAL_NUM = None
EVAL_NAME = None
EVAL_PREFIX = None
VERBOSE = False
ADEPT_URL = config("ADEPT_URL")

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

REQ_HEMORRHAGE_PROCEDURES = {
    'desert': {
        'US Military 1': ['R Chest Puncture'],
        'Civilian 1': ['L Shin Amputation'],
        'Attacker 1': ['R Wrist Amputation'],
        'US Military 2': ['L Stomach Puncture'],
        'Civilian 2': ['R Stomach Puncture'],
        'Attacker 2': ['L Shoulder Puncture'],
        'Civilian 3': ['L Thigh Laceration']
    },
    'urban': {
        'US Military 1': ['R Bicep Puncture'],
        'US Military 2': ['L Stomach Puncture'],
        'Shooter 1': ['L Shoulder Puncture'],
        'US Military 3': ['R Thigh Puncture'],
        'Civilian 2': ['L Chest Puncture'],
        'Civilian 3': ['R Stomach Puncture'],
        'US Military 4': ['L Stomach Puncture']
    }
}

ALL_REQ_PROCEDURES = {
    'desert': {
        'US Military 1': ['R Chest Puncture', 'L Chest Collapse'], 
        'Civilian 1': ['L Shin Amputation'],
        'Attacker 1': ['R Wrist Amputation'],
        'US Military 2': ['L Stomach Puncture'],
        'Civilian 2': ['R Stomach Puncture'],
        'Attacker 2': ['L Shoulder Puncture'], 
        'Civilian 3': ['L Thigh Laceration'],
        'US Military 3': ['L Forearm Burn', 'L Chest Burn'], 
        'US Military 4': ['L Wrist Broken']
    },
    'urban': {
        'US Military 1': ['R Bicep Puncture'], 
        'US Military 2': ['L Stomach Puncture'], 
        'Civilian 1': ['R Wrist Broken'], 
        'Shooter 1': ['L Shoulder Puncture'], 
        'US Military 3': ['R Thigh Puncture'], 
        'Civilian 2': ['L Chest Puncture', 'R Chest Collapse'], 
        'Civilian 3': ['R Stomach Puncture'], 
        'US Military 4': ['L Stomach Puncture'] 
    }
}

SUPPLEMENTAL_PROCEDURES = {
    'desert': {
        'US Military 1': ['Nasal Airway'],
        'Civilian 1': ['IV Blood', 'Antibiotics', 'Blanket', 'Fentanyl Lollipop'],
        'Attacker 1': ['IV Blood', 'Antibiotics', 'Blanket', 'Fentanyl Lollipop'],
        'US Military 2': ['IV Blood', 'Antibiotics', 'Blanket', 'Fentanyl Lollipop'],
        'Civilian 2': ['IV Blood', 'Antibiotics', 'Blanket', 'Fentanyl Lollipop'], 
        'Attacker 2': ['IV Blood', 'Antibiotics', 'Blanket', 'Fentanyl Lollipop'], 
        'Civilian 3': ['IV Blood', 'Blanket', 'Fentanyl Lollipop'], 
        'US Military 3': ['Blanket', 'Fentanyl Lollipop'],
        'US Military 4': []
    },
    'urban': {
        'US Military 1': ['IV Blood', 'Antibiotics', 'Blanket', 'Fentanyl Lollipop'],
        'US Military 2': ['IV Blood', 'Antibiotics', 'Blanket', 'Fentanyl Lollipop'],
        'Civilian 1': ['Fentanyl Lollipop'], 
        'Shooter 1': ['IV Blood', 'Antibiotics', 'Blanket', 'Fentanyl Lollipop'], 
        'US Military 3': ['IV Blood', 'Blanket', 'Fentanyl Lollipop'],
        'Civilian 2': ['L Chest Puncture', 'R Chest Collapse'], 
        'Civilian 3': ['IV Blood', 'Antibiotics', 'Blanket', 'Fentanyl Lollipop'], 
        'US Military 4': ['IV Blood', 'Antibiotics', 'Blanket', 'Fentanyl Lollipop']
    }
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
    pid_in_log = False


    def __init__(self, json_path):
        '''
        Load in the file and parse the yaml
        '''
        # Get environment from json to choose correct desert/urban yamls
        with open(json_path, 'r', encoding='utf-8') as json_file:
            self.json_data = json.load(json_file)
            self.json_filename = json_file.name
        if (self.json_data['configData']['teleportPointOverride'] == 'Tutorial' or 'Tutorial' in self.json_data.get('configData', {}).get('narrative', {}).get('narrativeSections', [{'sectionDescription': ''}])[0].get('sectionDescription')):
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
        narrative = self.json_data["configData"]["narrative"]["narrativeDescription"]
        if 'Desert' in narrative:
            env = f"{EVAL_PREFIX}-desert-openworld.yaml"
        elif 'Urban' in narrative:
            env = f"{EVAL_PREFIX}-urban-openworld.yaml"
        else:
            self.logger.log(LogLevel.WARN, f'Skipping narrative {narrative} since it is not a(n) {EVAL_PREFIX} Open World scenario.')
            return

        self.environment = env
        self.logger.log(LogLevel.INFO, f'Environment: {self.environment}')

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
            self.logger.log(LogLevel.INFO, f"Create output file {filename}.")
        self.output_ow = open(filename, 'w', encoding='utf-8')
        try:
            # Get yaml file
            yaml_filename = os.path.join(os.path.join('phase2', EVAL_PREFIX), env)
            if VERBOSE:
                self.logger.log(LogLevel.INFO, f"Opening {yaml_filename}.")
            ow_file = open(yaml_filename, 'r', encoding='utf-8')
            if VERBOSE:
                self.logger.log(LogLevel.INFO, f"Loading {yaml_filename}.")
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
            self.match_ow_probes(env)
            self.analyze_openworld(env)
        else:
            self.logger.log(LogLevel.WARN, f"No function available to probe match for environment {self.environment}")


    def analyze_openworld(self, env: str):

        results = {
            'pid': self.participantId,
            f'{env} Assess_patient': 0,
            f'{env} Assess_total': 0,
            f'{env} Treat_patient': 0,
            f'{env} Treat_total': 0,
            f'{env} Triage_time': 0,
            f'{env} Triage_time_patient': 0,
            f'{env} Engage_patient': 0,
            f'{env} Tag_acc': 0,
            f'{env} Tag_expectant': False,
            f'{env} Hemorrhage control': 0,
            f'{env} Hemorrhage control_time': None,
            f'{env} Triage Performance': 0
        }

        ow_csv = open(self.json_filename.replace('.json', '.csv'), 'r', encoding='utf-8')
        reader = csv.reader(ow_csv)
        header = next(reader)
        data = []
        for line in reader:
            data.append(line)
        if ow_csv:
            ow_csv.close()

        def timestamp_to_seconds(timestamp):
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
        results[f'{env} Engage_patient'] = sum(engagement_times) / max(1, len(engagement_times))


        def count_assessment_actions():
            '''returns the total count of assessment actions during the scenario'''
            assessment_actions = ['SP_O2_TAKEN', 'BREATHING_CHECKED', 'PULSE_TAKEN']
            count = 0
            last_done = {}
            per_patient = {}
            for x in data:
                # only count actions that are more than 5 seconds apart from the last of the same type of action
                if x[0] in assessment_actions:
                    if (x[0] not in last_done or (timestamp_to_seconds(x[2]) - last_done[x[0]]) > 5):
                        last_done[x[0]] = timestamp_to_seconds(x[2])
                        count += 1
                        patient = x[header.index('PatientID')].split(' Root')[0]
                        if patient not in per_patient:
                            per_patient[patient] = 0
                        per_patient[patient] += 1
            return {'count': count, 'per_patient': per_patient}

        assessments = count_assessment_actions()
        results[f'{env} Assess_total'] = assessments['count']
        results[f'{env} Assess_patient'] = results[f'{env} Assess_total'] / max(1, patients_engaged)

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
        results[f'{env} Treat_total'] = treatments['count']
        results[f'{env} Treat_patient'] = results[f'{env} Treat_total'] / max(1, patients_treated)

        def get_triage_time():
            '''gets the time from start to finish (in seconds) to complete the scenario'''
            if len(data) > 0:
                start = float(data[0][1])
                end = float(data[len(data)-2][1])
                return ((end-start))/1000

        results[f'{env} Triage_time'] = get_triage_time()

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
        results[f'{env} Tag_ACC'] = tag_counts['correct'] / tag_counts['count']
        results[f'{env} Tag_Expectant'] = 'Yes' if tag_counts['tags'].get('US Soldier 3') == 'gray' else 'No'

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
        results[f'{env} Triage_time_patient'] = triage_times['total'] / max(1, patients_engaged)

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
        results[f'{env} Search1'] = search1
        results[f'{env} Search2'] = search2
        results[f'{env} Personal_safety'] = ps1

        def get_hemorrhage_control():
            to_complete = copy.deepcopy(REQ_HEMORRHAGE_PROCEDURES[env.lower()])
            start_time = 0
            end_time = 0
            for x in data:
                if x[0] == 'SESSION_START':
                    start_time = timestamp_to_seconds(x[header.index('Timestamp')])
                if x[0] == 'INJURY_TREATED':
                    patient = x[header.index("PatientID")]
                    where = x[header.index("InjuryName")]
                    completed = x[header.index("InjuryTreatmentComplete")]
                    # only look for hemorrhage control that has been completed
                    if completed:
                        if patient in to_complete:
                            # if hemorrhage has been completely treated, remove from list
                            if where in to_complete[patient]:
                                to_complete[patient].remove(where)
                                # update end time to latest treatment. As the csv is written in read in time order, this will end up getting
                                # the last hemorrhage control to calculate end time minus start time
                                end_time = timestamp_to_seconds(x[header.index('Timestamp')])
                                # remove patients whose hemorrhages have all been treated
                                if len(to_complete[patient]) == 0:
                                    del to_complete[patient]

            # if there are no patients left in the dictionary, we have succeeded with hemorrhage control!
            res = 1 if len(list(to_complete.keys())) == 0 else 0
            time_to_hcontrol = (end_time-start_time) if res == 1 else None
            return {'completed': res, 'time': time_to_hcontrol}
        
        hem_control = get_hemorrhage_control()
        results[f'{env} Hemorrhage control'] = hem_control['completed']
        results[f'{env} Hemorrhage control_time'] = hem_control['time']

        def get_triage_performance():
            '''
            For every expected treatment, assign a 1 if they applied it and a 0 if they didn't.
            Assign an extra 0 for any treatment applied that isn't correct.
            Use the mean (decimal) as the percentage. 
            In other words, score hits, misses, and false alarms where both misses and false alarms are treated as incorrect.
            The denominator is the total # of treatments they applied + # of treatments they did not attempt
            '''
            to_complete = copy.deepcopy(ALL_REQ_PROCEDURES[env.lower()])
            supplemental = copy.deepcopy(SUPPLEMENTAL_PROCEDURES[env.lower()])
            supplemental_points = {}
            total_tools_applied = 0
            correct_tools_applied = 0
            misses = 0
            for x in data:
                # injury treated will always be followed by tool applied, which we'll use to count total
                # we use injury treated to count correct applications
                if x[0] == 'INJURY_TREATED':
                    patient = x[header.index("PatientID")]
                    where = x[header.index("InjuryName")]
                    completed = x[header.index("InjuryTreatmentComplete")]
                    if completed:
                        if patient in to_complete:
                            # if injury has been treated, remove from list
                            if where in to_complete[patient]:
                                to_complete[patient].remove(where)
                                correct_tools_applied += 1
                                # remove patients who are completely treated
                                if len(to_complete[patient]) == 0:
                                    del to_complete[patient]
                # injury_treated wouldn't get the false alarms; tool hover/selected could be them trying and failing
                # so tool_applied works best here to get hits and false alarms
                if x[0] == 'TOOL_APPLIED':
                    total_tools_applied += 1

                    # count the number of allowed supplemental treatments given to a patient (allows for multiple applications)
                    patient = x[header.index('PatientID')]
                    tool = x[header.index('ToolType')]
                    if patient in supplemental and tool in supplemental[patient]:
                        if patient not in supplemental_points:
                            supplemental_points[patient] = 0
                        supplemental_points[patient] += 1

            # count misses
            for patient in to_complete:
                misses += len(to_complete[patient])

            # add supplemental points (only counts if the participant gave the required treatments first!)
            for patient in supplemental_points:
                if patient not in to_complete:
                    correct_tools_applied += supplemental_points[patient]

            return (correct_tools_applied / max(1, total_tools_applied + misses)) * 100
        
        results[f'{env} Triage Performance'] = get_triage_performance()

        if env == 'Desert':
            patients_in_order = ['US Military 1', 'Civilian 1', 'Attacker 1', 'US Military 2', 'Civilian 2', 'Attacker 2', 'Civilian 3', 'US Military 3', 'US Military 4']
        elif env == 'Urban':
            patients_in_order = ['US Military 1', 'US Military 2', 'Civilian 1', 'Shooter 1', 'US Military 3', 'Civilian 2', 'Civilian 3', 'US Military 4']
        clean_patient_order_engaged = []
        for x in patient_order_engaged:
            if x not in clean_patient_order_engaged:
                clean_patient_order_engaged.append(x)
        for i in range(len(patients_in_order)):
            name = f'Patient{i+1}'
            sim_name = patients_in_order[i]
            triage_time = triage_times['interactions'].get(sim_name, 0)
            results[f'{env} {name}_time'] = triage_time
            try:
                results[f'{env} {name}_order'] = clean_patient_order_engaged.index(sim_name) + 1
            except:
                results[f'{env} {name}_order'] = 'N/A'
            results[f'{env} {name}_evac'] = 'Yes' if sim_name in evaced else 'No'
            results[f'{env} {name}_assess'] = assessments['per_patient'].get(sim_name, 0)
            results[f'{env} {name}_treat'] = treatments['per_patient'].get(sim_name, 0)
            results[f'{env} {name}_tag'] = tag_counts['tags'].get(sim_name, 'N/A')

        text_response = text_scenario_collection.find_one({"evalNumber": 9 if '2025093' in str(self.participantId) else EVAL_NUM, 'participantID': self.participantId, "scenario_id": {"$not": {"$regex": "PS-AF"}}})
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
            self.logger.log(LogLevel.INFO, f"\n{env} Results: {results}")

        self.logger.log(LogLevel.INFO, f"{'' if SEND_TO_MONGO else 'NOT '}Saving to database.")
        if SEND_TO_MONGO:
            mongo_id = self.participantId + '_ow_' + self.environment.split('.yaml')[0]
            try:
                mongo_collection_raw.insert_one({'openWorld': True, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': self.json_data, 'pid': self.participantId, '_id': self.participantId + '_' + self.environment.replace('.yaml', '')})
            except:
                mongo_collection_raw.update_one({'_id': self.participantId + '_' + self.environment.replace(' ', '-')}, {'$set': {'openWorld': True, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': self.json_data, 'pid': self.participantId}})
            try:
                mongo_collection_matches.insert_one({'scenario_id': self.ow_yaml['id'], 'timestamp': self.timestamp, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'actionAnalysis': results, 'openWorld': True, 'env': self.environment.split('.yaml')[0], 'text_kdmas': text_kdma_results, 'pid': self.participantId, '_id': mongo_id})
            except:
                mongo_collection_matches.update_one({'_id': mongo_id}, {'$set': {'scenario_id': self.ow_yaml['id'], 'timestamp': self.timestamp, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'actionAnalysis': results, 'openWorld': True, 'env': self.environment.split('.yaml')[0], 'text_kdmas': text_kdma_results, 'pid': self.participantId, '_id': mongo_id}})
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
            if VERBOSE:
                self.logger.log(LogLevel.INFO, f"--> Sending probes: {probes}")
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
        self.logger.log(LogLevel.INFO, f"Processing {env}")
        # Parse the YAML file to generate a map of probe IDs to a map of sim patient names to choice ids
        probe_map = {}
        for scene in self.ow_yaml['scenes']:
            patient_name_map = {} # maps patient ID to sim patient name
            response_map = {} # maps sim patient name to response (choice_id)
            probe_id = None
            for character in scene['state']['characters']:
                sim_patient_name = character['unstructured'].split(';')[-1].strip() # Sim patient name added after semi-colon in csv
                patient_name_map[character['id']] = sim_patient_name
            for mapping in scene['action_mapping']:
                probe_id = mapping['probe_id']
                choice_id = mapping['choice']
                character_id = mapping['character_id']
                response_map[patient_name_map[character_id]] = choice_id
            probe_map[probe_id] = response_map

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
                match_data.append({'scene_id': probe_id, 'probe_id': probe_id, 'found_match': True, 'response': response_map[first_char], 'user_action': {}})
            else:
                self.logger.log(LogLevel.WARN, f"Unmatched probe {probe_id}.")
                match_data.append({'scene_id': probe_id, 'probe_id': probe_id, 'found_match': False, 'response': '', 'user_action': {}})
        self.logger.log(LogLevel.INFO, f"Found {len(probes)} out of {len(probe_map)} probes.")

        # Send these probes (with their choices) to TA1 to get OW KDMA values for AF and MF
        ow_align = {}
        if CALC_KDMAS:
            ow_align['sid'], ow_align['kdmas'] = self.get_ta1_calculations(self.ow_yaml['id'], probes)
        match_data = {'alignment': ow_align, 'data': match_data}
        if VERBOSE:
            print()
            self.logger.log(LogLevel.INFO, f"\nMatch data: {match_data}")
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
    if args.is_weekly: # Not currently used in phase 2
        # Should only run new files, and calculate KDMAs for those missing it
        SEND_TO_MONGO = True
        CALC_KDMAS = True
        RUN_ALL = False
    if args.no_output:
        SEND_TO_MONGO = False
    if args.is_verbose:
        VERBOSE = True
    EVAL_NUM = DEFAULT_EVAL_NUM if not args.eval_num else args.eval_num
    if EVAL_NUM in [8, 9, 10]:
        EVAL_PREFIX = 'june2025'
    else:
        print(f"Evaluation #{EVAL_NUM} is not supported at this time.")
        exit(1)

    # Instantiate mongo client
    client = MongoClient(config('MONGO_URL'))
    db = client.dashboard
    if SEND_TO_MONGO:
        # create new collection for simulation runs
        mongo_collection_matches = db['humanSimulator']
        mongo_collection_raw = db['humanSimulatorRaw']
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
        # If date is after 6/2/2025, we are good! This is part of phase 2
        valid_date = sim_date > ph2_date
        # Remove files that have invalid pids
        pid = dir.split('_')[-1]
        try:
            pid = int(pid)
        except:
            print(f"Remove invalidly formatted pid {pid}, parent file {os.path.join(parent)}.")
            removed.append(parent)
            continue
        pid_in_log = participant_log_collection.count_documents({"ParticipantID": int(pid)}) > 0

        if not pid_in_log or not valid_date:
            print(f"Remove pid {pid}, parent directory {parent}, because it is not in the participant log or has an invalid date.")
            removed.append(parent)
            continue
        if "202506" in str(pid):
            EVAL_NAME = 'June 2025 Collaboration'
            EVAL_PREFIX = 'june2025'
            EVAL_NUM = 8
        elif "202507" in str(pid):
            EVAL_NAME = 'July 2025 Collaboration'
            EVAL_PREFIX = 'june2025'
            EVAL_NUM = 9
        elif "202509" in str(pid):
            EVAL_NAME = 'September 2025 Collaboration'
            EVAL_PREFIX = 'june2025'
            EVAL_NUM = 10
        else:
            print(f"Cannot match eval number to pid {pid}. Skipping.")
            continue
        if os.path.isdir(parent):
            for f in os.listdir(parent):
                if '.json' in f:
                    print(f"\n** Processing {f} **")
                    # json found! Grab matching csv and send to the probe matcher
                    try:
                        matcher = ProbeMatcher(os.path.join(parent, f))
                        if matcher.environment != '':
                            matcher.match_probes()
                        matcher.__del__()
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        exit()
                elif '.html' in f or '.jpg' in f:
                    os.remove(os.path.join(parent, f))

    if len(removed) > 0:
        print()
        print('Remove the following path(s):')
        for path in removed:
            print(f"  {path}")
