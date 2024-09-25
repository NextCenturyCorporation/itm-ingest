import yaml, argparse, json, os, copy
from logger import LogLevel, Logger
from pymongo import MongoClient
from datetime import datetime
import requests
from decouple import config 

SEND_TO_MONGO = True
RUN_ALIGNMENT = True
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
    "DryRunEval-MJ5-eval Narrative": "dryrun-adept-eval-MJ5.yaml"
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
    }
}


mongo_collection_matches = None
mongo_collection_raw = None
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
        self.timestamp = datetime.strptime(str_time, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()*1000

        pid = self.json_data['participantId']
        pid = pid if pid != '' else self.json_data['sessionId']
        self.participantId = pid
        env = SCENE_MAP.get(self.json_data["configData"]["narrative"]["narrativeDescription"], '')
        if env == '':
            self.logger.log(LogLevel.WARN, "Environment not defined. Unable to process data")
            return
        self.environment = env
        
        if pid in ENVIRONMENTS_BY_PID:
            ENVIRONMENTS_BY_PID[pid].append(self.environment)
        else:
            ENVIRONMENTS_BY_PID[pid] = [self.environment]
        # create output files
        try:
            os.mkdir('output')
        except:
            pass
        if 'adept' not in self.environment:
            self.output_soartech = open(os.path.join('output', env.split('.yaml')[0] + f'_soartech_{pid}.json'), 'w', encoding='utf-8')
        else:
            self.output_adept = open(os.path.join('output', env.split('.yaml')[0] + f'_adept_{pid}.json'), 'w', encoding='utf-8')
        # get soartech/adept yaml data
        if 'qol' in env or 'vol' in env:
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
        print(self.environment)
        if 'qol' in self.environment or 'vol' in self.environment:
            self.match_qol_vol_probes()
        elif 'adept' in self.environment:
            self.match_adept_probes()
        else:
            self.logger.log(LogLevel.WARN, f"No function available to probe match for environment {self.environment}")
    

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
                    answer = ('casualty_' + action_taken['answer'][0]).lower()
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
                for target in targets:
                    if ('vol' in target and 'vol' not in self.soartech_yaml['id']) or ('qol' in target and 'qol' not in self.soartech_yaml['id']):
                        continue
                    st_align[target] = self.get_session_alignment(f'{ST_URL}/api/v1/response', 
                                            f'{ST_URL}/api/v1/alignment/session?session_id={self.soartech_sid}&target_id={target}',
                                            match_data,
                                            self.soartech_sid,
                                            self.soartech_yaml['id'])
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
                mongo_collection_raw.insert_one({'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': updated_json, 'pid': self.participantId, '_id': self.participantId + '_' + self.environment})
            except:
                mongo_collection_raw.update_one({'_id': self.participantId + '_' + self.environment}, {'$set': {'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': updated_json, 'pid': self.participantId, '_id': self.participantId + '_' + self.environment}})
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
                for target in targets:
                    if ('vol' in target and 'vol' not in self.soartech_yaml['id']) or ('qol' in target and 'qol' not in self.soartech_yaml['id']):
                        continue
                    ad_align[target] = self.get_session_alignment(f'{ADEPT_URL}/api/v1/response', 
                                            f'{ADEPT_URL}/api/v1/alignment/session?session_id={self.adept_sid}&target_id={target}&population=false',
                                            match_data,
                                            self.adept_sid,
                                            self.adept_yaml['id'])
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
                mongo_collection_raw.insert_one({'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': self.json_data, 'pid': self.participantId, '_id': self.participantId + '_' + self.environment})
            except:
                mongo_collection_raw.update_one({'_id': self.participantId + '_' + self.environment}, {'$set': {'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': self.json_data, 'pid': self.participantId, '_id': self.participantId + '_' + self.environment}})
        json.dump(match_data, self.output_adept, indent=4)  


    def get_session_alignment(self, probe_url, align_url, probes, sid, scenario):
        '''
        Takes in the list of probes/matches and the urls to access and returns the session alignment
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
        return requests.get(align_url).json()


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
                        adept_sid = requests.post(f'{ADEPT_URL}/api/v1/new_session').text
                        soartech_sid = requests.post(f'{ST_URL}/api/v1/new_session?user_id=default_use').json()
                        matcher = ProbeMatcher(os.path.join(parent, f), adept_sid, soartech_sid)
                        # matcher = ProbeMatcher(os.path.join(parent, f), None, None) # use this for basic matching testing when SSL is not working
                        if matcher.environment != '':
                            matcher.match_probes()
                    except Exception as e:
                        print(e)
                elif '.html' in f or '.jpg' in f:
                    os.remove(os.path.join(parent, f))
    print()
