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
Previously, we post-constructed N probe sets of 24 probes (8 probes per attribute) based on Latin square selection (binary)
or random selection (trinary), outputting two csv files, one of all binary probe sets, the other all trinary probe sets.
This script reads in these csv files, collects the ADM responses from the database, feeds the probes and responses to TA1 to
collect alignment and kdma values, and creates synthetic ADM runs as if the ADM had run on each probe set.

This script was adapted from _1_2_4_feb_2026_rq2.py, which was the Feb2026 equivalent RQ2 script.
"""

# These are constants that cannot be overridden via the command line
EVALUATION_TYPE = 'June2026'
EVALUATION_NAME = 'Phase 2 June 2026 Evaluation'
EVAL_NUM = 17
DOMAIN = 'p2triage'
TA1_NAME = 'adept'
ADEPT_URL = config("ADEPT_URL")
HIT_TA1_SERVER = True # Useful for testing or if you can't reach the TA1 server
PROBES_PER_SET = 8
BINARY_PROBESET_CSV_FILE = os.path.join('phase2', EVALUATION_TYPE.lower(), 'RQ2-probesets.csv')
TRINARY_PROBESET_CSV_FILE = os.path.join('phase2', EVALUATION_TYPE.lower(), 'RQ2-probesets-trinary.csv')

# These are default values that can be overridden via the command line
NUM_SUBSETS = 25
VERBOSE = False
WRITE_TO_DB = True

# A list of all Adm_data (the actual ADM runs) that will be used to create synthetic ADM runs.
# Each entry in the list contains the info for a single ADM run (one per target, each of baseline and aligned)
all_adm_data: list = []
# e.g., [{'adm_name': 'baseline', 'alignment_target_id': 'Jun2026-AF-binomial-110', 'scenario_id': 'June2026-AFr12-eval',
#                'probe_responses': {'Probe 1': "Response 1-A", ... }, {'adm_name': 'aligned', ... }]

BAD_ADMS = ['ALIGN-ADM-Random__73bb07e1-2fdb-4bf4-b259-e15dd84e9e5c'
            ]
ORPHAN_ADM = {'old_name': 'ALIGN-ADM-OutlinesBaseline-DeepSeek-R1-Distill-Llama-8B__6d9ffe7b-a882-4846-9d8d-95a1644c76c2',
              'new_name': 'ALIGN-ADM-OutlinesBaseline-DeepSeek-R1-Distill-Llama-8B_01_12'}
ORPHAN_ADM = None


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
    adm_cursor = adm_collection.find({'evalNumber': EVAL_NUM, "scenario": {"$regex": "-eval"}, 'synthetic': {'$exists': False}})
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
def read_probe_sets(filespec, kdma_abbreviations):
    headers = []
    for kdma in kdma_abbreviations:
        for probe_num in range(PROBES_PER_SET):
            column_name = f'Probe-{kdma}{probe_num+1}'
            headers.append(column_name)

    csvfile = open(filespec, 'r', encoding='utf-8')
    reader: csv.DictReader = csv.DictReader(csvfile, fieldnames=headers, restkey='junk')
    next(reader) # skip header

    # Process the csv file
    print(f"Reading {NUM_SUBSETS} RQ2 probe subsets from {filespec}.")
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
def send_probes(req_session, probe_url, session_id, probes: dict, scenario)-> None:
    for probe in probes:
        req_session.post(probe_url, json={
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
def get_ta1_calculations(req_session, adm_data: Adm_data, probe_ids: list) -> Tuple[list, str, float, list]:
    probes = []
    session_id = None
    for probe_id in probe_ids:
        probes.append({'probe_id': probe_id, 'choice': adm_data.probe_responses[probe_id]})
    if HIT_TA1_SERVER:
        try:
            session_id = req_session.post(f'{ADEPT_URL}api/v1/new_session').text.replace('"', '').strip()
            send_probes(req_session, f'{ADEPT_URL}api/v1/response', session_id, probes, adm_data.scenario_id)
            session_alignment = req_session.get(f'{ADEPT_URL}api/v1/alignment/session?session_id={session_id}&target_id={adm_data.alignment_target_id}&population=false').json()
            kdmas = req_session.get(f'{ADEPT_URL}api/v1/computed_kdma_profile?session_id={session_id}').json()
            return probes, session_id, session_alignment['score'], kdmas
        except Exception:
            print(f"--> Error: could not get alignment/kdmas for {adm_data.adm_name} in scenario {adm_data.scenario_id} at target {adm_data.alignment_target_id}.")
            return probes, session_id, None, None
    else:
        return probes, 'random_ta1_id', random.uniform(-3.0, 3.0), \
            [{'kdma': 'affiliation', 'value': random.random()},
             {'kdma': 'personal_safety', 'value': random.random()}, {'kdma': 'search', 'value': random.random()}
             ]


"""
  Create synthetic ADM run for random assessment set:
  For every ADM run
    Determine attribute from scenario ID (e.g., June2026-AF-eval or June2026-AF-SS-eval)
    For every probeset (n=NUM_SUBSETS)
      Get the nth probeset (either binary or trinary depending on original ADM scenario)
      Get alignment and kdmas from TA1 based on ADM choices to the probeset IDs
      Create synthetic scenario id and name, e.g. "June2026-AFr23-eval" and "Affiliation Focus Random Set 23"
      Create synthetic row in admTargetRuns populating it with content from adm_data[target], calculated session alignment, kdmas, and scenario id/name
"""
def create_synthetic_adm_runs(mongo_db, binary_probe_sets: list, trinary_probe_sets: list) -> int:
    adm_collection = mongo_db['admTargetRuns']
    total_synthetic_adm_runs = 0
    all_synthethic_adm_runs = []
    error_count = 0
    req_session = None

    if HIT_TA1_SERVER:
        req_session = requests.Session()

    for adm_data in all_adm_data:
        adm_name = adm_data.adm_name
        target = adm_data.alignment_target_id
        orig_scenario_id = adm_data.scenario_id
        is_trinary = 'trinary' in orig_scenario_id
        truncation_offset = 13 if is_trinary else 5 # trailing '-eval' and (optionally) '-trinary'
        attribute = orig_scenario_id[len(EVALUATION_TYPE)+1:-truncation_offset] # skip e.g. leading 'Jun2026-' and trailing '-eval' and '-trinary'
        if attribute == '':
            attribute = 'AF-MF-PS-SS'

        if VERBOSE:
            print()
        print(f"Processing adm data for {adm_name}, {target}, {orig_scenario_id}.")
        for subset_num in range(1, NUM_SUBSETS + 1):
            probe_set: list = trinary_probe_sets[subset_num-1] if is_trinary else binary_probe_sets[subset_num-1]
            if VERBOSE:
                print(f"-> Processing probe subset #{subset_num}: {probe_set}")
            acronyms: list = attribute.split('-')
            set_construction = str(len(acronyms)) + 'D'
            probe_set = [probe_id for probe_id in probe_set if any(kdma in probe_id for kdma in acronyms)]
            if set_construction == '1D': # Need to convert 2D-style probe IDs to 1D
                probe_set = [probe_id.split('.')[1] for probe_id in probe_set]
            sent_probes, ta1_id, alignment_score, kdmas = get_ta1_calculations(req_session, adm_data, probe_set)
            if not alignment_score or not kdmas:
                error_count += 1
            synth_scenario_id = f"{EVALUATION_TYPE}-{attribute}r{subset_num}-eval" # e.g., "June2026-AFr23-eval"
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
            synthethic_adm_run: dict = {'evaluation': evaluation, 'results': results, 'evalNumber': EVAL_NUM, 'scenario': synth_scenario_id,
                                        'evalName': EVALUATION_NAME, 'adm_name': adm_data.adm_name, 'synthetic': True,
                                        'probes': sent_probes, 'alignment_target': adm_data.alignment_target_id}
            total_synthetic_adm_runs += 1
            all_synthethic_adm_runs.append(synthethic_adm_run)

    if HIT_TA1_SERVER:
        req_session.close()

    if WRITE_TO_DB:
        result = adm_collection.insert_many(all_synthethic_adm_runs)
        if total_synthetic_adm_runs != len(result.inserted_ids):
            print(f'Total runs mismatch: expected {total_synthetic_adm_runs} but wrote {len(result.inserted_ids)} documents to database instead.')

    print(f"{total_synthetic_adm_runs} synthetic ADM runs {'' if WRITE_TO_DB else 'NOT '}uploaded to database.")
    print(f"Finished with a total of {error_count} error(s).{'  See logs for affected ADM runs.' if error_count else ''}")


def main(mongo_db):
    adm_collection = mongo_db['admTargetRuns']
    if WRITE_TO_DB:
        print('Deleting some bad/aborted ADMs.')
        for adm_name in BAD_ADMS:
            adm_collection.delete_many({'evalNumber': EVAL_NUM, 'adm_name': adm_name})
        if ORPHAN_ADM:
            adm_collection.update_one(
                    {'adm_name': ORPHAN_ADM['old_name']},
                    {'$set': {
                        'adm_name': ORPHAN_ADM['new_name'],
                        'evaluation.adm_name': ORPHAN_ADM['new_name']
                    }}
                )

    print('Getting ADM data from full Evaluation run...')
    load_adm_data(mongo_db)

    # Clear out any previous run
    if WRITE_TO_DB:
        adm_collection.delete_many({'evalNumber': EVAL_NUM, 'synthetic': True})

    print('\nReading binary probe sets from csv...')
    binary_probe_sets: list = read_probe_sets(BINARY_PROBESET_CSV_FILE, ['AF', 'PS', 'SS'])
    print('\nReading trinary probe sets from csv...')
    trinary_probe_sets: list = read_probe_sets(TRINARY_PROBESET_CSV_FILE, ['AF', 'PS'])
    print(f"\nCreating synthetic ADM runs.")
    create_synthetic_adm_runs(mongo_db, binary_probe_sets, trinary_probe_sets)

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
