import csv
import argparse
import os
import random
import requests
from pymongo import MongoClient
from decouple import config 
from dataclasses import dataclass
from typing import Tuple

"""
For RQ2, ADMs will be run on evaluation (hold-out) probes at a variety of alignment targets to collect probe responses.
Previously, we post-constructed N probe sets of 32 probes (8 probes per attribute) based on Latin square selection,
outputting a csv file of all probe sets.
This script reads in this csv file, collects the ADM responses from the database, feeds the probes and responses to TA1 to
collect alignment and kdma values, and creates synthetic ADM runs as if the ADM had run on each probe set.

This script was adapted from _1_1_0_adaptive_experiment.py, which contained some of the necessary building blocks / logic.
"""

# These are constants that cannot be overridden via the command line
EVALUATION_TYPE = 'Feb2026'
EVALUATION_NAME = 'Phase 2 February 2026 Evaluation'
EVAL_NUM = 15
DOMAIN = 'p2triage'
TA1_NAME = 'adept'
ADEPT_URL = config("ADEPT_URL")
HIT_TA1_SERVER = True # Useful for testing or if you can't reach the TA1 server
PROBES_PER_SET = 8
PROBESET_CSV_FILE = os.path.join('phase2', EVALUATION_TYPE, 'RQ2-probesets.csv')

# These are default values that can be overridden via the command line
NUM_SUBSETS = 25
VERBOSE = False
WRITE_TO_DB = True

kdma_abbreviations: list = ['AF', 'MF', 'PS', 'SS']

# A list of all Adm_data (the actual ADM runs) that will be used to create synthetic ADM runs.
# Each entry in the list contains the info for a single ADM run (one per target, each of baseline and aligned)
all_adm_data: list = []
# e.g., [{'adm_name': 'baseline', 'alignment_target_id': 'ADEPT-July2025-affiliation-0.3', 'scenario_id': 'July2025-AFr12-eval',
#                'probe_responses': {'Probe 1': "Response 1-A", ... }, {'adm_name': 'aligned', ... }]


@dataclass
class Adm_data:
    adm_name: str
    alignment_target_id: str
    scenario_id: str
    scenario_name: str
    probe_responses: dict


# Get ADM data from full eval run and store probe responses locally
def load_adm_data(mongo_db):
    adm_collection = mongo_db['admTargetRuns']
    adm_cursor = adm_collection.find({'evalNumber': 15, "scenario": {"$regex": "-eval"}, 'synthetic': {'$exists': False}})
    adm_runs = list(adm_cursor)
    print(f"Retrieved {len(adm_runs)} non-synthetic adm runs from database.")

    # A list of all probe responses for all adm runs for this attribute (one per target/adm type combination)
    for adm_run in adm_runs:
        probe_responses = {}
        for h in adm_run['history']:
            if h['command'] == 'Respond to TA1 Probe':
                probe_responses[h['parameters']['probe_id']] = h['parameters']['choice']
        adm_data = Adm_data(adm_run['adm_name'],
                            adm_run['alignment_target'],
                            adm_run['scenario'],
                            adm_run['evaluation']['scenario_name'],
                            probe_responses)
        if VERBOSE:
            print(f"Adding {len(adm_data.probe_responses)} probe responses for {adm_data.adm_name} for scenario {adm_data.scenario_id} at alignment {adm_data.alignment_target_id}")
        all_adm_data.append(adm_data)

    adm_cursor.close()
    print("Stored all ADM data (probe responses)")


# Read probe sets from csv
def read_probe_sets():
    headers = []
    for kdma in kdma_abbreviations:
        for probe_num in range(PROBES_PER_SET):
            column_name = f'Probe-{kdma}{probe_num+1}'
            headers.append(column_name)

    csvfile = open(PROBESET_CSV_FILE, 'r', encoding='utf-8')
    reader: csv.DictReader = csv.DictReader(csvfile, fieldnames=headers, restkey='junk')
    next(reader) # skip header

    # Process the csv file
    print(f"Reading {NUM_SUBSETS} RQ2 probe subsets from {PROBESET_CSV_FILE}.")
    probe_sets: list = []
    for line in reader:
        if len(probe_sets) > NUM_SUBSETS: # User specified less than 
            continue
        probe_set = []
        for field in headers:
            probe_set.append(line[field])
        probe_sets.append(probe_set)
    csvfile.close()
    return probe_sets


# Adapted from dbutils.send_probes
def send_probes(probe_url, session_id, probes: dict, scenario)-> None:
    for probe in probes:
        requests.post(probe_url, json={
            "response": {
                "probe_id": probe['probe_id'],
                "choice": probe['choice'],
                "justification": "justification",
                "scenario_id": scenario,
            },
            "session_id": session_id
        })


"""
    Create a TA1 session
    Respond to the random probes based on the adm_run's probe_responses
    Calculate session alignment against adm_data[target] and get kdma values
"""
def get_ta1_calculations(adm_data: Adm_data, probe_ids: list) -> Tuple[list, str, float, list]:
    probes = []
    for probe_id in probe_ids:
        probes.append({'probe_id': probe_id, 'choice': adm_data.probe_responses[probe_id]})
    if HIT_TA1_SERVER:
        session_id = requests.post(f'{ADEPT_URL}api/v1/new_session').text.replace('"', '').strip()
        send_probes(f'{ADEPT_URL}api/v1/response', session_id, probes, adm_data.scenario_id)
        session_alignment = requests.get(f'{ADEPT_URL}api/v1/alignment/session?session_id={session_id}&target_id={adm_data.alignment_target_id}&population=false').json()
        kdmas = requests.get(f'{ADEPT_URL}api/v1/computed_kdma_profile?session_id={session_id}').json()
        return probes, session_id, session_alignment['score'], kdmas
    else:
        return probes, 'foobar', random.uniform(-3.0, 3.0), \
            [{'kdma': 'affiliation', 'value': random.random()}, {'kdma': 'merit', 'value': random.random()},
             {'kdma': 'personal_safety', 'value': random.random()}, {'kdma': 'search', 'value': random.random()}
             ]


# Create attribute-specific 1D mini-probesets and add attribute-specific alignment score and TA1 session ID to the synthetic ADM's results
def add_1D_scores(adm_data: Adm_data, probe_ids: list, results: dict):
    all_attribute_data = []
    for kdma in kdma_abbreviations:
        attribute_data = {}
        mini_probeset = [probe_id for probe_id in probe_ids if kdma in probe_id]
        probes, ta1_id, alignment_score, kdmas = get_ta1_calculations(adm_data, mini_probeset)
        attribute_data[kdma] = {'ta1_session_id': ta1_id, 'alignment_score': alignment_score, 'kdmas': kdmas, 'probes': probes}
        all_attribute_data.append(attribute_data)

    results['attribute_data'] = all_attribute_data


"""
  Create synthetic ADM run for random assessment set:
  clear out previous synthetic runs for this evaluation
  For every ADM run
    Determine attribute from scenario ID (e.g., Feb2026-AF-eval, Feb2026-AF-PS-eval, or Feb2026-eval)
    For every probeset (n=NUM_SUBSETS)
      Get the nth probeset
      Get alignment and kdmas from TA1 based on ADM choices to the probeset IDs
      Create synthetic scenario id and name, e.g. "July2025-AFr23-eval" and "Affiliation Focus Random Set 23"
      Create synthetic row in admTargetRuns populating it with content from adm_data[target], calculated session alignment, kdmas, and scenario id/name
      If it's a 4D target/scenario, then for each attribute
        Create attribute-specific 1D mini-probesets and add attribute-specific alignment score and TA1 session ID to the synthetic ADM's results
"""
def create_synthetic_adm_runs(mongo_db, probe_sets: list):
    adm_collection = mongo_db['admTargetRuns']
    total_synthetic_adm_runs = 0
    all_synthethic_adm_runs = []

    for adm_data in all_adm_data:
        adm_name = adm_data.adm_name
        target = adm_data.alignment_target_id
        orig_scenario_id = adm_data.scenario_id
        attribute = orig_scenario_id[len(EVALUATION_TYPE)+1:-5] # skip e.g. leading 'Feb2026-' and trailing '-eval'
        if attribute == '':
            attribute = 'AF-MF-PS-SS'

        print(f"Processing adm data for {adm_name}, {target}, {orig_scenario_id}.")
        for subset_num in range(1, NUM_SUBSETS + 1):
            probe_set: list = probe_sets[subset_num-1]
            if VERBOSE:
                print(f"Processing probe subset #{subset_num}: {probe_set}")
            acronyms: list = attribute.split('-')
            set_construction = str(len(acronyms)) + 'D'
            probe_set = [probe_id for probe_id in probe_set if any(kdma in probe_id for kdma in acronyms)]
            if set_construction == '1D': # Need to convert 2D-style probe IDs to 1D
                probe_set = [probe_id.split('.')[1] for probe_id in probe_set]
            sent_probes, ta1_id, alignment_score, kdmas = get_ta1_calculations(adm_data, probe_set)
            synth_scenario_id = f"{EVALUATION_TYPE}-{attribute}r{subset_num}-eval" # e.g., "July2025-AFr23-eval"
            synth_scenario_name = adm_data.scenario_name.replace('Set', 'Random Set ' + str(subset_num)) # e.g., "Search vs Stay Random Set 23"
            if VERBOSE:
                print(f"  {synth_scenario_id}: Got alignment score of {alignment_score} and kdmas of {kdmas}")
            evaluation: dict = {'evalName': EVALUATION_NAME,
                                'evalNumber': EVAL_NUM,
                                'scenario_name': synth_scenario_name,
                                'scenario_id': synth_scenario_id,
                                'set_construction': set_construction,
                                'alignment_target_id': adm_data.alignment_target_id,
                                'adm_name': adm_data.adm_name,
                                'adm_profile': 'baseline' if 'baseline' in adm_data.adm_name.lower() else 'aligned',
                                'domain': DOMAIN,
                                'start_time': 'N/A',
                                'end_time': 'N/A',
                                'ta1_name': TA1_NAME,
                                'ta3_session_id': 'N/A'}
            results: dict = {'ta1_session_id': ta1_id, 'alignment_score': alignment_score, 'kdmas': kdmas}
            if set_construction == '4D':
                add_1D_scores(adm_data, probe_set, results)
            synthethic_adm_run: dict = {'evaluation': evaluation, 'results': results, 'evalNumber': EVAL_NUM, 'scenario': synth_scenario_id,
                                        'evalName': EVALUATION_NAME, 'adm_name': adm_data.adm_name, 'synthetic': True,
                                        'probes': sent_probes, 'alignment_target': adm_data.alignment_target_id}
            total_synthetic_adm_runs += 1
            all_synthethic_adm_runs.append(synthethic_adm_run)

    if (WRITE_TO_DB):
        result = adm_collection.insert_many(all_synthethic_adm_runs)
        if total_synthetic_adm_runs != len(result.inserted_ids):
            print(f'Total runs mismatch: expected {total_synthetic_adm_runs} but wrote {len(result.inserted_ids)} documents to database instead.')
    else:
        print(f"{total_synthetic_adm_runs} synthetic ADM runs NOT uploaded to database.")


def create_4D_adm(mongo_db, probe_sets: list, alignment_target: str):
    all_history = []
    sent_probes = []
    # Iterate through probe sets, adding a probe_id/choice pair to sent_probes for each probe and Respond to TA1 command to history
    for probe_set in probe_sets:
        for probe_id in probe_set:
            patient = random.choice(['A', 'B'])
            response = f"Response {probe_id.split()[-1]}-{patient}"
            sent_probes.append({'probe_id': probe_id, 'choice': response})
            params = {'session_id': 'my_ta1_id', 'scenario_id': 'Feb2026-eval', 'probe_id': probe_id,
                      'choice': response, 'action_id': f"treat_patient_{patient.lower()}", 'justification': 'Fake ADM Justification'}
            history = {'command': 'Respond to TA1 Probe', 'parameters': params, 'response': None}
            all_history.append(history)

    evaluation: dict = {'evalName': EVALUATION_NAME,
                        'evalNumber': EVAL_NUM,
                        'scenario_name': 'Full Evaluation Set',
                        'scenario_id': 'Feb2026-eval',
                        'alignment_target_id': alignment_target,
                        'adm_name': "Fake ADM",
                        'adm_profile': '',
                        'domain': DOMAIN,
                        'start_time': 'yesterday',
                        'end_time': 'today',
                        'ta1_name': TA1_NAME,
                        'ta3_session_id': 'my_ta3_id'}
    results: dict = {'ta1_session_id': 'my_ta1_id', 'alignment_score': 'Not requested', 'kdmas': None}
    fake_adm_run: dict = {'evaluation': evaluation, 'results': results, 'history': all_history, 'adm_name': "Fake ADM",
                     'scenario': 'Feb2026-eval', 'alignment_target': alignment_target, 'evalNumber': EVAL_NUM,
                     'evalName': EVALUATION_NAME}

    if VERBOSE:
        print(f"Adding Fake ADM: {fake_adm_run}")
    if (WRITE_TO_DB):
        adm_collection = mongo_db['admTargetRuns']
        adm_collection.insert_one(fake_adm_run)


def main(mongo_db):
    print('\nReading probe sets from csv...')
    probe_sets: list = read_probe_sets()

    print('Getting ADM data from full Evaluation run...')
    create_4D_adm(mongo_db, probe_sets, 'Feb2026-AF3-MF3-PS3-SS3')
    load_adm_data(mongo_db)

    # Clear out any previous run
    if WRITE_TO_DB:
        mongo_db['admTargetRuns'].delete_many({'evalNumber': EVAL_NUM, 'synthetic': True})

    print(f"\nCreating synthetic ADM runs.")
    create_synthetic_adm_runs(mongo_db, probe_sets)
    print('\nDone.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generates synthetic ADM results for random RQ2 probe subsets.')
    parser.add_argument('-c', '--count', metavar='count', required=False, type=int, default=NUM_SUBSETS,
                        help=f"How many probe subsets to process (<= {NUM_SUBSETS}, default {NUM_SUBSETS})")
    parser.add_argument('-n', '--no_output', action='store_true', required=False, default=False,
                        help='Do not write to the MongoDB')
    parser.add_argument('-v', '--verbose', action='store_true', required=False, default=False,
                        help='Verbose logging')

    args = parser.parse_args()
    if args.count > 0:
        NUM_SUBSETS = min(args.count, NUM_SUBSETS)
    if args.verbose:
        VERBOSE = True
    if args.no_output:
        WRITE_TO_DB = False

    client = MongoClient(config('MONGO_URL'))
    main(client.dashboard)
