import yaml, argparse, json, os, copy, csv
from logger import LogLevel, Logger
from pymongo import MongoClient
from datetime import datetime
import requests
from decouple import config 
import utils.db_utils as db_utils
from dateutil import parser as dateparser

SEND_TO_MONGO = True # send all raw and calculated data to the mongo db if true
RUN_ALIGNMENT = True # send data to servers to calculate alignment if true
RUN_ALL = True  # run all files in the input directory, even if they have already been run/analyzed, if true
RUN_COMPARISON = True # run the vr/text and vr/adm comparisons, whether RUN_ALL is True or False
RECALCULATE_COMPARISON = True
RERUN_ADEPT_SESSIONS = False # rerun adept sessions only to get new session ids
EVAL_NUM = 5
EVAL_NAME = 'Phase 1 Evaluation'


ADEPT_URL = config("ADEPT_PH1_URL")
ST_URL = config("ST_URL")

SCENE_MAP = {
    "qol-ph1-eval-2 Narrative": "phase1-soartech-eval-qol2.yaml",
    "qol-ph1-eval-3 Narrative": "phase1-soartech-eval-qol3.yaml",
    "qol-ph1-eval-4 Narrative": "phase1-soartech-eval-qol4.yaml",
    "vol-ph1-eval-2 Narrative": "phase1-soartech-eval-vol2.yaml",
    "vol-ph1-eval-3 Narrative": "phase1-soartech-eval-vol3.yaml",
    "vol-ph1-eval-4 Narrative": "phase1-soartech-eval-vol4.yaml",
    "DryRunEval-MJ2-eval Narrative": "phase1-adept-eval-MJ2.yaml",
    "DryRunEval-MJ4-eval Narrative": "phase1-adept-eval-MJ4.yaml",
    "DryRunEval-MJ5-eval Narrative": "phase1-adept-eval-MJ5.yaml",
    "Desert Open World Narrative": "Desert Open World Narrative"
}

ACTION_TRANSLATION = {
    "APPLY_TREATMENT": "Treatment",
    "CHECK_ALL_VITALS": "Vitals",
    "MOVE_TO_EVAC": "DragPatient",
    "MESSAGE": "Justify",
    "MOVE_TO": "Go",
    'END_SCENE': 'None',
    "SEARCH": "None"
}

JUSTIFY_MAPPING = {
    "Reason for Evacuating Kicker": {
        "Learn Plan of Kicker": "Response 3-A.1-B",
        "Kicker is More Injured": "Response 3-A.1-A"
    },
    "Reason for Evacuating Passerby": {
        "Passerby is Innocent": "Response 3-B.1-B",
        "Kicker Carying other Weapon": "Response 3-B.1-A" # typo is in sim json, just copying it here!
    },
    "Adept Probe 7: Why did you choose to evacuate the victim?": {
        "They were the most seriously injured": "Response 7-A",
        "They were the most likely to benefit from treatment at the next level of care.": "Response 7-B",
        "Command guidance and protocol.": "Response 7-C",
        "They were an innocent victim.": "Response 7-D"
    },
    "Adept Probe 7: Why did you choose to evacuate the shooter?": {
        "They were the most seriously injured": "Response 7-A",
        "They were the most likely to benefit from treatment at the next level of care.": "Response 7-B",
        "Command guidance and protocol.": "Response 7-C",
        "They were an innocent victim.": "Response 7-D"
    },
    "Adept Probe 10: Why did you choose to evac that casualty?": {
        "They were the most seriously injured.": "Response 10-A",
        "They were the most likely to benefit from treatment at the next level of care.": "Response 10-B",
        "US forces are always the highest priority.": "Response 10-C"
    }
}

ST_PROBES = {
    "delegation": {
        "qol-ph1-eval-2": ['qol-ph1-eval-2-Probe-1', 'qol-ph1-eval-2-Probe-2', 'qol-ph1-eval-2-Probe-3', 'qol-ph1-eval-2-Probe-4', 'qol-ph1-eval-2-Probe-5', 'qol-ph1-eval-2-Probe-6'],
        "qol-ph1-eval-3": ['qol-ph1-eval-3-Probe-1', 'qol-ph1-eval-3-Probe-2', 'qol-ph1-eval-3-Probe-3', 'qol-ph1-eval-3-Probe-4', 'qol-ph1-eval-3-Probe-5', 'qol-ph1-eval-3-Probe-6'],
        "qol-ph1-eval-4": ['qol-ph1-eval-4-Probe-1', 'qol-ph1-eval-4-Probe-2', 'qol-ph1-eval-4-Probe-3', 'qol-ph1-eval-4-Probe-4', 'qol-ph1-eval-4-Probe-5', 'qol-ph1-eval-4-Probe-6'],
        "vol-ph1-eval-2": ['vol-ph1-eval-2-Probe-1', 'vol-ph1-eval-2-Probe-2', 'vol-ph1-eval-2-Probe-3', 'vol-ph1-eval-2-Probe-4', 'vol-ph1-eval-2-Probe-5', 'vol-ph1-eval-2-Probe-6'],
        "vol-ph1-eval-3": ['vol-ph1-eval-3-Probe-1', 'vol-ph1-eval-3-Probe-2', 'vol-ph1-eval-3-Probe-3', 'vol-ph1-eval-3-Probe-4', 'vol-ph1-eval-3-Probe-5', 'vol-ph1-eval-3-Probe-6'],
        "vol-ph1-eval-4": ['vol-ph1-eval-4-Probe-1', 'vol-ph1-eval-4-Probe-2', 'vol-ph1-eval-4-Probe-3', 'vol-ph1-eval-4-Probe-4', 'vol-ph1-eval-4-Probe-5', 'vol-ph1-eval-4-Probe-6']
    },
    "all": {
        "qol-ph1-eval-2": ['qol-ph1-eval-2-Probe-1', 'qol-ph1-eval-2-Probe-2', 'qol-ph1-eval-2-Probe-3', 'qol-ph1-eval-2-Probe-4', 'qol-ph1-eval-2-Probe-5', 'qol-ph1-eval-2-Probe-6'],
        "qol-ph1-eval-3": ['qol-ph1-eval-3-Probe-1', 'qol-ph1-eval-3-Probe-2', 'qol-ph1-eval-3-Probe-3', 'qol-ph1-eval-3-Probe-4', 'qol-ph1-eval-3-Probe-5', 'qol-ph1-eval-3-Probe-6'],
        "qol-ph1-eval-4": ['qol-ph1-eval-4-Probe-1', 'qol-ph1-eval-4-Probe-2', 'qol-ph1-eval-4-Probe-3', 'qol-ph1-eval-4-Probe-4', 'qol-ph1-eval-4-Probe-5', 'qol-ph1-eval-4-Probe-6'],
        "vol-ph1-eval-2": ['vol-ph1-eval-2-Probe-1', 'vol-ph1-eval-2-Probe-2', 'vol-ph1-eval-2-Probe-3', 'vol-ph1-eval-2-Probe-4', 'vol-ph1-eval-2-Probe-5', 'vol-ph1-eval-2-Probe-6'],
        "vol-ph1-eval-3": ['vol-ph1-eval-3-Probe-1', 'vol-ph1-eval-3-Probe-2', 'vol-ph1-eval-3-Probe-3', 'vol-ph1-eval-3-Probe-4', 'vol-ph1-eval-3-Probe-5', 'vol-ph1-eval-3-Probe-6'],
        "vol-ph1-eval-4": ['vol-ph1-eval-4-Probe-1', 'vol-ph1-eval-4-Probe-2', 'vol-ph1-eval-4-Probe-3', 'vol-ph1-eval-4-Probe-4', 'vol-ph1-eval-4-Probe-5', 'vol-ph1-eval-4-Probe-6']
    }
}

AD_DEL_PROBES = {
    "DryRunEval-IO2-eval": ['Probe 4', 'Probe 8', 'Probe 9', 'Probe 9-B.1', 'Probe 9-A.1', 'Probe 10'],
    "DryRunEval-MJ2-eval": ['Probe 2B-1', 'Probe 2A-1', 'Response 3-B.2-B-gauze-v', 'Response 3-B.2-B-gauze-s', 'Response 3-B.2-A-gauze-v', 'Response 3-B.2-A-gauze-s', 'Probe 5', 'Probe 5-A.1', 'Probe 5-B.1', 'Probe 6', 'Probe 7'],
    "DryRunEval-IO4-eval": ['Probe 6', 'Probe 7', 'Probe 8', 'Probe 10'],
    "DryRunEval-MJ4-eval": ['Probe 1', 'Probe 2 kicker', 'Probe 2 passerby', 'Probe 2-A.1', 'Probe 2-D.1', 'Probe 2-D.1-B.1', 'Probe 3', 'Probe 3-A.1', 'Probe 3-B.1', 'Probe 9', 'Response 10-B', 'Response 10-C', 'Probe 10-A.1'],
    "DryRunEval-IO5-eval": ['Probe 7', 'Probe 8', 'Probe 8-A.1', 'Probe 8-A.1-A.1', 'Probe 9', 'Probe 9-A.1', 'Probe 9-B.1', 'Probe 9-C.1'],
    "DryRunEval-MJ5-eval": ['Probe 1', 'Probe 1-A.1', 'Probe 1-B.1', 'Probe 2', 'Response 2-A.1-B', 'Response 2-B.1-B', 'Response 2-B.1-B-gauze-u', 'Response 2-A.1-B-gauze-sp', 'Probe 2-A.1-A.1', 'Probe 2-B.1-A.1', 'Probe 2-A.1-B.1-A.1', 'Probe 2-B.1-B.1-A.1', 'Probe 3', 'Probe 4']
}

VITALS_ACTIONS = ["SpO2", "Breathing", "Pulse"]


ENV_MAP = {
    "phase1-soartech-eval-qol2.yaml": "qol-ph1-eval-2",
    "phase1-soartech-eval-qol3.yaml": "qol-ph1-eval-3",
    "phase1-soartech-eval-qol4.yaml": "qol-ph1-eval-4",
    "phase1-soartech-eval-vol2.yaml": "vol-ph1-eval-2",
    "phase1-soartech-eval-vol3.yaml": "vol-ph1-eval-3",
    "phase1-soartech-eval-vol4.yaml": "vol-ph1-eval-4",
    "phase1-adept-eval-MJ2.yaml": "DryRunEval-MJ2-eval",
    "phase1-adept-eval-MJ4.yaml": "DryRunEval-MJ4-eval",
    "phase1-adept-eval-MJ5.yaml": "DryRunEval-MJ5-eval"
}


mongo_collection_matches = None
mongo_collection_raw = None
text_scenario_collection = None
delegation_collection = None
medic_collection = None
adm_collection = None
mini_adms_collection = None
participant_log_collection = None
ENVIRONMENTS_BY_PID = {}


class ProbeMatcher:
    logger = Logger("probeMatcher")
    soartech_file = None
    adept_file = None
    soartech_yaml = None
    adept_yaml = None
    json_file = None
    json_data = None
    output_soartech = None
    output_adept = None
    participantId = ''
    environment = ''
    csv_file = None
    timestamp = None
    analyze = True
    pid_in_log = False


    def __init__(self, json_path, adept_sid, soartech_sid):
        '''
        Load in the file and parse the yaml
        '''
        self.adept_sid = adept_sid
        self.soartech_sid = soartech_sid
        # get environment from json to choose correct adept/soartech yamls
        self.json_file = open(json_path, 'r', encoding='utf-8')
        self.json_data = json.load(self.json_file)
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
            self.logger.log(LogLevel.WARN, "Environment not defined. Unable to process data")
            return
        self.environment = env
        print(self.environment)
        
        if pid in ENVIRONMENTS_BY_PID:
            ENVIRONMENTS_BY_PID[pid].append(self.environment)
        else:
            ENVIRONMENTS_BY_PID[pid] = [self.environment]
        # create output files
        try:
            os.mkdir('output')
        except:
            pass
        if 'Open World' in self.environment:
            pass
        elif 'adept' not in self.environment:
            filename = os.path.join('output', env.split('.yaml')[0] + f'_soartech_{pid}.json')
            if not self.should_file_run(filename):
                if RUN_COMPARISON:
                    self.output_soartech = open(filename, 'r', encoding='utf-8')
                return
            self.output_soartech = open(filename, 'w', encoding='utf-8')
        else:
            filename = os.path.join('output', env.split('.yaml')[0] + f'_adept_{pid}.json')
            if not self.should_file_run(filename): 
                if RUN_COMPARISON:
                    self.output_adept = open(filename, 'r', encoding='utf-8')
                return
            self.output_adept = open(filename, 'w', encoding='utf-8')
        # get soartech/adept yaml data
        if 'Open World' in env:
            pass
        elif 'qol' in env or 'vol' in env:
            self.soartech_file = open(os.path.join(os.path.join("phase1", "scenarios"), env), 'r', encoding='utf-8')
            try:
                self.soartech_yaml = yaml.load(self.soartech_file, Loader=yaml.CLoader)
            except Exception as e:
                self.logger.log(LogLevel.ERROR, "Error while loading in soartech yaml file. Please ensure the file is a valid yaml format and try again.\n\n" + str(e) + "\n")
        else:
            self.adept_file = open(os.path.join(os.path.join("phase1", "scenarios"), env), 'r', encoding='utf-8')
            try:
                self.adept_yaml = yaml.load(self.adept_file, Loader=yaml.CLoader)
            except Exception as e:
                self.logger.log(LogLevel.ERROR, "Error while loading in adept yaml file. Please ensure the file is a valid yaml format and try again.\n\n" + str(e) + "\n")
        self.clean_json()


    def __del__(self):
        '''
        Basic cleanup: closing the file loaded in on close.
        '''
        self.logger.log(LogLevel.DEBUG, "Program closing...")
        if (self.soartech_file):
            self.soartech_file.close()
        if (self.adept_file):
            self.adept_file.close()
        if (self.json_file):
            self.json_file.close()
        if (self.output_soartech):
            self.output_soartech.close()
        if (self.output_adept):
            self.output_adept.close()


    def should_file_run(self, filename):
        '''
        If RUN_ALL is False, looks to see if the input file already has a matching output file. If it does and:
            1. We are not running alignment OR
            2. We are running alignment and alignment has already been calculated for this file
        then return False in order to skip the analysis of this file.
        '''
        run_this_file = True
        mongo_id = None
        if 'adept' in self.environment:
            mongo_id = self.participantId + '_ad_' + self.environment.split('.yaml')[0]
        elif 'qol' in self.environment or 'vol' in self.environment:
            mongo_id = self.participantId + '_st_' + self.environment.split('.yaml')[0]
        else:
            mongo_id = self.participantId + '_dre_open_world'
        found = list(mongo_collection_matches.find({'_id': mongo_id}))
        if not RUN_ALL and ((SEND_TO_MONGO and len(found) > 0 and os.path.exists(filename)) or (not SEND_TO_MONGO and os.path.exists(filename))):
            if RERUN_ADEPT_SESSIONS and 'adept' in self.environment:
                return run_this_file
            if not RUN_ALIGNMENT:
                run_this_file = False
            if RUN_ALIGNMENT:
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
        if 'qol' in self.environment or 'vol' in self.environment:
            self.match_qol_vol_probes()
        elif 'adept' in self.environment:
            self.match_adept_probes()
        elif 'Open World' in self.environment:
            self.analyze_openworld()
        else:
            self.logger.log(LogLevel.WARN, f"No function available to probe match for environment {self.environment}")
    

    def analyze_openworld(self):
        results = {
            'pid': self.participantId,
            'assess_patient': 0,
            'assess_total': 0,
            'treat_patient': 0,
            'treat_total': 0,
            'triage_time': 0,
            'triage_time_patient': 0,
            'engage_patient': 0,
            'tag_acc': 0,
            'tag_expectant': False
        }

        ow_csv = open(self.json_file.name.replace('.json', '.csv'), 'r', encoding='utf-8')
        reader = csv.reader(ow_csv)
        header = next(reader)
        data = []
        for line in reader:
            data.append(line)

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
        results['engage_patient'] = sum(engagement_times) / max(1, len(engagement_times))
        

        def count_assessment_actions():
            '''returns the total count of assessment actions during the scenario'''
            assessment_actions = ['SP_O2_TAKEN', 'BREATHING_CHECKED', 'PULSE_TAKEN']
            count = 0
            last_done = {}
            per_patient = {}
            for x in data:
                # only count actions that are more than 5 seconds apart from the last of the same type of action
                if x[0] in assessment_actions and (x[0] not in last_done or (timestamp_to_milliseconds(x[2]) - last_done[x[0]]) > 5000):
                    last_done[x[0]] = timestamp_to_milliseconds(x[2])
                    count += 1
                    patient = x[header.index('PatientID')].split(' Root')[0]
                    if patient not in per_patient:
                        per_patient[patient] = 0
                    per_patient[patient] += 1
            return {'count': count, 'per_patient': per_patient}
        
        assessments = count_assessment_actions()
        results['assess_total'] = assessments['count']
        results['assess_patient'] = results['assess_total'] / max(1, patients_engaged)

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
        results['treat_total'] = treatments['count']
        results['treat_patient'] = results['treat_total'] / max(1, patients_treated)

        def get_triage_time():
            '''gets the time from start to finish (in seconds) to complete the scenario'''
            if len(data) > 0:
                start = float(data[0][1])
                end = float(data[len(data)-2][1])
                return ((end-start))/1000
            
        results['triage_time'] = get_triage_time()

        def get_tags():
            tags = {
                'US Soldier 1': 'red',
                'Civilian 1': 'red',
                'Attacker 1': 'red',
                'US Soldier 2': 'red',
                'US Soldier 3': 'gray',
                'Attacker 2': 'yellow_orange',
                'US Soldier 4': 'yellow_orange',
                'Civilian 2': 'red'
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
        results['tag_acc'] = tag_counts['correct'] / tag_counts['count']

        results['tag_expectant'] = 'Yes' if tag_counts['tags'].get('US Soldier 3') == 'gray' else 'No'


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
        results['triage_time_patient'] = triage_times['total'] / max(1, patients_engaged)

        def get_evaced_patients():
            answers = []
            answer_map = {
                "US Military Female Thigh Amputation": 'US Soldier 1',
                "US Military Female Calf Shrapnel": 'US Soldier 4',
                "US Military Male Stomach Puncture": 'US Soldier 2',
                "US Military Male Neck Puncture": 'US Soldier 3',
                "Civilian Child Thigh Amputation": 'Civilian 1',
                "Civilian Adult Calf Shrapnel": 'Civilian 2',
                "Attacker Teen Wrist Amputation": 'Attacker 1',
                "Attacker Adult Shoulder Puncture": 'Attacker 2'
            }
            for x in self.json_data['actionList']:
                if x['actionType'] == 'Question':
                    answers.append(answer_map[x['answer']])
            return answers
        
        evaced = get_evaced_patients()

        patients_in_order = ['US Soldier 1', 'Civilian 1', 'Attacker 1', 'US Soldier 2', 'US Soldier 3', 'Attacker 2', 'US Soldier 4', 'Civilian 2']
        clean_patient_order_engaged = []
        for x in patient_order_engaged:
            if x not in clean_patient_order_engaged:
                clean_patient_order_engaged.append(x)
        for i in range(len(patients_in_order)):
            name = f'Patient {i+1}'
            sim_name = patients_in_order[i]
            triage_time = triage_times['interactions'].get(sim_name, 0)
            results[f'{name}_time'] = triage_time
            try:
                results[f'{name}_order'] = clean_patient_order_engaged.index(sim_name) + 1
            except:
                results[f'{name}_order'] = 'N/A'
            results[f'{name}_evac'] = 'Yes' if sim_name in evaced else 'No'
            results[f'{name}_assess'] = assessments['per_patient'].get(sim_name, 0)
            results[f'{name}_treat'] = treatments['per_patient'].get(sim_name, 0)
            results[f'{name}_tag'] = tag_counts['tags'].get(sim_name, 'N/A')

        if SEND_TO_MONGO:
            mid = self.participantId + '_dre_open_world'
            try:
                mongo_collection_raw.insert_one({'openWorld': True, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': self.json_data, 'pid': self.participantId, '_id': self.participantId + '_' + self.environment.replace(' ', '-')})
            except:
                mongo_collection_raw.update_one({'_id': self.participantId + '_' + self.environment.replace(' ', '-')}, {'$set': {'openWorld': True, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': self.json_data, 'pid': self.participantId}})
            try:
                mongo_collection_matches.insert_one({'scenario_id': 'eval_open_world', 'timestamp': self.timestamp, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': results, 'openWorld': True, 'env': self.environment.split('.yaml')[0], 'pid': self.participantId, '_id': mid})
            except:
                mongo_collection_matches.update_one({'_id': mid}, {'$set': {'scenario_id': 'eval_open_world', 'timestamp': self.timestamp, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': results, 'openWorld': True, 'env': self.environment.split('.yaml')[0], 'pid': self.participantId, '_id': mid}})
            if self.pid_in_log:
                num_sim_found = mongo_collection_raw.count_documents({"pid": str(self.participantId)})
                participant_log_collection.update_one({'_id': participant_log_collection.find_one({"ParticipantID": int(self.participantId)})['_id']}, 
                                                      {'$set': {'claimed': True, "simEntryCount": num_sim_found}})


    def match_qol_vol_probes(self):
        soartech_scenes = self.soartech_yaml['scenes']
        last_action_ind_used = 0
        match_data = []
        total = 0
        found = 0
        updated_json = copy.deepcopy(self.json_data) # so we can update with missing probes
        # ST has no branching, so we can just go straight through the scenes
        for scene in soartech_scenes:
            actions = {} # {"Treatment": {"v": probe, "x": probe}, "Vitals": {"v": probe, "x": probe}, "Intent": {"v": probe, "x": probe}, etc}
            # get all available actions for the scene
            for probe_action in scene['action_mapping']:
                action_label = None
                if probe_action.get('intent_action', False):
                    action_label = 'Intend'
                else:
                    action_label = ACTION_TRANSLATION.get(probe_action['action_type'], None)
                if action_label is None:
                    if probe_action['action_type'] != 'END_SCENE':
                        self.logger.log(LogLevel.WARN, f"No action translation found for {probe_action['action_type']}")
                else:
                    if action_label not in actions:
                        if action_label not in ['None']:
                            actions[action_label] = {}
                        else:
                            actions[action_label] = []
                    # we are not checking specific treatments, so this is okay to overwrite
                    if 'character_id' in probe_action:
                            actions[action_label][probe_action['character_id']] = probe_action
                    else:
                        actions[action_label].append(probe_action)
            # go through actions taken until a match is found
            found_match = False
            total += 1
            matched = None
            for (ind, action_taken) in enumerate(self.json_data['actionList'][last_action_ind_used:]):
                if action_taken['actionType'] == 'Question' and 'Intend' in actions:
                    # fix for typo in vol scenarios - should be O vs U, but in some versions is O vs N
                    if action_taken['answer'] in ['N (35; TBI, forehead scrape)', 'N (36; TBI, forehead scrape)', 'N (37; TBI, face shrapnel)']:
                        action_taken['answer'] = 'U' + action_taken['answer'][1:]
                    answer = ('casualty_' + action_taken['answer'][0].strip()).lower()
                    if answer in actions['Intend']:
                        last_action_ind_used += ind + 1
                        found_match = True
                        matched = actions['Intend'][answer]
                        break
                elif action_taken['actionType'] in VITALS_ACTIONS and 'Vitals' in actions:
                    if action_taken['casualty'] in actions['Vitals']:
                        last_action_ind_used += ind + 1
                        found_match = True
                        matched = actions['Vitals'][action_taken['casualty']]
                        break
                elif action_taken['actionType'] in actions:
                    if scene['id'] == 'id-11' and 'qol' in self.environment:
                        # need to specifically check for lollipop treatment
                        if action_taken['casualty'] in actions[action_taken['actionType']] and action_taken['treatment'] == 'Fentanyl Lollipop':
                            last_action_ind_used += ind + 1
                            found_match = True
                            matched = actions[action_taken['actionType']][action_taken['casualty']]
                            break
                    elif action_taken['casualty'] in actions[action_taken['actionType']]:
                        last_action_ind_used += ind + 1
                        found_match = True
                        matched = actions[action_taken['actionType']][action_taken['casualty']]
                        break
            if found_match:
                found += 1
                match_data.append({
                    "scene_id": scene['id'],
                    "probe_id": matched['probe_id'],
                    "found_match": True,
                    "probe": matched,
                    "user_action": action_taken
                })

        print(f"Found {found} out of {total} probes")
        st_align = {}
        if RUN_ALIGNMENT:
            try:
                targets = [
                    'qol-human-8022671-SplitLowMulti-ph1', 'qol-human-6403274-SplitHighBinary-ph1', 'qol-human-3043871-SplitHighBinary-ph1', 
                    'qol-human-5032922-SplitLowMulti-ph1', 'qol-human-0000001-SplitEvenMulti-ph1', 'qol-human-7040555-SplitHighMulti-ph1',
                    'qol-synth-LowExtreme-ph1', 'qol-synth-HighExtreme-ph1', 'qol-synth-HighCluster-ph1', 'qol-synth-LowCluster-ph1', 
                    'vol-human-8022671-SplitHighMulti-ph1', 'vol-human-1774519-SplitHighMulti-ph1', 'vol-human-6403274-SplitEvenBinary-ph1', 
                    'vol-human-8478698-SplitLowMulti-ph1', 'vol-human-5032922-SplitLowMulti-ph1', 'vol-synth-LowExtreme-ph1', 'vol-synth-HighCluster-ph1',
                    'vol-synth-LowCluster-ph1'
                ]
                if EVAL_NUM != 12:
                    db_utils.send_probes(f'{ST_URL}api/v1/response', match_data, self.soartech_sid, self.soartech_yaml['id'])
                    for target in targets:
                        if ('vol' in target and 'vol' not in self.soartech_yaml['id']) or ('qol' in target and 'qol' not in self.soartech_yaml['id']):
                            continue
                        st_align[target] = self.get_session_alignment(f'{ST_URL}api/v1/alignment/session?session_id={self.soartech_sid}&target_id={target}')
                    st_align['kdmas'] = self.get_session_alignment(f'{ST_URL}api/v1/computed_kdma_profile?session_id={self.soartech_sid}')
                    st_align['sid'] = self.soartech_sid
            except:
                self.logger.log(LogLevel.WARN, "Session Alignment Get Request failed")
        match_data = {'alignment': st_align, 'data': match_data}
        if SEND_TO_MONGO:
            mid = self.participantId + '_st_' + self.environment.split('.yaml')[0]
            try:
                mongo_collection_matches.insert_one({'scenario_id': self.soartech_yaml['id'], 'timestamp': self.timestamp, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': match_data, 'ta1': 'st', 'env': self.environment.split('.yaml')[0], 'pid': self.participantId, '_id': mid})
            except:
                mongo_collection_matches.update_one({'_id': mid}, {'$set': {'scenario_id': self.soartech_yaml['id'], 'timestamp': self.timestamp, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': match_data, 'ta1': 'st', 'env': self.environment.split('.yaml')[0], 'pid': self.participantId, '_id': mid}})
            try:
                mongo_collection_raw.insert_one({'openWorld': False, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': updated_json, 'pid': self.participantId, '_id': self.participantId + '_' + self.environment})
            except:
                mongo_collection_raw.update_one({'_id': self.participantId + '_' + self.environment}, {'$set': {'openWorld': False, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': updated_json, 'pid': self.participantId, '_id': self.participantId + '_' + self.environment}})
            if self.pid_in_log:
                num_sim_found = mongo_collection_raw.count_documents({"pid": str(self.participantId)})
                participant_log_collection.update_one({'_id': participant_log_collection.find_one({"ParticipantID": int(self.participantId)})['_id']}, 
                                                      {'$set': {'claimed': True, "simEntryCount": num_sim_found}})
        
        json.dump(match_data, self.output_soartech, indent=4)  
                

    def get_scene_by_id(self, scenes, scene_id):
        for scene in scenes:
            if scene['id'] == scene_id:
                return scene
        return None


    def get_next_scene_by_index(self, scenes, this_scene):
        for i in range(len(scenes)-1):
            if scenes[i] == this_scene:
                return scenes[i+1]
        return None


    def match_adept_probes(self):
        adept_scenes = self.adept_yaml['scenes']
        last_action_ind_used = 0
        match_data = []
        found = 0
        total = 0
        looking_for_justify = False
        repeating_gauze = False
        stored_next_id = None
        if self.adept_yaml['id'] == 'DryRunEval-MJ4-eval':
            self.logger.log(LogLevel.INFO, f"Starting MJ4 probe matching for participant {self.participantId}")
        # Adept has branching, which makes things a little more difficult
        first_scene_id = self.adept_yaml.get('first_scene', self.adept_yaml['scenes'][0]['id'])
        cur_scene = self.get_scene_by_id(adept_scenes, first_scene_id)
        while True:
            if self.adept_yaml['id'] == 'DryRunEval-MJ4-eval':
                self.logger.log(LogLevel.INFO, f"Processing scene: {cur_scene['id']}")
            actions = {} # {"Treatment": {"v": probe, "x": probe}, "Vitals": {"v": probe, "x": probe}, "Intent": {"v": probe, "x": probe}, etc}
            # get all available actions for the scene
            
            for probe_action in cur_scene['action_mapping']:
                action_label = None
                if probe_action.get('intent_action', False):
                    action_label = 'Intend'
                else:
                    action_label = ACTION_TRANSLATION.get(probe_action['action_type'], None)
                if action_label is None:
                    self.logger.log(LogLevel.WARN, f"No action translation found for {probe_action['action_type']}")
                else:
                    if action_label not in actions:
                        if action_label not in ['Justify', 'None']:
                            actions[action_label] = {}
                        else:
                            actions[action_label] = []
                    # we might be checking specific treatments, so we need an array here (different from ST)
                    if 'character_id' in probe_action:
                        if action_label == 'Treatment':
                            if probe_action['character_id'] not in actions[action_label]:
                                actions[action_label][probe_action['character_id']] = []
                            actions[action_label][probe_action['character_id']].append(probe_action)
                        else:
                            actions[action_label][probe_action['character_id']] = probe_action
                    else:
                        actions[action_label].append(probe_action)
            if self.adept_yaml['id'] == 'DryRunEval-MJ4-eval':
                self.logger.log(LogLevel.INFO, f"Available actions for scene {cur_scene['id']}: {list(actions.keys())}")
            # go through actions taken until a match is found
            found_match = False
            total += 1
            matched = None
            for (ind, action_taken) in enumerate(self.json_data['actionList'][last_action_ind_used:]):
                if self.adept_yaml['id'] == 'DryRunEval-MJ4-eval':
                    self.logger.log(LogLevel.INFO, f"Checking action: {action_taken['actionType']} on {action_taken.get('casualty', 'N/A')}")
                if action_taken['casualty'] == 'US Soldier' and self.adept_yaml['id'] == 'DryRunEval-MJ4-eval':
                    action_taken['casualty'] = 'US soldier'
                # handles first probes of MJ2, which are "intent" probes, but we have actual actions
                if self.adept_yaml['id'] == 'DryRunEval-MJ2-eval' and 'Probe 2' in cur_scene['id'] and 'Intend' in actions and action_taken['actionType'] in ['ApproachPatient', "SpO2", "Breathing", "Pulse", 'Treatment']:
                    last_action_ind_used += ind
                    found_match = True
                    matched = actions['Intend'][action_taken['casualty']]
                    break
                # adept does not have dragging, dragPatient is MOVE_TO_EVAC
                elif action_taken['actionType'] == 'Question' and (('Intend' in actions or 'Justify' in actions or "Go" in actions or 'DragPatient' in actions) 
                                                                 or ('treat the attacker' in action_taken['question'] and cur_scene['id'] == 'Scene 3' and self.adept_yaml['id'] == 'DryRunEval-MJ5-eval')):
                    answer = None
                    if self.adept_yaml['id'] == 'DryRunEval-MJ5-eval' and 'Attacker' in action_taken['answerChoices']:
                        c_map = {"Attacker": "attacker", "US Soldier (Dixon)": "us_soldier", "Local Soldier (Upton)": "Upton", "Dixon and Upton (US and Local Soldier)": "Upton"}
                        answer = c_map[action_taken['answer']]
                    else:
                        answer = action_taken['answer'].split('(')[0].split(' -')[0].strip()
                        if answer == 'US Soldier' and self.adept_yaml['id'] == 'DryRunEval-MJ4-eval':
                            answer = 'US soldier'
                        if not repeating_gauze and answer == 'Soldier' and self.adept_yaml['id'] == 'DryRunEval-MJ2-eval':
                            answer = 'US military member'
                    # special mapping for treat attacker question
                    if 'treat the attacker' in action_taken['question'] and cur_scene['id'] == 'Scene 3' and self.adept_yaml['id'] == 'DryRunEval-MJ5-eval':
                        last_action_ind_used += ind
                        found_match = True
                        matched = cur_scene['action_mapping'][0] if action_taken['answer'] == 'No' else cur_scene['action_mapping'][1]
                        break
                    # special mapping for move/treat jungle question
                    elif "Treat US Soldier" in action_taken['answerChoices'] and 'Stay with Civilians' in action_taken['answerChoices'] and cur_scene['id'] == 'Scene 2' and self.adept_yaml['id'] == 'DryRunEval-MJ4-eval':
                        last_action_ind_used += ind
                        found_match = True
                        matched = cur_scene['action_mapping'][0] if 'Treat' in action_taken['answer'] else cur_scene['action_mapping'][1]
                        self.logger.log(LogLevel.INFO, f"MJ4 Scene 2 decision - Answer: {action_taken['answer']}, Matched probe: {matched.get('probe_id', 'N/A')}")
                        break   
                    # special mapping for move/stay urban questions
                    elif "Treat Soldier" in action_taken['answerChoices'] and 'Go Back to Shooter/Victim' in action_taken['answerChoices'] and cur_scene['id'] == 'Probe 4-B.1' and self.adept_yaml['id'] == 'DryRunEval-MJ2-eval':
                        last_action_ind_used += ind
                        found_match = True
                        matched = cur_scene['action_mapping'][2] if 'Treat' in action_taken['answer'] else cur_scene['action_mapping'][0]
                        break   
                    elif "Go to Soldier" in action_taken['answerChoices'] and 'Search for More Patients' in action_taken['answerChoices'] and cur_scene['id'] == 'Scene 2A' and self.adept_yaml['id'] == 'DryRunEval-MJ2-eval':
                        last_action_ind_used += ind
                        found_match = True
                        matched = cur_scene['action_mapping'][2] if 'Go to' in action_taken['answer'] else cur_scene['action_mapping'][3]
                        break   
                    elif "Assess Soldier" in action_taken['answerChoices'] and 'Go Back to Shooter/Victim' in action_taken['answerChoices'] and cur_scene['id'] == 'Scene 3' and self.adept_yaml['id'] == 'DryRunEval-MJ2-eval':
                        last_action_ind_used += ind
                        found_match = True
                        matched = cur_scene['action_mapping'][2] if 'Assess' in action_taken['answer'] else cur_scene['action_mapping'][0]
                        break   
                    elif 'Justify' in actions and looking_for_justify:
                        question = action_taken['question']
                        answer = action_taken['answer'].strip()

                        if question in JUSTIFY_MAPPING:
                            probe_choice = JUSTIFY_MAPPING[question].get(answer)
                            if probe_choice:
                                last_action_ind_used += ind
                                found_match = True
                                for x in cur_scene['action_mapping']:
                                    if x['choice'] == probe_choice:
                                        matched = x
                                        break
                                break

                    elif answer in actions.get('Intend', []):
                        last_action_ind_used += ind
                        found_match = True
                        matched = actions['Intend'][answer]
                        break
                    elif answer in actions.get('Go', []):
                        last_action_ind_used += ind
                        found_match = True
                        matched = actions['Go'][answer]
                        break
                    elif answer in actions.get('DragPatient', []):
                        last_action_ind_used += ind
                        found_match = True
                        matched = actions['DragPatient'][answer]
                        break
                elif action_taken['actionType'] in VITALS_ACTIONS:
                    # Priority 1: Strict Vitals Match
                    if 'Vitals' in actions and action_taken['casualty'] in actions['Vitals']:
                        last_action_ind_used += ind
                        found_match = True
                        matched = actions['Vitals'][action_taken['casualty']]
                        if self.adept_yaml['id'] == 'DryRunEval-MJ4-eval':
                            self.logger.log(LogLevel.INFO, f"Vitals action matched for {action_taken['casualty']}")
                        break
                    # Priority 2: Loose Rule - Map Vitals action to Treatment probe
                    elif 'Treatment' in actions and action_taken['casualty'] in actions['Treatment']:
                        last_action_ind_used += ind
                        found_match = True
                        # Get all treatment options for this casualty
                        char_actions = actions['Treatment'][action_taken['casualty']]
                        
                        # Logic to select the best treatment probe 
                        # (Prefer generic treatments since Vitals don't imply blood/gauze)
                        if len(char_actions) == 1:
                            matched = char_actions[0]
                        else:
                            default = None
                            for x in char_actions:
                                # Look for generic treatment or specific generic marker
                                if x.get('parameters', {}).get('treatment', None) is None or x.get('action_id') == "treat_kicker_but_dont_give_blood":
                                    default = x
                                    break
                            # Use generic if found, otherwise default to first available treatment
                            matched = default if default is not None else char_actions[0]
                            
                        if self.adept_yaml['id'] == 'DryRunEval-MJ4-eval':
                            self.logger.log(LogLevel.INFO, f"Vitals action LOOSELY matched as Treatment for {action_taken['casualty']}")
                        break
                elif action_taken['actionType'] in actions:
                    if action_taken['casualty'] in actions[action_taken['actionType']]:
                        last_action_ind_used += ind
                        found_match = True
                        if action_taken['actionType'] == 'Treatment':
                            char_actions = actions[action_taken['actionType']][action_taken['casualty']]
                            if len(char_actions) == 1:
                                matched = char_actions[0]
                            else:
                                default = None
                                treatment_mapping = {"IV - Blood": "Blood", "Hemostatic Gauze": "Hemostatic gauze"}
                                for x in char_actions:
                                    if x.get('parameters', {}).get('treatment', None) is None or x.get('action_id') == "treat_kicker_but_dont_give_blood":
                                        default = x
                                    elif x.get('parameters', {}).get('treatment', None) == treatment_mapping.get(action_taken['treatment'], action_taken['treatment']):
                                        matched = x
                                        break
                                if matched is None:
                                    matched = default
                        else:
                            matched = actions[action_taken['actionType']][action_taken['casualty']]
                        if self.adept_yaml['id'] == 'DryRunEval-MJ4-eval':
                            self.logger.log(LogLevel.INFO, f"Treatment action matched: {action_taken['treatment']} on {action_taken['casualty']}")
                        break
            if self.adept_yaml['id'] == 'DryRunEval-MJ4-eval' and found_match:
                self.logger.log(LogLevel.INFO, f"MATCH FOUND - Scene: {cur_scene['id']}, Probe: {matched.get('probe_id', 'N/A')}, Action: {action_taken['actionType']}")
            if found_match or len(cur_scene['action_mapping']) == 1 or 'None' in actions:
                if len(cur_scene['action_mapping']) == 1:
                    # some adept scenes are just there for transitions and don't really require action
                    matched = cur_scene['action_mapping'][0]
                    if self.adept_yaml['id'] == 'DryRunEval-MJ4-eval':
                        self.logger.log(LogLevel.INFO, f"Single-action scene: {cur_scene['id']}, Auto-matched probe: {matched.get('probe_id', 'N/A')}")
                elif not found_match and 'None' in actions:
                    matched = actions['None'][0]
                    if self.adept_yaml['id'] == 'DryRunEval-MJ4-eval':
                        self.logger.log(LogLevel.INFO, f"None-action scene: {cur_scene['id']}, Auto-matched probe: {matched.get('probe_id', 'N/A')}")
                else:
                    # need to start looking at _next_ index, not this index!
                    last_action_ind_used += 1
                found += 1
                match_data.append({
                    "scene_id": cur_scene['id'],
                    "probe_id": matched['probe_id'],
                    "found_match": True,
                    "probe": matched,
                    "user_action": action_taken if found_match else None
                })   
                if self.adept_yaml['id'] == 'DryRunEval-MJ4-eval':
                    next_scene = matched.get('next_scene', cur_scene.get('next_scene'))
                    self.logger.log(LogLevel.INFO, f"Transitioning from {cur_scene['id']} to {next_scene}")         
                if self.adept_yaml['id'] == 'DryRunEval-MJ2-eval' and matched.get('next_scene', cur_scene.get('next_scene')) == 'Probe 4-B.1-B.1':
                    # if intend to treat US soldier, mark the next probe as "treat US soldier"
                    found += 1
                    total += 1
                    cur_scene = self.get_scene_by_id(adept_scenes, 'Probe 4-B.1-B.1')
                    matched = cur_scene['action_mapping'][2]
                    if matched.get('choice') == "Response 9-C.1-A":
                        matched['unstructured'] = "Move Upton and US soldier to evac."
                    match_data.append({
                        "scene_id": 'Probe 4-B.1-B.1',
                        "probe_id": matched['probe_id'],
                        "found_match": True,
                        "probe": matched,
                        "user_action": None
                    })    
                if self.adept_yaml['id'] == 'DryRunEval-MJ2-eval' and matched.get('next_scene', cur_scene.get('next_scene')) == 'Transition to Scene 4':
                    # scene 4 is a transition scene, does not require user action    
                    found += 1
                    total += 1
                    cur_scene = self.get_scene_by_id(adept_scenes, 'Transition to Scene 4')
                    matched = cur_scene['action_mapping'][0]
                    match_data.append({
                        "scene_id": 'Transition to Scene 4',
                        "probe_id": matched['probe_id'],
                        "found_match": True,
                        "probe": matched,
                        "user_action": None
                    })   
                if self.adept_yaml['id'] == 'DryRunEval-MJ4-eval' and matched.get('next_scene', cur_scene.get('next_scene')) == 'Transition to Scene 2':
                    # another transition scene, does not require user action    
                    found += 1
                    total += 1
                    cur_scene = self.get_scene_by_id(adept_scenes, 'Transition to Scene 2')
                    matched = cur_scene['action_mapping'][0]
                    match_data.append({
                        "scene_id": 'Transition to Scene 2',
                        "probe_id": matched['probe_id'],
                        "found_match": True,
                        "probe": matched,
                        "user_action": None
                    })   
                # need to see if there is also a justify action
                if not looking_for_justify and 'Justify' in actions:
                    looking_for_justify = True
                    repeating_gauze = False
                    stored_next_id = matched.get('next_scene', cur_scene.get('next_scene'))
                # need to see if this is a multiple gauze question
                elif ((self.adept_yaml['id'] == 'DryRunEval-MJ2-eval' and cur_scene['id'] == 'Scene 2A' and matched['choice'] in ['Response 3-B.2-A-gauze-s', 'Response 3-B.2-B-gauze-v']) \
                    or (self.adept_yaml['id'] == 'DryRunEval-MJ5-eval' and cur_scene['id'] == 'Probe 3' and matched['choice'] in ['Response 3-A-gauze-sp', 'Response 3-B-gauze-u'])):
                    # Scene 2A in MJ2 (Urban) is repeatable for gauze applications
                    # Probe 3 in MJ5 (Desert) is repeatable for gauze applications 
                    repeating_gauze = True
                    looking_for_justify = False
                    stored_next_id = matched.get('next_scene', cur_scene.get('next_scene'))
                else:
                    looking_for_justify = False
                    repeating_gauze = False
                    next_scene_id = matched.get('next_scene', cur_scene.get('next_scene'))
                    if next_scene_id is not None:
                        cur_scene = self.get_scene_by_id(adept_scenes, next_scene_id)
                    else:
                        break
                    if cur_scene is None:
                        break
            else:
                if self.adept_yaml['id'] == 'DryRunEval-MJ4-eval':
                    self.logger.log(LogLevel.WARN, f"NO MATCH FOUND for scene: {cur_scene['id']}")
                if looking_for_justify or repeating_gauze:
                    looking_for_justify = False
                    repeating_gauze = False
                    if stored_next_id is not None:
                        cur_scene = self.get_scene_by_id(adept_scenes, stored_next_id)
                    else:
                        break
                    stored_next_id = None
                    if cur_scene is None:
                        break                    
                self.logger.log(LogLevel.WARN, f'Could not find match for scene "{cur_scene["id"]}"')
                if cur_scene['id'] == 'Probe 9' and self.adept_yaml['id'] == 'DryRunEval-MJ4-eval':
                    cur_scene = self.get_scene_by_id(adept_scenes, 'Probe 10')
                else:
                    break
        print(f"Found {found} out of {total} probes")
        ad_align = {}
        if RUN_ALIGNMENT:
            try:
                db_utils.send_probes(f'{ADEPT_URL}api/v1/response', match_data, self.adept_sid, self.adept_yaml['id'])
                mj_targets = self.get_session_alignment(f'{ADEPT_URL}api/v1/get_ordered_alignment?session_id={self.adept_sid}&population=false&kdma_id=Moral%20judgement')
                io_targets = self.get_session_alignment(f'{ADEPT_URL}api/v1/get_ordered_alignment?session_id={self.adept_sid}&population=false&kdma_id=Ingroup%20Bias')
                targets = mj_targets + io_targets
                for target in targets:
                    if target is not None:
                        k = list(target.keys())[0]
                        v = target[k]
                        ad_align[k] = v
                ad_align['kdmas'] = self.get_session_alignment(f'{ADEPT_URL}api/v1/computed_kdma_profile?session_id={self.adept_sid}')
                ad_align['sid'] = self.adept_sid
            except:
                self.logger.log(LogLevel.WARN, "Session Alignment Get Request failed")
        match_data = {'alignment': ad_align, 'data': match_data}
        if SEND_TO_MONGO:
            mid = self.participantId + '_ad_' + self.environment.split('.yaml')[0]
            try:
                mongo_collection_matches.insert_one({'scenario_id': self.adept_yaml['id'], 'timestamp': self.timestamp, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': match_data, 'ta1': 'ad', 'env': self.environment.split('.yaml')[0], 'pid': self.participantId, '_id': mid})
            except:
                mongo_collection_matches.update_one({'_id': mid}, {'$set': {'scenario_id': self.adept_yaml['id'], 'timestamp': self.timestamp, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': match_data, 'ta1': 'ad', 'env': self.environment.split('.yaml')[0], 'pid': self.participantId, '_id': mid}})
            try:
                mongo_collection_raw.insert_one({'openWorld': False, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': self.json_data, 'pid': self.participantId, '_id': self.participantId + '_' + self.environment})
            except:
                mongo_collection_raw.update_one({'_id': self.participantId + '_' + self.environment}, {'$set': {'openWorld': False, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': self.json_data, 'pid': self.participantId, '_id': self.participantId + '_' + self.environment}})
            if self.pid_in_log:
                num_sim_found = mongo_collection_raw.count_documents({"pid": str(self.participantId)})
                participant_log_collection.update_one({'_id': participant_log_collection.find_one({"ParticipantID": int(self.participantId)})['_id']}, 
                                                      {'$set': {'claimed': True, "simEntryCount": num_sim_found}})
        json.dump(match_data, self.output_adept, indent=4)  


    def get_session_alignment(self, align_url):
        '''
        Returns the session alignment
        '''
        return requests.get(align_url).json()
    

    def run_comparison(self):
        '''
        Runs VR vs Text alignment comparison and VR vs ADM alignment comparison for 
        the current sim scenario. Adds the result to the output jsons and to mongo
        '''
        if 'qol' not in self.environment and 'vol' not in self.environment and 'adept' not in self.environment:
            return
        vr_sid = None
        failed_mongo_check = False
        json_data = None
        f = None
        if 'qol' in self.environment or 'vol' in self.environment:
            f = self.output_soartech
        elif 'adept' in self.environment:
            f = self.output_adept
        else:
            return
        filename = f.name
        f.close()
        if SEND_TO_MONGO:
            mongo_id = None
            if 'adept' in self.environment:
                mongo_id = self.participantId + '_ad_' + self.environment.split('.yaml')[0]
            elif 'qol' in self.environment or 'vol' in self.environment:
                mongo_id = self.participantId + '_st_' + self.environment.split('.yaml')[0]
            else:
                mongo_id = self.participantId + '_dre_open_world'
            found = list(mongo_collection_matches.find({'_id': mongo_id}))
            if not found or len(found) == 0:
                self.logger.log(LogLevel.WARN, "Error getting data from mongo for comparison. Using local file as backup. KDMAs may be lost")
            else:
                json_data = found[0]['data']
        if not SEND_TO_MONGO or failed_mongo_check:
            readable = open(filename, 'r', encoding='utf-8')
            json_data = json.load(readable)
            readable.close()
        vr_sid = json_data.get('alignment', {}).get('sid')
        if vr_sid is None:
            self.logger.log(LogLevel.WARN, "Error getting session id. Maybe alignment hasn't run for file?")
            return
        # do not recalculate score if it's already done!
        if RECALCULATE_COMPARISON or not (json_data.get('alignment').get('vr_vs_text', None) is not None and not RUN_ALL):
            comparison = self.get_text_vr_comparison(vr_sid)
            if comparison is not None:
                json_data['alignment']['vr_vs_text'] = comparison
                writable = open(filename, 'w', encoding='utf-8')
                json.dump(json_data, writable, indent=4)
                writable.close()

        adms_vs_text = json_data.get('alignment').get('adms_vs_text', [])
        if EVAL_NUM != 12 and (RECALCULATE_COMPARISON or not (adms_vs_text is not None and len(adms_vs_text) > 0 and not RUN_ALL)):
            comparison = self.get_adm_vr_comparisons(vr_sid)
            if comparison is not None:
                json_data['alignment']['adms_vs_text'] = comparison
                writable = open(filename, 'w', encoding='utf-8')
                json.dump(json_data, writable, indent=4)
                writable.close()
        if SEND_TO_MONGO:
            mid = self.participantId + ('_st_' if 'qol' in self.environment or 'vol' in self.environment else '_ad_')  + self.environment.split('.yaml')[0]
            try:
                mongo_collection_matches.update_one({'_id': mid}, {'$set': { 'data.alignment': json_data.get('alignment')}})
            except:
                self.logger.log(LogLevel.WARN, f"No mongo document found with id {mid}! Cannot update document with comparison scores.")


    def get_text_vr_comparison(self, vr_sid):
        res = None
        if 'qol' in self.environment or 'vol' in self.environment:
            vr_scenario = ENV_MAP[self.environment]

            # VR session vs text scenario (ST)
            text_response = text_scenario_collection.find_one({"evalNumber": EVAL_NUM, 'participantID': self.participantId, 'scenario_id': {"$regex": vr_scenario.split('-')[0], "$options": "i"}})
            if text_response is None:
                self.logger.log(LogLevel.WARN, f"Error getting text response for pid {self.participantId} {vr_scenario.split('-')[0]} scenario")
                return None
            text_sid = text_response['serverSessionId']
            text_scenario = text_response['scenario_id']
            
            # send all probes to ST server for VR vs text
            query_param = f"session_1={vr_sid}&session_2={text_sid}"
            for probe_id in ST_PROBES['all'][vr_scenario]:
                query_param += f"&session1_probes={probe_id}"
            for probe_id in ST_PROBES['all'][text_scenario]:
                query_param += f"&session2_probes={probe_id}"
            if EVAL_NUM != 12:
                res = requests.get(f'{ST_URL}api/v1/alignment/session/subset?{query_param}').json()
                if res is None or 'score' not in res:
                    self.logger.log(LogLevel.WARN, "Error getting comparison score (soartech). Perhaps not all probes have been completed in the sim?")
                    return
                res = res['score']
        elif 'adept' in self.environment:
            # get text session id
            text_response = text_scenario_collection.find_one({"evalNumber": EVAL_NUM, 'participantID': self.participantId, 'scenario_id': {"$in": ["DryRunEval-MJ2-eval", "DryRunEval-MJ4-eval", "DryRunEval-MJ5-eval", 'phase1-adept-eval-MJ2', 'phase1-adept-eval-MJ4', 'phase1-adept-eval-MJ5']}})
            if text_response is None:
                self.logger.log(LogLevel.WARN, f"Error getting text response for pid {self.participantId} adept scenario")
                return None
            text_sid = text_response['combinedSessionId']
            # send text and vr session ids to Adept server
            res_mj = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions_population?session_id_1_or_target_id={vr_sid}&session_id_2_or_target_id={text_sid}&target_pop_id=ADEPT-DryRun-Moral%20judgement-Population-All').json()
            res_io = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions_population?session_id_1_or_target_id={vr_sid}&session_id_2_or_target_id={text_sid}&target_pop_id=ADEPT-DryRun-Ingroup%20Bias-Population-All').json()
            res = {'MJ': None, 'IO': None}
            if res_mj is not None:
                if 'score' not in res_mj:
                    self.logger.log(LogLevel.WARN, "Error getting comparison score (adept, MJ). You may have to rerun alignment to get a new adept session id.")
                else:
                    res['MJ'] = res_mj['score']
            if res_io is not None:
                if 'score' not in res_io:
                    self.logger.log(LogLevel.WARN, "Error getting comparison score (adept, IO). You may have to rerun alignment to get a new adept session id.")
                else:
                    res['IO'] = res_io['score']
        return res


    def get_adm_vr_comparisons(self, vr_sid):
        # get the survey
        survey = delegation_collection.find_one({"results.Participant ID Page.questions.Participant ID.response": self.participantId})
        results = []
        vr_scenario = ENV_MAP[self.environment]
        # get all adms shown in delegation that match the attribute
        if not survey or survey.get('results') is None:
            self.logger.log(LogLevel.WARN, "Could not find survey for " + self.participantId)
            return []
        for page in survey.get('results', []):
            if 'Medic' in page and ' vs ' not in page:
                page_scenario = survey['results'][page]['scenarioIndex']
                if ('qol' in self.environment and 'qol' in page_scenario) or ('vol' in self.environment and 'vol' in page_scenario):
                    # find the adm session id that matches the medic shown in the delegation survey
                    adm = db_utils.find_adm_from_medic(EVAL_NUM, medic_collection, adm_collection, page, page_scenario, survey)
                    if adm is None:
                        continue
                    adm_session = adm['history'][len(adm['history'])-1]['parameters']['session_id']
                    # create ST query param
                    query_param = f"session_1={vr_sid}&session_2={adm_session}"
                    for probe_id in ST_PROBES['delegation'][vr_scenario]:
                        query_param += f"&session1_probes={probe_id}"
                    for probe_id in ST_PROBES['delegation'][page_scenario]:
                        query_param += f"&session2_probes={probe_id}"
                    # get comparison score
                    if EVAL_NUM != 12:
                        res = requests.get(f'{ST_URL}api/v1/alignment/session/subset?{query_param}').json()
                        if 'score' not in res:
                            self.logger.log(LogLevel.WARN, "Error getting comparison score (soartech). Perhaps not all probes have been completed in the sim?")
                        else:
                            results.append({
                                "score": res['score'],
                                "adm_author": survey['results'][page]['admAuthor'],
                                "adm_alignment": survey['results'][page]['admAlignment'],
                                'adm_name': survey['results'][page]['admName'],
                                'adm_target': survey['results'][page]['admTarget'],
                                'adm_scenario': page_scenario,
                                'sim_scenario': vr_scenario
                            })
                elif ('adept' in self.environment and 'DryRunEval' in page_scenario):
                    adm = db_utils.find_adm_from_medic(EVAL_NUM, medic_collection, adm_collection, page, page_scenario.replace('IO', 'MJ'), survey)
                    if adm is None:
                        continue
                    adm_target = adm['history'][len(adm['history'])-1]['parameters']['target_id']
                    found_mini_adm = mini_adms_collection.find_one({'target': adm_target, 'scenario': page_scenario.replace('IO', 'MJ'), 'adm_name': survey['results'][page]['admName'], 'evalNumber': EVAL_NUM})
                    if found_mini_adm is None:
                        # get new adm session that contains only the probes seen in the delegation survey
                        probe_ids = AD_DEL_PROBES[page_scenario] # this is where IO/MJ comes into play - choosing the probes
                        probe_responses = []
                        for x in adm['history']:
                            if x['command'] == 'Respond to TA1 Probe':
                                if x['parameters']['choice'] in probe_ids or x['parameters']['probe_id'] in probe_ids:
                                    probe_responses.append(x['parameters'])
                        found_mini_adm = db_utils.mini_adm_run(EVAL_NUM, mini_adms_collection, probe_responses, adm_target, survey['results'][page]['admName'])
                    res = None
                    if 'Moral' in adm_target:
                        res = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions_population?session_id_1_or_target_id={vr_sid}&session_id_2_or_target_id={found_mini_adm["session_id"]}&target_pop_id=ADEPT-DryRun-Moral%20judgement-Population-All').json()
                    else:
                        res = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions_population?session_id_1_or_target_id={vr_sid}&session_id_2_or_target_id={found_mini_adm["session_id"]}&target_pop_id=ADEPT-DryRun-Ingroup%20Bias-Population-All').json()
                    if 'score' not in res:
                        self.logger.log(LogLevel.WARN, "Error getting comparison score (adept). You may have to rerun alignment to get a new adept session id.")
                    else:
                        results.append({
                            "score": res['score'],
                            "adm_author": survey['results'][page]['admAuthor'],
                            "adm_alignment": survey['results'][page]['admAlignment'],
                            'adm_name': survey['results'][page]['admName'],
                            'adm_target': survey['results'][page]['admTarget'],
                            'adm_scenario': page_scenario,
                            'sim_scenario': vr_scenario
                        })
        return results

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='ITM - Probe Matcher', usage='probe_matcher.py [-h] -i [-w] PATH')

    parser.add_argument('-i', '--input_dir', dest='input_dir', type=str, help='The path to the directory where all participant files are. Required.')
    parser.add_argument('-w', '--weekly', action='store_true', dest='is_weekly', help='A flag to determine if this is a weekly run. If weekly, global variables change.')
    parser.add_argument('-e', '--eval_num', dest='eval_num', type=int, help="The eval number to use during runtime")
    args = parser.parse_args()
    removed = []
    if not args.input_dir:
        print("Input directory (-i PATH) is required to run the probe matcher.")
        exit(1)
    if args.is_weekly:
        # should only run new files, and run alignment/comparisons for those missing it
        SEND_TO_MONGO = True 
        RUN_ALIGNMENT = True 
        RUN_ALL = False 
        RUN_COMPARISON = True 
        RECALCULATE_COMPARISON = True
        RERUN_ADEPT_SESSIONS = True
    if args.eval_num:
        if args.eval_num == 5:
            EVAL_NAME = 'Phase 1 Evaluation'
            EVAL_NUM = 5
        if args.eval_num == 6:
            EVAL_NAME = 'Jan 2025 Eval'
            EVAL_NUM = 6
        if args.eval_num == 12:
            EVAL_NAME = 'Eval 12 UK Phase 1'
            EVAL_NUM = 12
    # instantiate mongo client
    client = MongoClient(config('MONGO_URL'))
    db = client.dashboard
    if SEND_TO_MONGO:
        # create new collection for simulation runs
        mongo_collection_matches = db['humanSimulator']
        mongo_collection_raw = db['humanSimulatorRaw']
        text_scenario_collection = db['userScenarioResults']
        delegation_collection = db['surveyResults']
        medic_collection = db['admMedics']
        adm_collection = db["admTargetRuns"]
        mini_adms_collection = db['delegationADMRuns']
    participant_log_collection = db['participantLog']

    # go through the input directory and find all sub directories
    sub_dirs = [name for name in os.listdir(args.input_dir) if os.path.isdir(os.path.join(args.input_dir, name))]
    # for each subdirectory, see if a json file exists
    for dir in sub_dirs:
        parent = os.path.join(args.input_dir, dir)
        # get date of sim
        csv_file = open(os.path.join(parent, dir+'.csv'), 'r', encoding='utf-8')
        reader = csv.reader(csv_file)
        next(reader)
        line2 = next(reader)
        sim_date = datetime.strptime(line2[2], "%m/%d/%Y %I:%M:%S %p")
        ph1_date = datetime(2024, 11, 24)
        # if date is after 11/24, we are good! This is part of phase 1
        valid_date = sim_date > ph1_date
        # remove files that have invalid pids
        pid = dir.split('_')[-1]
        try:
            pid = int(pid)
        except:
            os.system(f'rm -rf {os.path.join(parent)}')
            removed.append(parent)
            continue
        pid_in_log = participant_log_collection.count_documents({"ParticipantID": int(pid)}) > 0

        if not pid_in_log or not valid_date:
            os.system(f'rm -rf {parent}')
            removed.append(parent)
            continue
        
        if os.path.isdir(parent):
            for f in os.listdir(parent):
                if '.json' in f:
                    print(f"\n** Processing {f} **")
                    # json found! grab matching csv and send to the probe matcher
                    # try:
                    adept_sid = requests.post(f'{ADEPT_URL}api/v1/new_session').text.replace('"', '').strip()
                    if EVAL_NUM != 12:
                        soartech_sid = requests.post(f'{ST_URL}api/v1/new_session?user_id=default_use').json()
                    else:
                        soartech_sid = 123
                    matcher = ProbeMatcher(os.path.join(parent, f), adept_sid, soartech_sid)
                    # matcher = ProbeMatcher(os.path.join(parent, f), None, None) # use this for basic matching testing when SSL is not working
                    if matcher.environment != '' and matcher.analyze:
                        matcher.match_probes()
                    if matcher.environment != '' and RUN_COMPARISON:
                        matcher.run_comparison()
                    matcher.__del__()
                    # except Exception as e:
                    #     print(e)
                elif '.html' in f or '.jpg' in f:
                    os.remove(os.path.join(parent, f))
    print()
    print('Removed:', removed)
