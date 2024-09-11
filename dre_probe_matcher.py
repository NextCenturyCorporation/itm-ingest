import yaml, argparse, json, os, csv
from logger import LogLevel, Logger
from pymongo import MongoClient
from datetime import datetime
import requests
from decouple import config 

SEND_TO_MONGO = False
EVAL_NUM = 3
EVAL_NAME = 'Dry Run Evaluation'

SCENE_MAP = {
    "qol-dre-1-eval Narrative": "dryrun-soartech-eval-qol1.yaml",
    "qol-dre-2-eval Narrative": "dryrun-soartech-eval-qol2.yaml",
    "qol-dre-3-eval Narrative": "dryrun-soartech-eval-qol3.yaml",
    "vol-dre-1-eval Narrative": "dryrun-soartech-eval-vol1.yaml",
    "vol-dre-2-eval Narrative": "dryrun-soartech-eval-vol2.yaml",
    "vol-dre-3-eval Narrative": "dryrun-soartech-eval-vol3.yaml",
}

ACTION_TRANSLATION = {
    "APPLY_TREATMENT": "Treatment",
    "CHECK_ALL_VITALS": "Vitals",
    "MOVE_TO_EVAC": "DragPatient"
}

VITALS_ACTIONS = ["SpO2", "Breathing", "Pulse"]


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
        self.json_file = open(json_path, 'r')
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
        if SEND_TO_MONGO:
            try:
                mongo_collection_raw.insert_one({'evalNumber': EVAL_NUM, 'evalName': EVAL_NAME, 'data': self.json_data, 'pid': self.participantId, '_id': self.participantId + '_' + self.environment})
            except:
                # not overwriting document in mongo
                pass
        
        if pid in ENVIRONMENTS_BY_PID:
            ENVIRONMENTS_BY_PID[pid].append(self.environment)
        else:
            ENVIRONMENTS_BY_PID[pid] = [self.environment]
        # create output files
        try:
            os.mkdir('output')
        except:
            pass
        self.output_soartech = open(os.path.join('output', env.split('.yaml')[0] + f'_soartech_{pid}.json'), 'w')
        self.output_adept = open(os.path.join('output', env.split('.yaml')[0] + f'_adept_{pid}.json'), 'w')
        # get soartech/adept yaml data
        if 'qol' in env or 'vol' in env:
            self.soartech_file = open(os.path.join(os.path.join("soartech-evals", "eval4"), env), 'r')
            
            try:
                self.soartech_yaml = yaml.load(self.soartech_file, Loader=yaml.CLoader)
            except Exception as e:
                self.logger.log(LogLevel.ERROR, "Error while loading in soartech yaml file. Please ensure the file is a valid yaml format and try again.\n\n" + str(e) + "\n")
        else:
            self.adept_file = open(os.path.join(os.path.join("adept-evals", "eval4"), env), 'r')
            try:
                self.adept_yaml = yaml.load(self.adept_file, Loader=yaml.CLoader)
            except Exception as e:
                self.logger.log(LogLevel.ERROR, "Error while loading in adept yaml file. Please ensure the file is a valid yaml format and try again.\n\n" + str(e) + "\n")

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

    def match_probes(self):
        if 'qol' in self.environment or 'vol' in self.environment:
            self.match_qol_vol_probes()
        else:
            self.logger.log(LogLevel.WARN, f"No function available to probe match for environment {self.environment}")
    

    def match_qol_vol_probes(self):
        soartech_scenes = self.soartech_yaml['scenes']
        last_action_ind_used = 0
        match_data = []
        # ST has no branching, so we can just go straight through the scenes
        for scene in soartech_scenes:
            actions = {} # {"Treatment": {"v": probe, "x": probe}, "Vitals": {"v": probe, "x": probe}, "Intent": {"v": probe, "x": probe}, etc}
            # get all available actions for the scene
            for probe_action in scene['action_mapping']:
                action_label = None
                if probe_action['intent_action']:
                    action_label = 'Intend'
                else:
                    action_label = ACTION_TRANSLATION.get(probe_action['action_type'], None)
                if action_label is None:
                    self.logger.log(LogLevel.WARN, f"No action translation found for {probe_action['action_type']}")
                else:
                    if action_label not in actions:
                        actions[action_label] = {}
                    # we are not checking specific treatments, so this is okay to overwrite
                    actions[action_label][probe_action['character_id']] = probe_action
            # go through actions taken until a match is found
            found_match = False
            matched = None
            for (ind, action_taken) in enumerate(self.json_data['actionList'][last_action_ind_used:]):
                if action_taken['actionType'] == 'Question' and 'Intend' in actions:
                    # fix for typo in vol scenarios - should be O vs U, but in some versions is O vs N
                    if action_taken['answer'] in ['N (35; TBI, forehead scrape)', 'N (36; TBI, forehead scrape)', 'N (37; TBI, face shrapnel)']:
                        action_taken['answer'] = 'U' + action_taken['answer'][1:]
                    answer = ('casualty_' + action_taken['answer'][0]).lower()
                    if answer in actions['Intend']:
                        last_action_ind_used = ind
                        found_match = True
                        matched = actions['Intend'][answer]
                        break
                elif action_taken['actionType'] in VITALS_ACTIONS and 'Vitals' in actions:
                    if action_taken['casualty'] in actions['Vitals']:
                        last_action_ind_used = ind
                        found_match = True
                        matched = actions['Vitals'][action_taken['casualty']]
                        break
                elif action_taken['actionType'] in actions:
                    if action_taken['casualty'] in actions[action_taken['actionType']]:
                        last_action_ind_used = ind
                        found_match = True
                        matched = actions[action_taken['actionType']][action_taken['casualty']]
                        break
            if found_match:
                match_data.append({
                    "scene_id": scene['id'],
                    "probe_id": matched['probe_id'],
                    "found_match": True,
                    "probe": matched,
                    "user_action": action_taken
                })
        # print(json.dumps(match_data, indent=4))
        # QOL:
        # go to: O vs. U (intent to treat)
        # go to: O vs. N (treat)
        # go to: U vs. W (treat)
        # then drag U vs. W? (move to safety)
        # go to: G vs. Y (intent to treat)
        # go to: X vs. Y (treat)
        # go to: G vs. H; (treat)
        # then drag G vs. H? (move to safety)
        # Z vs. L? (intent to treat)
        # Z vs. A? (treat)
        # L vs. M; (treat)
        # pain meds L vs. M? (supply limit)
        # VOL:
        # go to: Y vs. G (intent to treat)
        # go to: Y vs. X (treat)
        # go to: G vs. H (treat)
        # then drag G vs. H? (move to safety)
        # go to: C vs. P (intent to treat)
        # go to: C vs. B (treat)
        # go to: P vs. V; (treat)
        # then drag P vs. V? (move to safety)
        # O vs. U? (intent to treat)
        # O vs. N? (treat)
        # U vs. W; (treat)
        # then drag U vs. W? (move to safety)
                

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
                        # adept_sid = requests.post(f'{config("ADEPT_URL")}/api/v1/new_session').text
                        # soartech_sid = requests.post(f'{config("ST_URL")}/api/v1/new_session?user_id=default_use').json()
                        # matcher = ProbeMatcher(os.path.join(parent, f), os.path.join(parent, dir + '.csv'), adept_sid, soartech_sid)
                        matcher = ProbeMatcher(os.path.join(parent, f), None, None)
                        if matcher.environment != '':
                            matcher.match_probes()
                        break
                    except Exception as e:
                        print(e)
    # print(json.dumps(ENVIRONMENTS_BY_PID, indent=4))