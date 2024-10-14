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
RUN_ALL = False  # run all files in the input directory, even if they have already been run/analyzed, if true
RUN_COMPARISON = True # run the vr/text and vr/adm comparisons, whether RUN_ALL is True or False
RECALCULATE_COMPARISON = True
RERUN_ADEPT_SESSIONS = True # rerun adept sessions only to get new session ids
EVAL_NUM = 4
EVAL_NAME = 'Dry Run Evaluation'

ADEPT_URL = "https://darpaitm.caci.com/adept/" # config("ADEPT_URL")
ST_URL = "https://darpaitm.caci.com/soartech/" # config("ST_URL")

SCENE_MAP = {
    "qol-dre-1-eval Narrative": "dryrun-soartech-eval-qol1.yaml",
    "qol-dre-2-eval Narrative": "dryrun-soartech-eval-qol2.yaml",
    "qol-dre-3-eval Narrative": "dryrun-soartech-eval-qol3.yaml",
    "vol-dre-1-eval Narrative": "dryrun-soartech-eval-vol1.yaml",
    "vol-dre-2-eval Narrative": "dryrun-soartech-eval-vol2.yaml",
    "vol-dre-3-eval Narrative": "dryrun-soartech-eval-vol3.yaml",
    "DryRunEval-MJ2-eval Narrative": "dryrun-adept-eval-MJ2.yaml",
    "DryRunEval-MJ4-eval Narrative": "dryrun-adept-eval-MJ4.yaml",
    "DryRunEval-MJ5-eval Narrative": "dryrun-adept-eval-MJ5.yaml",
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
        "qol-dre-1-eval": ['4.2', '4.3', '4.6', '4.7', '4.10', 'qol-dre-train2-Probe-11'],
        "qol-dre-2-eval": ['qol-dre-2-eval-Probe-2', 'qol-dre-2-eval-Probe-3', 'qol-dre-2-eval-Probe-6', 'qol-dre-2-eval-Probe-7', 'qol-dre-2-eval-Probe-10', 'qol-dre-2-eval-Probe-11'],
        "qol-dre-3-eval": ['qol-dre-3-eval-Probe-2', 'qol-dre-3-eval-Probe-3', 'qol-dre-3-eval-Probe-6', 'qol-dre-3-eval-Probe-7', 'qol-dre-3-eval-Probe-10', 'qol-dre-3-eval-Probe-11'],
        "vol-dre-1-eval": ['4.2', '4.3', '4.6', '4.7', '4.10', 'vol-dre-train2-Probe-11'],
        "vol-dre-2-eval": ['vol-dre-2-eval-Probe-2', 'vol-dre-2-eval-Probe-3', 'vol-dre-2-eval-Probe-6', 'vol-dre-2-eval-Probe-7', 'vol-dre-2-eval-Probe-10', 'vol-dre-2-eval-Probe-11'],
        "vol-dre-3-eval": ['vol-dre-3-eval-Probe-2', 'vol-dre-3-eval-Probe-3', 'vol-dre-3-eval-Probe-6', 'vol-dre-3-eval-Probe-7', 'vol-dre-3-eval-Probe-10', 'vol-dre-3-eval-Probe-11']
    },
    "all": {
        "qol-dre-1-eval": ['4.1', '4.2', '4.3', '4.4', '4.5', '4.6', '4.7', '4.8', '4.9', '4.10', 'qol-dre-train2-Probe-11', '12'],
        "qol-dre-2-eval": ['qol-dre-2-eval-Probe-1', 'qol-dre-2-eval-Probe-2', 'qol-dre-2-eval-Probe-3', 'qol-dre-2-eval-Probe-4', 'qol-dre-2-eval-Probe-5', 'qol-dre-2-eval-Probe-6', 'qol-dre-2-eval-Probe-7', 'qol-dre-2-eval-Probe-8', 'qol-dre-2-eval-Probe-9', 'qol-dre-2-eval-Probe-10', 'qol-dre-2-eval-Probe-11', 'qol-dre-2-eval-Probe-12'],
        "qol-dre-3-eval": ['qol-dre-3-eval-Probe-1', 'qol-dre-3-eval-Probe-2', 'qol-dre-3-eval-Probe-3', 'qol-dre-3-eval-Probe-4', 'qol-dre-3-eval-Probe-5', 'qol-dre-3-eval-Probe-6', 'qol-dre-3-eval-Probe-7', 'qol-dre-3-eval-Probe-8', 'qol-dre-3-eval-Probe-9', 'qol-dre-3-eval-Probe-10', 'qol-dre-3-eval-Probe-11', 'qol-dre-3-eval-Probe-12'],
        "vol-dre-1-eval": ['4.1', '4.2', '4.3', '4.4', '4.5', '4.6', '4.7', '4.8', '4.9', '4.10', 'vol-dre-train2-Probe-11', 'vol-dre-train2-Probe-12'],
        "vol-dre-2-eval": ['vol-dre-2-eval-Probe-1', 'vol-dre-2-eval-Probe-2', 'vol-dre-2-eval-Probe-3', 'vol-dre-2-eval-Probe-4', 'vol-dre-2-eval-Probe-5', 'vol-dre-2-eval-Probe-6', 'vol-dre-2-eval-Probe-7', 'vol-dre-2-eval-Probe-8', 'vol-dre-2-eval-Probe-9', 'vol-dre-2-eval-Probe-10', 'vol-dre-2-eval-Probe-11', 'vol-dre-2-eval-Probe-12'],
        "vol-dre-3-eval": ['vol-dre-3-eval-Probe-1', 'vol-dre-3-eval-Probe-2', 'vol-dre-3-eval-Probe-3', 'vol-dre-3-eval-Probe-4', 'vol-dre-3-eval-Probe-5', 'vol-dre-3-eval-Probe-6', 'vol-dre-3-eval-Probe-7', 'vol-dre-3-eval-Probe-8', 'vol-dre-3-eval-Probe-9', 'vol-dre-3-eval-Probe-10', 'vol-dre-3-eval-Probe-11', 'vol-dre-3-eval-Probe-12']
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

# scene: id-3; probe: vol-dre-2-eval-Probe-4, choice-0: G, choice-1: H
# scene: id-7; probe: vol-dre-2-eval-Probe-8, choice-0: P, choice-1: V
# scene: id-11; probe: vol-dre-2-eval-Probe-12, choice-0: U, choice-1: W

# scene: id-3; probe: 4.4, choice-0: U, choice-1: W
# scene: id-7; probe: 4.8, choice-0: G, choice-1: H

DRAGGING_MAP = {
    "00bb614f-4e6c-482e-b143-f2e984a9cdc9_20249205": {
        "id-3": "choice-1", # W 
        "id-7": "choice-0" # G
    },
    "927f6c89-963f-40aa-b29e-9d30028c7ca3_20249203": {
        "id-3": "choice-0", # G
        "id-7": "choice-0", # P
        "id-11": "choice-0" # U
    },
    "c2bebdcb-e247-4e06-b4e7-229cf1dbec4e_20249204": {
        "id-3": "choice-1", # W
        "id-7": "choice-0" # G
    },
    "bae30dd5-1145-4cb9-97ee-5e79863dbc38_20249201": {
        "id-3": "choice-1", # W
        "id-7": "choice-0" # G
    },
    "6a90c3a6-f15b-4ee8-9604-8c351e83cfd6_20249201": {
        "id-3": "choice-1", # H
        "id-7": "choice-0", # P
        "id-11": "choice-1" # W
    },
    "8395ef5b-b514-4fd2-b2e2-020a6ea10ad0_20249213": {
        "id-3": "choice-1", # H
        "id-7": "choice-0", # P 
        "id-11": "choice-0" # U
    },
    "e202018f-f6d7-40d0-809c-61ca80227db0_20249204": {
        "id-3": "choice-0", # G
        "id-7": "choice-1", # V
        "id-11": "choice-0" # U
    },
    "a51b409a-5f29-49e4-a7b8-6f5532159560_20249207": {
        "id-3": "choice-1", # H
        "id-7": "choice-0", # P 
        "id-11": "choice-0" # U
    },
    "2ab032e5-9cb3-47d4-9864-7dd1ea6d33b4_20249202": {
        "id-3": "choice-1", # W
        "id-7": "choice-1" # H
    },
    "f49de803-6665-4bc2-a3e9-981a647b63ff_20249206": {
        "id-3": "choice-0", # G
        "id-7": "choice-1", # V
        "id-11": "choice-1" # W
    },
    "9beec8c4-475d-4f20-8e5e-e2ba6165632f_20249207": {
        "id-3": "choice-1", # W
        "id-7": "choice-0" # G
    },
    "34b24007-8e2c-4c2f-ad0e-238a646dc9be_20249206": {
        "id-3": "choice-0", # U
        "id-7": "choice-0" # G
    },
    "d7f584e4-0586-4dd3-aa16-3799bb1e88c9_20249202": {
        "id-3": "choice-0", # G
        "id-7": "choice-0", # P
        "id-11": "choice-1" # W
    },
    "a5479d6f-213b-4ef4-bfcb-b166acf51542_20249203": {
        "id-3": "choice-1", # W
        "id-7": "choice-0" # G
    },
    "2fbde6b6-5f25-4657-8db1-4f9bf5f85822_20249205": {
        "id-3": "choice-1", # H
        "id-7": "choice-0", # P
        "id-11": "choice-1" # W
    },
    "095b00b1-74ca-4455-a4e1-d608578aa446_202409101": {
        "id-3": "choice-1", # H
        "id-7": "choice-0", # P
        "id-11": "choice-1" # W
    },
    "d7dbc70b-2cfe-4038-a235-446316e0f9ee_202409102": {
        "id-3": "choice-0", # U
        "id-7": "choice-0" # G
    },
    "3eeeb003-c17d-4f3d-8f23-b16a8ac3d4fe_202409112": {
        "id-3": "choice-0", # G
        "id-7": "choice-1", # V
        "id-11": "choice-0" # U
    },
}

ENV_MAP = {
    "dryrun-soartech-eval-qol1.yaml": "qol-dre-1-eval",
    "dryrun-soartech-eval-qol2.yaml": "qol-dre-2-eval",
    "dryrun-soartech-eval-qol3.yaml": "qol-dre-3-eval",
    "dryrun-soartech-eval-vol1.yaml": "vol-dre-1-eval",
    "dryrun-soartech-eval-vol2.yaml": "vol-dre-2-eval",
    "dryrun-soartech-eval-vol3.yaml": "vol-dre-3-eval",
    "dryrun-adept-eval-MJ2.yaml": "DryRunEval-MJ2-eval",
    "dryrun-adept-eval-MJ4.yaml": "DryRunEval-MJ4-eval",
    "dryrun-adept-eval-MJ5.yaml": "DryRunEval-MJ5-eval"
}


mongo_collection_matches = None
mongo_collection_raw = None
text_scenario_collection = None
delegation_collection = None
medic_collection = None
adm_collection = None
mini_adms_collection = None
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
            self.soartech_file = open(os.path.join(os.path.join("soartech-evals", "eval4"), env), 'r', encoding='utf-8')
            try:
                self.soartech_yaml = yaml.load(self.soartech_file, Loader=yaml.CLoader)
            except Exception as e:
                self.logger.log(LogLevel.ERROR, "Error while loading in soartech yaml file. Please ensure the file is a valid yaml format and try again.\n\n" + str(e) + "\n")
        else:
            self.adept_file = open(os.path.join(os.path.join("adept-evals", "eval4"), env), 'r', encoding='utf-8')
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
        if not RUN_ALL and os.path.exists(filename):
            if RERUN_ADEPT_SESSIONS and 'adept' in self.environment:
                return run_this_file
            if not RUN_ALIGNMENT:
                run_this_file = False
            if RUN_ALIGNMENT:
                f = open(filename, 'r', encoding='utf-8')
                data = json.load(f)
                if len(list(data.get('alignment', {}).keys())) > 1 and 'sid' in data.get('alignment', {}):
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
            'tag_expectant': 0
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
                if x[0] in ['TOOL_APPLIED', 'TAG_APPLIED']:
                    engagement_order.append(x[header.index('PatientID')].split(' Root')[0])
                    if x[0] == 'TOOL_APPLIED':
                        treated.append(x[header.index('PatientID')].split(' Root')[0])
                elif x[0] in ['SP_O2_TAKEN', 'BREATHING_CHECKED', 'PULSE_TAKEN']:
                    engagement_order.append(x[header.index('PatientID')].split(' Root')[0])
            simple_order = []
            for x in engagement_order:
                if len(simple_order) > 0 and x == simple_order[-1]:
                    continue
                simple_order.append(x)
            print(simple_order)
            return {'engaged': len(list(set(engagement_order))), 'treated': len(list(set(treated)))}

        engaged_counts = find_patients_engaged()
        patients_engaged = engaged_counts['engaged']
        patients_treated = engaged_counts['treated']

        def count_assessment_actions():
            '''returns the total count of assessment actions during the scenario'''
            assessment_actions = ['SP_O2_TAKEN', 'BREATHING_CHECKED', 'PULSE_TAKEN']
            count = 0
            last_done = {}
            for x in data:
                # only count actions that are more than 5 seconds apart from the last of the same type of action
                if x[0] in assessment_actions and (x[0] not in last_done or (timestamp_to_milliseconds(x[2]) - last_done[x[0]]) > 5000):
                    last_done[x[0]] = timestamp_to_milliseconds(x[2])
                    count += 1
            return count
        
        results['assess_total'] = count_assessment_actions()
        results['assess_patient'] = results['assess_total'] / max(1, patients_engaged)

        def count_treatment_actions():
            '''returns the total count of treatment actions during the scenario'''
            count = 0
            for x in data:
                if x[0] == 'TOOL_APPLIED' and 'Pulse_Oximeter' not in x:
                    count += 1
            return count
        
        results['treat_total'] = count_treatment_actions()
        results['treat_patient'] = results['treat_total'] / max(1, patients_treated)

        def get_triage_time():
            '''gets the time from start to finish (in seconds) to complete the scenario'''
            if len(data) > 0:
                start = float(data[0][1])
                end = float(data[len(data)-2][1])
                return ((end-start))/1000
            
        results['triage_time'] = get_triage_time()




        print(results)
        return results

#     'Triage_time_patient', 'Engage_patient', 'Tag_ACC', 'Tag_Expectant',
#     'Patient1_time', 'Patient1_order', 'Patient1_evac', 'Patient1_assess', 'Patient1_treat', 'Patient1_tag',
#     'Patient2_time', 'Patient2_order', 'Patient2_evac', 'Patient2_assess', 'Patient2_treat', 'Patient2_tag',
#     'Patient3_time', 'Patient3_order', 'Patient3_evac', 'Patient3_assess', 'Patient3_treat', 'Patient3_tag',
#     'Patient4_time', 'Patient4_order', 'Patient4_evac', 'Patient4_assess', 'Patient4_treat', 'Patient4_tag',
#     'Patient5_time', 'Patient5_order', 'Patient5_evac', 'Patient5_assess', 'Patient5_treat', 'Patient5_tag',
#     'Patient6_time', 'Patient6_order', 'Patient6_evac', 'Patient6_assess', 'Patient6_treat', 'Patient6_tag',
#     'Patient7_time', 'Patient7_order', 'Patient7_evac', 'Patient7_assess', 'Patient7_treat', 'Patient7_tag',
#     'Patient8_time', 'Patient8_order', 'Patient8_evac', 'Patient8_assess', 'Patient8_treat', 'Patient8_tag'
# ]


        if SEND_TO_MONGO:
            try:
                mongo_collection_raw.insert_one({'openWorld': True, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': self.json_data, 'pid': self.participantId, '_id': self.participantId + '_' + self.environment.replace(' ', '-')})
            except:
                mongo_collection_raw.update_one({'_id': self.participantId + '_' + self.environment.replace(' ', '-')}, {'$set': {'openWorld': True, 'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': self.json_data, 'pid': self.participantId}})


    def match_qol_vol_probes(self):
        soartech_scenes = self.soartech_yaml['scenes']
        last_action_ind_used = 0
        match_data = []
        total = 0
        found = 0
        updated_json = copy.deepcopy(self.json_data) # so we can update with missing probes
        actions_added = 0
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
            else:
                # get manual mappings based on file name and scene
                file_name = self.json_data['sessionId'] + '_' + self.participantId
                mapping = DRAGGING_MAP.get(file_name, {}).get(scene['id'], None)
                if mapping is not None:
                    for x in scene['action_mapping']:
                        if x['choice'] == mapping:
                            matched = x
                            break
                    if matched is not None:
                        found += 1
                        fake_action = {
                            "actionType": "DragPatient",
                            "casualty": matched['character_id'],
                            "note": "Manually Found"
                        }
                        match_data.append({
                            "scene_id": scene['id'],
                            "probe_id": matched['probe_id'],
                            "found_match": True,
                            "probe": matched,
                            "user_action": fake_action
                        })
                        updated_json['actionList'].insert(last_action_ind_used+actions_added+1, fake_action)
                        actions_added += 1

        print(f"Found {found} out of {total} probes")
        st_align = {}
        if RUN_ALIGNMENT:
            try:
                targets = ['vol-human-8022671-SplitHighMulti', 'qol-human-2932740-HighExtreme', 'vol-human-1774519-SplitHighMulti', 'qol-human-6349649-SplitHighMulti', 
                        'vol-human-6403274-SplitEvenBinary', 'qol-human-3447902-SplitHighMulti', 'vol-human-7040555-SplitEvenBinary', 'qol-human-7040555-SplitHighMulti', 
                        'vol-human-2637411-SplitEvenMulti', 'qol-human-3043871-SplitHighBinary', 'vol-human-2932740-SplitEvenMulti', 'qol-human-6403274-SplitHighBinary', 
                        'vol-human-8478698-SplitLowMulti', 'qol-human-1774519-SplitEvenBinary', 'vol-human-3043871-SplitLowMulti', 'qol-human-9157688-SplitEvenBinary', 
                        'vol-human-5032922-SplitLowMulti', 'qol-human-0000001-SplitEvenMulti', 'vol-synth-LowExtreme', 'qol-human-8022671-SplitLowMulti', 'vol-synth-HighExtreme', 
                        'qol-human-5032922-SplitLowMulti', 'vol-synth-HighCluster', 'qol-synth-LowExtreme', 'vol-synth-LowCluster', 'qol-synth-HighExtreme', 'vol-synth-SplitLowBinary', 
                        'qol-synth-HighCluster', 'qol-synth-LowCluster', 'qol-synth-SplitLowBinary']
                self.send_probes(f'{ST_URL}/api/v1/response', match_data, self.soartech_sid, self.soartech_yaml['id'])
                # send fake probes for 3 entries that are missing data. These probes will not be used to calculate alignment!
                if self.participantId == '202409111' and 'vol' in self.environment:
                    self.send_probes(f'{ST_URL}/api/v1/response', 
                        [
                            { 
                                "scene_id": 'id-10', 
                                "probe_id": 'vol-dre-train2-Probe-11', 
                                "found_match": False, 
                                "probe": {'probe_id': 'vol-dre-train2-Probe-11', 'choice': 'choice-1'}, 
                                "user_action": None
                            }, 
                            { 
                                "scene_id": 'id-11',
                                "probe_id": 'vol-dre-train2-Probe-12', 
                                "found_match": False, 
                                "probe": {'probe_id': 'vol-dre-train2-Probe-12', 'choice': 'choice-1'}, 
                                "user_action": None
                            }
                        ], self.soartech_sid, self.soartech_yaml['id'])
                if self.participantId == '202409112' and 'qol' in self.environment:
                    self.send_probes(f'{ST_URL}/api/v1/response', 
                        [
                            { 
                                "scene_id": 'id-11',
                                "probe_id": '12', 
                                "found_match": False, 
                                "probe": {'probe_id': '12', 'choice': 'choice-1'}, 
                                "user_action": None
                            }
                        ], self.soartech_sid, self.soartech_yaml['id'])                
                if self.participantId == '202409112' and 'vol' in self.environment:
                    self.send_probes(f'{ST_URL}/api/v1/response', 
                        [
                            { 
                                "scene_id": 'id-6',
                                "probe_id": '4.7', 
                                "found_match": False, 
                                "probe": {'probe_id': '4.7', 'choice': 'choice-0'}, 
                                "user_action": None
                            }
                        ], self.soartech_sid, self.soartech_yaml['id'])  
                for target in targets:
                    if ('vol' in target and 'vol' not in self.soartech_yaml['id']) or ('qol' in target and 'qol' not in self.soartech_yaml['id']):
                        continue
                    # do not include fake probes (see above) in alignment calculation
                    if self.participantId == '202409111' and 'vol' in self.environment:
                        # don't include 11 and 12
                        st_align[target] = self.get_session_alignment(f'{ST_URL}api/v1/alignment/session/subset?session_1={self.soartech_sid}&session_2={target}&session1_probes=4.1&session1_probes=4.2&session1_probes=4.3&session1_probes=4.4&session1_probes=4.5&session1_probes=4.6&session1_probes=4.7&session1_probes=4.8&session1_probes=4.9&session1_probes=4.10&session2_probes=4.1&session2_probes=4.2&session2_probes=4.3&session2_probes=4.4&session2_probes=4.5&session2_probes=4.6&session2_probes=4.7&session2_probes=4.8&session2_probes=4.9&session2_probes=4.10')
                    elif self.participantId == '202409112' and 'qol' in self.environment:
                        # don't include 12
                        st_align[target] = self.get_session_alignment(f'{ST_URL}api/v1/alignment/session/subset?session_1={self.soartech_sid}&session_2={target}\
                                                                      &session1_probes=4.1&session1_probes=4.2&session1_probes=4.3&session1_probes=4.4&session1_probes=4.5&session1_probes=4.6&\
                                                                      session1_probes=4.7&session1_probes=4.8&session1_probes=4.9&session1_probes=4.10&session1_probes=qol-dre-train2-Probe-11&\
                                                                      session2_probes=4.1&session2_probes=4.2&session2_probes=4.3&session2_probes=4.4&session2_probes=4.5&session2_probes=4.6&\
                                                                      session2_probes=4.7&session2_probes=4.8&session2_probes=4.9&session2_probes=4.10&session2_probes=qol-dre-train2-Probe-11')
                    elif self.participantId == '202409112' and 'vol' in self.environment:
                        # don't include 4.7
                        st_align[target] = self.get_session_alignment(f'{ST_URL}api/v1/alignment/session/subset?session_1={self.soartech_sid}&session_2={target}\
                                                                      &session1_probes=4.1&session1_probes=4.2&session1_probes=4.3&session1_probes=4.4&session1_probes=4.5&session1_probes=4.6\
                                                                      &session1_probes=4.8&session1_probes=4.9&session1_probes=4.10&session1_probes=vol-dre-train2-Probe-11&\
                                                                      session1_probes=vol-dre-train2-Probe-12&session2_probes=4.1&session2_probes=4.2&session2_probes=4.3&session2_probes=4.4&\
                                                                      session2_probes=4.5&session2_probes=4.6&session2_probes=4.8&session2_probes=4.9&session2_probes=4.10&\
                                                                      session2_probes=vol-dre-train2-Probe-11&session2_probes=vol-dre-train2-Probe-12')
                    else:
                        st_align[target] = self.get_session_alignment(f'{ST_URL}/api/v1/alignment/session?session_id={self.soartech_sid}&target_id={target}')
                st_align['kdmas'] = self.get_session_alignment(f'{ST_URL}/api/v1/computed_kdma_profile?session_id={self.soartech_sid}')
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
        # Adept has branching, which makes things a little more difficult
        first_scene_id = self.adept_yaml.get('first_scene', self.adept_yaml['scenes'][0]['id'])
        cur_scene = self.get_scene_by_id(adept_scenes, first_scene_id)
        while True:
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
            # go through actions taken until a match is found
            found_match = False
            total += 1
            matched = None
            for (ind, action_taken) in enumerate(self.json_data['actionList'][last_action_ind_used:]):
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
                        break   
                    # special mapping for move/stay urban questions
                    elif "Treat Soldier" in action_taken['answerChoices'] and 'Go Back to Shooter/Victim' in action_taken['answerChoices'] and cur_scene['id'] == 'Probe 4-B.1' and self.adept_yaml['id'] == 'DryRunEval-MJ2-eval':
                        last_action_ind_used += ind
                        found_match = True
                        matched = cur_scene['action_mapping'][2] if 'Treat' in action_taken['answer'] else cur_scene['action_mapping'][0]
                        break   
                    elif "Assess Soldier" in action_taken['answerChoices'] and 'Go Back to Shooter/Victim' in action_taken['answerChoices'] and cur_scene['id'] == 'Scene 3' and self.adept_yaml['id'] == 'DryRunEval-MJ2-eval':
                        last_action_ind_used += ind
                        found_match = True
                        matched = cur_scene['action_mapping'][2] if 'Assess' in action_taken['answer'] else cur_scene['action_mapping'][0]
                        break   
                    elif 'Justify' in actions and looking_for_justify:
                        if action_taken['question'] in JUSTIFY_MAPPING:
                            last_action_ind_used += ind
                            found_match = True
                            probe_choice = JUSTIFY_MAPPING[action_taken['question']][action_taken['answer'].strip()]
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
                elif action_taken['actionType'] in VITALS_ACTIONS and 'Vitals' in actions:
                    if action_taken['casualty'] in actions['Vitals']:
                        last_action_ind_used += ind
                        found_match = True
                        matched = actions['Vitals'][action_taken['casualty']]
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
                        break
            if found_match or len(cur_scene['action_mapping']) == 1 or 'None' in actions:
                if len(cur_scene['action_mapping']) == 1:
                    # some adept scenes are just there for transitions and don't really require action
                    matched = cur_scene['action_mapping'][0]
                elif not found_match and 'None' in actions:
                    matched = actions['None'][0]
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
                targets = ['ADEPT-DryRun-Moral judgement-0.0', 'ADEPT-DryRun-Ingroup Bias-0.0', 'ADEPT-DryRun-Moral judgement-0.1', 'ADEPT-DryRun-Ingroup Bias-0.1', 'ADEPT-DryRun-Moral judgement-0.2', 'ADEPT-DryRun-Ingroup Bias-0.2', 'ADEPT-DryRun-Moral judgement-0.3', 
                        'ADEPT-DryRun-Ingroup Bias-0.3', 'ADEPT-DryRun-Moral judgement-0.4', 'ADEPT-DryRun-Ingroup Bias-0.4', 'ADEPT-DryRun-Moral judgement-0.5', 'ADEPT-DryRun-Ingroup Bias-0.5', 'ADEPT-DryRun-Moral judgement-0.6', 'ADEPT-DryRun-Ingroup Bias-0.6', 'ADEPT-DryRun-Moral judgement-0.7', 'ADEPT-DryRun-Ingroup Bias-0.7', 'ADEPT-DryRun-Moral judgement-0.8', 
                        'ADEPT-DryRun-Ingroup Bias-0.8', 'ADEPT-DryRun-Moral judgement-0.9', 'ADEPT-DryRun-Ingroup Bias-0.9', 'ADEPT-DryRun-Moral judgement-1.0', 'ADEPT-DryRun-Ingroup Bias-1.0']
                self.send_probes(f'{ADEPT_URL}/api/v1/response', match_data, self.adept_sid, self.adept_yaml['id'])
                for target in targets:
                    ad_align[target] = self.get_session_alignment(f'{ADEPT_URL}/api/v1/alignment/session?session_id={self.adept_sid}&target_id={target}&population=false')
                ad_align['kdmas'] = self.get_session_alignment(f'{ADEPT_URL}/api/v1/computed_kdma_profile?session_id={self.adept_sid}')
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
        json.dump(match_data, self.output_adept, indent=4)  


    def send_probes(self, probe_url, probes, sid, scenario):
        '''
        Sends the probes to the server
        '''
        for x in probes:
            if 'probe' in x and 'choice' in x['probe']:
                requests.post(probe_url, json={
                    "response": {
                        "choice": x['probe']['choice'],
                        "justification": "justification",
                        "probe_id": x['probe']['probe_id'],
                        "scenario_id": scenario,
                    },
                    "session_id": sid
                })


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
        if RECALCULATE_COMPARISON or not (adms_vs_text is not None and len(adms_vs_text) > 0 and not RUN_ALL):
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
            text_response = text_scenario_collection.find_one({"evalNumber": 4, 'participantID': self.participantId, 'scenario_id': {"$regex": vr_scenario.split('-')[0], "$options": "i"}})
            if text_response is None:
                self.logger.log(LogLevel.WARN, f"Error getting text response for pid {self.participantId} {vr_scenario.split('-')[0]} scenario")
                return None
            text_sid = text_response['serverSessionId']
            text_scenario = text_response['scenario_id']
            
            # send all probes to ST server for VR vs text
            query_param = f"session_1={vr_sid}&session_2={text_sid}"
            for probe_id in ST_PROBES['all'][vr_scenario]:
                if 'vol' in self.environment and self.participantId == '202409111' and probe_id in [ST_PROBES['all'][vr_scenario][10], ST_PROBES['all'][vr_scenario][11]]:
                    continue
                if 'qol' in self.environment and self.participantId == '202409112' and probe_id in [ST_PROBES['all'][vr_scenario][11]]:
                    continue
                if 'vol' in self.environment and self.participantId == '202409112' and probe_id in [ST_PROBES['all'][vr_scenario][6]]:
                    continue
                query_param += f"&session1_probes={probe_id}"
            for probe_id in ST_PROBES['all'][text_scenario]:
                if 'vol' in self.environment and self.participantId == '202409111' and probe_id in [ST_PROBES['all'][text_scenario][10], ST_PROBES['all'][text_scenario][11]]:
                    continue
                if 'qol' in self.environment and self.participantId == '202409112' and probe_id in [ST_PROBES['all'][text_scenario][11]]:
                    continue
                if 'vol' in self.environment and self.participantId == '202409112' and probe_id in [ST_PROBES['all'][text_scenario][6]]:
                    continue
                query_param += f"&session2_probes={probe_id}"
            res = requests.get(f'{ST_URL}api/v1/alignment/session/subset?{query_param}').json()
            if res is None or 'score' not in res:
                self.logger.log(LogLevel.WARN, "Error getting comparison score (soartech). Perhaps not all probes have been completed in the sim?")
                return
            res = res['score']
        elif 'adept' in self.environment:
            # get text session id
            text_response = text_scenario_collection.find_one({"evalNumber": 4, 'participantID': self.participantId, 'scenario_id': {"$in": ["DryRunEval-MJ2-eval", "DryRunEval-MJ4-eval", "DryRunEval-MJ5-eval"]}})
            if text_response is None:
                self.logger.log(LogLevel.WARN, f"Error getting text response for pid {self.participantId} adept scenario")
                return None
            text_sid = text_response['combinedSessionId']
            # send text and vr session ids to Adept server
            res_mj = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions?session_id_1={vr_sid}&session_id_2={text_sid}&kdma_filter=Moral%20judgement').json()
            res_io = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions?session_id_1={vr_sid}&session_id_2={text_sid}&kdma_filter=Ingroup%20Bias').json()
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
        for page in survey['results']:
            if 'Medic' in page and ' vs ' not in page:
                page_scenario = survey['results'][page]['scenarioIndex']
                if ('qol' in self.environment and 'qol' in page_scenario) or ('vol' in self.environment and 'vol' in page_scenario):
                    # find the adm session id that matches the medic shown in the delegation survey
                    adm = db_utils.find_adm_from_medic(medic_collection, adm_collection, page, page_scenario, survey)
                    if adm is None:
                        continue
                    adm_session = adm['history'][len(adm['history'])-1]['parameters']['session_id']
                    # create ST query param
                    query_param = f"session_1={vr_sid}&session_2={adm_session}"
                    for probe_id in ST_PROBES['delegation'][vr_scenario]:
                        if 'vol' in self.environment and self.participantId == '202409111' and probe_id in [ST_PROBES['all'][vr_scenario][10], ST_PROBES['all'][vr_scenario][11]]:
                            continue
                        if 'qol' in self.environment and self.participantId == '202409112' and probe_id in [ST_PROBES['all'][vr_scenario][11]]:
                            continue
                        if 'vol' in self.environment and self.participantId == '202409112' and probe_id in [ST_PROBES['all'][vr_scenario][6]]:
                            continue
                        query_param += f"&session1_probes={probe_id}"
                    for probe_id in ST_PROBES['delegation'][page_scenario]:
                        if 'vol' in self.environment and self.participantId == '202409111' and probe_id in [ST_PROBES['all'][page_scenario][10], ST_PROBES['all'][page_scenario][11]]:
                            continue
                        if 'qol' in self.environment and self.participantId == '202409112' and probe_id in [ST_PROBES['all'][page_scenario][11]]:
                            continue
                        if 'vol' in self.environment and self.participantId == '202409112' and probe_id in [ST_PROBES['all'][page_scenario][6]]:
                            continue
                        query_param += f"&session2_probes={probe_id}"
                    # get comparison score
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
                    adm = db_utils.find_adm_from_medic(medic_collection, adm_collection, page, page_scenario.replace('IO', 'MJ'), survey)
                    if adm is None:
                        continue
                    adm_target = adm['history'][len(adm['history'])-1]['parameters']['target_id']
                    found_mini_adm = mini_adms_collection.find_one({'target': adm_target, 'scenario': page_scenario.replace('IO', 'MJ'), 'adm_name': survey['results'][page]['admName']})
                    if found_mini_adm is None:
                        # get new adm session that contains only the probes seen in the delegation survey
                        probe_ids = AD_DEL_PROBES[page_scenario] # this is where IO/MJ comes into play - choosing the probes
                        probe_responses = []
                        for x in adm['history']:
                            if x['command'] == 'Respond to TA1 Probe':
                                if x['parameters']['choice'] in probe_ids or x['parameters']['probe_id'] in probe_ids:
                                    probe_responses.append(x['parameters'])
                        found_mini_adm = db_utils.mini_adm_run(mini_adms_collection, probe_responses, adm_target, survey['results'][page]['admName'])
                    res = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions?session_id_1={vr_sid}&session_id_2={found_mini_adm["session_id"]}').json()
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
    parser = argparse.ArgumentParser(description='ITM - Probe Matcher', usage='probe_matcher.py [-h] -i PATH')

    parser.add_argument('-i', '--input_dir', dest='input_dir', type=str, help='The path to the directory where all participant files are. Required.')
    args = parser.parse_args()
    if not args.input_dir:
        print("Input directory (-i PATH) is required to run the probe matcher.")
        exit(1)
    if SEND_TO_MONGO:
        # instantiate mongo client
        client = MongoClient(config('MONGO_URL'))
        db = client.dashboard
        # create new collection for simulation runs
        mongo_collection_matches = db['humanSimulator']
        mongo_collection_raw = db['humanSimulatorRaw']
        text_scenario_collection = db['userScenarioResults']
        delegation_collection = db['surveyResults']
        medic_collection = db['admMedics']
        adm_collection = db["test"]
        mini_adms_collection = db['delegationADMRuns']

    # go through the input directory and find all sub directories
    sub_dirs = [name for name in os.listdir(args.input_dir) if os.path.isdir(os.path.join(args.input_dir, name))]
    # for each subdirectory, see if a json file exists
    for dir in sub_dirs:
        parent = os.path.join(args.input_dir, dir)
        if os.path.isdir(parent):
            for f in os.listdir(parent):
                if '.json' in f:
                    print(f"\n** Processing {f} **")
                    # json found! grab matching csv and send to the probe matcher
                    try:
                        adept_sid = requests.post(f'{ADEPT_URL}/api/v1/new_session').text.replace('"', '').strip()
                        soartech_sid = requests.post(f'{ST_URL}/api/v1/new_session?user_id=default_use').json()
                        matcher = ProbeMatcher(os.path.join(parent, f), adept_sid, soartech_sid)
                        # matcher = ProbeMatcher(os.path.join(parent, f), None, None) # use this for basic matching testing when SSL is not working
                        if matcher.environment != '' and matcher.analyze:
                            matcher.match_probes()
                        if matcher.environment != '' and RUN_COMPARISON:
                            matcher.run_comparison()
                        matcher.__del__()
                    except Exception as e:
                        print(e)
                elif '.html' in f or '.jpg' in f:
                    os.remove(os.path.join(parent, f))
    print()
