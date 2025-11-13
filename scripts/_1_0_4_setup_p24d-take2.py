import requests, os, csv, random
from pymongo import MongoClient
from decouple import config

JULY_EVAL_NUM = 9
FOUR_D_EVAL_NUM = 11
ADEPT_URL = config("ADEPT_URL")
HIT_TA1_SERVER = True  # Useful for testing or if you can't reach the TA1 server
WRITE_TO_DB = True     # Useful for testing or experimentation, without clobbering your DB
VERBOSE = False        # Useful for testing and debugging
PYTHON_CMD = 'python3' # System-dependent, default to production server
FOUR_D_COLLECTION = 'multiKdmaData4Dtake2' # Change this is you don't want to clobber the old collection

# Maps scenario ID to the probes in that subset.
# This could be accomplished by getting them from the subset yaml files in ingest.
PROBE_MAP: dict = {'July2025-AF1-eval' : ['Probe 5', 'Probe 9', 'Probe 15', 'Probe 18', 'Probe 29', 'Probe 101'],
                   'July2025-AF2-eval' : ['Probe 6', 'Probe 21', 'Probe 34', 'Probe 36', 'Probe 39', 'Probe 106'],
                   'July2025-AF3-eval' : ['Probe 31', 'Probe 40', 'Probe 48', 'Probe 107', 'Probe 111', 'Probe 113'],
                   'July2025-MF1-eval' : ['Probe 1', 'Probe 21', 'Probe 27', 'Probe 41', 'Probe 56', 'Probe 101'],
                   'July2025-MF2-eval' : ['Probe 22', 'Probe 30', 'Probe 43', 'Probe 102', 'Probe 107', 'Probe 109'],
                   'July2025-MF3-eval' : ['Probe 44', 'Probe 61', 'Probe 68', 'Probe 103', 'Probe 108', 'Probe 110'],
                   'July2025-PS1-eval' : ['Probe 1', 'Probe 3', 'Probe 4', 'Probe 7', 'Probe 8', 'Probe 14'],
                   'July2025-PS2-eval' : ['Probe 5', 'Probe 9', 'Probe 13', 'Probe 16', 'Probe 17', 'Probe 22'],
                   'July2025-PS3-eval' : ['Probe 11', 'Probe 19', 'Probe 20', 'Probe 21', 'Probe 23', 'Probe 24'],
                   'July2025-SS1-eval' : ['Probe 2', 'Probe 6', 'Probe 13', 'Probe 15', 'Probe 33', 'Probe 42'],
                   'July2025-SS2-eval' : ['Probe 4', 'Probe 14', 'Probe 21', 'Probe 26', 'Probe 39', 'Probe 45'],
                   'July2025-SS3-eval' : ['Probe 11', 'Probe 16', 'Probe 38', 'Probe 41', 'Probe 43', 'Probe 51']
                   }

PROBE_SETS = [['July2025-AF1-eval', 'July2025-MF1-eval', 'July2025-PS1-eval', 'July2025-SS1-eval'],
              ['July2025-AF2-eval', 'July2025-MF2-eval', 'July2025-PS2-eval', 'July2025-SS2-eval'],
              ['July2025-AF3-eval', 'July2025-MF3-eval', 'July2025-PS3-eval', 'July2025-SS3-eval']
              ]

KDMA_MAP = {'affiliation': 'af', 'merit': 'mf', 'personal_safety': 'ps', 'search': 'ss'}
BASELINE_ADM_NAME = 'ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3'
ALIGNED_ADM_NAME = 'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-Mistral-7B-Instruct-v0.3'


def main(mongo_db):
    # Create a new DB to store all the data; get the collections.
    multi_kdmas_4d = mongo_db[FOUR_D_COLLECTION]
    adm_collection = mongo_db['admTargetRuns']
    userCollection = mongo_db['userScenarioResults']
    if WRITE_TO_DB:
        multi_kdmas_4d.drop()

    # Run the dev script to get human kdmas; store in list for easy indexing.
    os.system(f'{PYTHON_CMD} dev_scripts/get_p2_4d_text_kdmas.py')
    file = open('text_kdmas.csv', 'r', encoding='utf-8')
    reader = csv.reader(file)
    text_kdma_header = next(reader)
    text_kdmas = []
    for line in reader:
        if len(line) > 2:  # Skip blank lines
            text_kdmas.append(line)
    # clean up csv file
    file.close()

    cur_line = 0
    total_lines = len(text_kdmas)
    for line in text_kdmas:
        cur_line += 1
        pid = line[text_kdma_header.index('PID')]
        print(f"\nProcessing pid {pid} ({cur_line} of {total_lines}).")

        # Create the document
        new_doc = {
            'admName': ALIGNED_ADM_NAME,
            'pid': pid,
            'human_set': -1,
            'afTarget': float(line[text_kdma_header.index('AF')]),
            'mfTarget': float(line[text_kdma_header.index('MF')]),
            'psTarget': float(line[text_kdma_header.index('PS')]),
            'ssTarget': float(line[text_kdma_header.index('SS')]),
            'af_kdma_aligned_set1':    -1, # We don't strictly have to add all of these here,
            'af_kdma_aligned_set2':    -1, # but it helps put the columns in order in MongoDB
            'af_kdma_aligned_set3':    -1, # and when exporting to a csv for Jennifer, especially
            'af_kdma_aligned_avg':     -1, # since we can replace these headers with the human-friendly
            'mf_kdma_aligned_set1':    -1, # headers like we see in RQ2.
            'mf_kdma_aligned_set2':    -1,
            'mf_kdma_aligned_set3':    -1,
            'mf_kdma_aligned_avg':     -1,
            'ps_kdma_aligned_set1':    -1,
            'ps_kdma_aligned_set2':    -1,
            'ps_kdma_aligned_set3':    -1,
            'ps_kdma_aligned_avg':     -1,
            'ss_kdma_aligned_set1':    -1,
            'ss_kdma_aligned_set2':    -1,
            'ss_kdma_aligned_set3':    -1,
            'ss_kdma_aligned_avg':     -1,
            'af_kdma_baseline_set1':   -1,
            'af_kdma_baseline_set2':   -1,
            'af_kdma_baseline_set3':   -1,
            'af_kdma_baseline_avg':    -1,
            'mf_kdma_baseline_set1':   -1,
            'mf_kdma_baseline_set2':   -1,
            'mf_kdma_baseline_set3':   -1,
            'mf_kdma_baseline_avg':    -1,
            'ps_kdma_baseline_set1':   -1,
            'ps_kdma_baseline_set2':   -1,
            'ps_kdma_baseline_set3':   -1,
            'ps_kdma_baseline_avg':    -1,
            'ss_kdma_baseline_set1':   -1,
            'ss_kdma_baseline_set2':   -1,
            'ss_kdma_baseline_set3':   -1,
            'ss_kdma_baseline_avg':    -1,
            'set1_aligned_alignment':  -1,
            'set2_aligned_alignment':  -1,
            'set3_aligned_alignment':  -1,
            'avg_aligned_alignment':   -1,
            'set1_baseline_alignment': -1,
            'set2_baseline_alignment': -1,
            'set3_baseline_alignment': -1,
            'avg_baseline_alignment':  -1
        }

        text_scenario = userCollection.find_one({'evalNumber': JULY_EVAL_NUM, 'participantID': pid}) # Any one will do
        human_session_id = text_scenario['combinedSessionId']
        scenario_id = text_scenario['scenario_id']
        new_doc['human_set'] = 1 if '1' in scenario_id else 3 if '3' in scenario_id else 2

        # Process aligned and baseline ADMs similarly but separately, culminating in a full document / csv line
        for adm_name in [ALIGNED_ADM_NAME, BASELINE_ADM_NAME]:
            print(f"  Processing adm_name {adm_name}.")
            adm_type = 'aligned' if adm_name == ALIGNED_ADM_NAME else 'baseline'
            kdma_sums = {'affiliation': 0, 'merit': 0, 'personal_safety': 0, 'search': 0}
            alignment_sum = 0
            alignment_count = 0

            # Process a single probe set for a given ADM
            for probe_set in PROBE_SETS:
                setnum = probe_set[0][-6] # e.g., ['July2025-AF1-eval', 'July2025-MF1-eval', 'July2025-PS1-eval', 'July2025-SS1-eval'] -> 1
                print(f"    Processing Set #{setnum}.")
                comboProbeList = [] # Collects the entire sets of probes/responses for e.g. AF1+MF1+PS1+SS1

                # Collect all ADM responses for all KDMAs in the current set.
                for scenario_id in probe_set: # e.g., 'July2025-AF1-eval'
                    print(f"      Processing scenario {scenario_id}.")
                    cur_kdma = scenario_id[9:11] # e.g., 'July2025-AF1-eval' -> 'AF'
                    adm_run = adm_collection.find_one({'evalNumber': FOUR_D_EVAL_NUM, 'synthetic': {'$exists': False},
                                                      'evaluation.adm_name': adm_name, 'alignment_target': f"target{cur_line}",
                                                      'scenario': f"July2025-{cur_kdma}-eval"})

                    # Collect all ADM responses for the specified scenario (e.g., AF1, MF2, SS3, etc.)
                    def collect_adm_responses(scenario: str) -> list:
                        responses = []
                        for entry in adm_run["history"]:
                            if entry["command"] == "Respond to TA1 Probe":
                                probe_id = entry['parameters']['probe_id']
                                if probe_id in PROBE_MAP[scenario]:
                                    if VERBOSE:
                                        print(f'        Adding response: {scenario}, {probe_id}, {entry["parameters"]["choice"]}')
                                    responses.append({"probe_id": probe_id, "justification": "justification",
                                                        "scenario_id": scenario, "choice": entry["parameters"]["choice"]})
                        return responses

                    comboProbeList.extend(collect_adm_responses(scenario_id))

                # Create a session with the probeset probe ids & responses, and collect the resulting kdma value.
                if HIT_TA1_SERVER:
                    combinedADMsessionId = requests.post(f"{ADEPT_URL}api/v1/new_session").text.replace('"', "").strip()
                    send = requests.post(f"{ADEPT_URL}api/v1/responses",
                                         json={"responses": comboProbeList, "session_id": combinedADMsessionId})
                    if 'status' in send.json():
                        print(send.json())

                    kdmas = requests.get(f'{ADEPT_URL}api/v1/computed_kdma_profile?session_id={combinedADMsessionId}').json()
                else:
                    combinedADMsessionId = 'foobar'
                    kdmas = [{'kdma': 'affiliation', 'value': random.random()}, {'kdma': 'merit', 'value': random.random()},
                             {'kdma': 'personal_safety', 'value': random.random()}, {'kdma': 'search', 'value': random.random()}
                             ]

                # Populate <kdma>_kdma_<aligned}baseline>_set<n> field and store value to compute average.
                for kdma in kdmas:
                    kdma_name = kdma['kdma']
                    kdma_value = kdma['value']
                    kdma_sums[kdma_name] += kdma_value
                    kdma_field = f"{KDMA_MAP[kdma_name]}_kdma_{adm_type}_set{setnum}"
                    if VERBOSE:
                        print(f"      Setting kdma field {kdma_field} to {kdma_value}.")
                    new_doc[kdma_field] = kdma_value

                # Get the alignment score, save it for the set, and add it to the total.
                response = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions?session_id_1={human_session_id}&session_id_2={combinedADMsessionId}').json() \
                    if HIT_TA1_SERVER else {'score': random.random()}

                if 'score' in response:
                    # Update average alignment
                    alignment_value = response['score']
                    alignment_sum += alignment_value
                    alignment_count += 1
                    alignment_field = f"set{setnum}_{adm_type}_alignment"
                    if VERBOSE:
                        print(f"      Setting alignment set field {alignment_field} to {alignment_value}")
                    new_doc[alignment_field] = alignment_value
                else:
                    print(f"Warning: could not get comparison score for text session {human_session_id} and adm session {combinedADMsessionId}.")

            # Calculate averages across sets and store in the document
            for kdma_name in kdma_sums:
                kdma_field = f"{KDMA_MAP[kdma_name]}_kdma_{adm_type}_avg"
                kdma_avg = kdma_sums[kdma_name] / len(PROBE_SETS)
                if VERBOSE:
                    print(f"      Calculating averages for {kdma_name} and storing in {kdma_field}.")
                new_doc[kdma_field] = kdma_avg
            avg_align_field = f"avg_{adm_type}_alignment"
            alignment_avg = alignment_sum / max(1, alignment_count)
            if VERBOSE:
                print(f"      Calculating average alignment and storing in {avg_align_field}.")
            new_doc[avg_align_field] = alignment_avg

        if WRITE_TO_DB:
            multi_kdmas_4d.insert_one(new_doc)

    print(f"\nMulti-KDMA Data collection '{FOUR_D_COLLECTION}' has {'' if WRITE_TO_DB else 'NOT '}been created and populated.")


if __name__ == '__main__':
    # Instantiate mongo client
    client = MongoClient(config('MONGO_URL'))
    mongo_db = client.dashboard
    main(mongo_db)