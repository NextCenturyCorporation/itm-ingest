import argparse
import random
import requests
from pymongo import MongoClient
from decouple import config 
from dataclasses import dataclass
from scripts._1_2_4_feb_2026_rq2 import read_probe_sets
from scripts._1_2_4_feb_2026_rq2 import get_ta1_calculations
from scripts._1_2_4_feb_2026_rq2 import add_1D_scores

"""
This script serves as a postscript for script 124, to be executed after 4D ADM runs are complete.
It reads in probe set csv file, collects the ADM responses from 4D runs from the database, feeds the probes and responses to TA1 to
collect alignment and kdma values, and creates synthetic ADM runs as if the ADM had run on each probe set.
"""

# These are constants that cannot be overridden via the command line
EVALUATION_TYPE = 'Feb2026'
EVALUATION_NAME = 'Phase 2 February 2026 Evaluation'
EVAL_NUM = 15
DOMAIN = 'p2triage'
TA1_NAME = 'adept'
HIT_TA1_SERVER = True # Useful for testing or if you can't reach the TA1 server

# These are default values that can be overridden via the command line
NUM_SUBSETS = 25
VERBOSE = False
WRITE_TO_DB = True


BAD_ADMS = ['ALIGN-ADM-Ph2-DirectRegression-BertRelevance-Mistral-7B-Instruct-v0.3__6a3e924b-967d-4498-bcb7-48f0b7dd24d2',
            'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-Mistral-7B-Instruct-v0.3__114a4f1c-9223-461c-b0b1-d52e7596179e']

kdma_abbreviations: list = ['AF', 'MF', 'PS', 'SS']

# A list of all Adm_data (the actual ADM runs) that will be used to create synthetic ADM runs.
# Each entry in the list contains the info for a single ADM run (one per target, each of baseline and aligned)
all_adm_data: list = []

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
    adm_cursor = adm_collection.find({'evalNumber': 15, "alignment_target": {"$regex": "Feb2026-AF.-MF.-PS.-SS."}, 'synthetic': {'$exists': False}})
    adm_4d_runs = list(adm_cursor)
    print(f"Retrieved {len(adm_4d_runs)} non-synthetic 4D ADM runs from database.")

    # A list of all probe responses for all adm runs for this attribute (one per target/adm type combination)
    for adm_run in adm_4d_runs:
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
    print("Stored all 4D ADM data (probe responses)")


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
    error_count = 0
    req_session = None

    if HIT_TA1_SERVER:
        req_session = requests.Session()

    for adm_data in all_adm_data:
        adm_name = adm_data.adm_name
        target = adm_data.alignment_target_id
        orig_scenario_id = adm_data.scenario_id
        attribute = 'AF-MF-PS-SS' # We know it's only 4D ADM runs
        set_construction = '4D'

        print(f"Processing adm data for {adm_name}, {target}, {orig_scenario_id}.")
        for subset_num in range(1, NUM_SUBSETS + 1):
            probe_set: list = probe_sets[subset_num-1]
            if VERBOSE:
                print(f"Processing probe subset #{subset_num}: {probe_set}")
            probe_set = [probe_id for probe_id in probe_set if any(kdma in probe_id for kdma in kdma_abbreviations)]
            sent_probes, ta1_id, alignment_score, kdmas = get_ta1_calculations(req_session, adm_data, probe_set)
            if not alignment_score or not kdmas:
                error_count += 1
            synth_scenario_id = f"{EVALUATION_TYPE}-{attribute}r{subset_num}-eval" # e.g., "Feb2026-AF-MF-PS-SSr23-eval"
            synth_scenario_name = adm_data.scenario_name.replace('Set', 'Random Set ' + str(subset_num)) # e.g., "Full Evaluation Set 23"
            if VERBOSE:
                print(f"  {synth_scenario_id}: Got alignment score of {alignment_score} and kdmas of {kdmas}")
            evaluation: dict = {'evalName': EVALUATION_NAME,
                                'evalNumber': EVAL_NUM,
                                'scenario_name': synth_scenario_name,
                                'scenario_id': synth_scenario_id,
                                'set_construction': set_construction,
                                'alignment_target_id': target,
                                'adm_name': adm_name,
                                'adm_profile': 'baseline' if 'baseline' in adm_data.adm_name.lower() else 'aligned',
                                'domain': DOMAIN,
                                'start_time': 'N/A',
                                'end_time': 'N/A',
                                'ta1_name': TA1_NAME,
                                'ta3_session_id': 'N/A'}
            results: dict = {'ta1_session_id': ta1_id, 'alignment_score': alignment_score, 'kdmas': kdmas}
            error_count += add_1D_scores(req_session, adm_data, probe_set, results)
            synthethic_adm_run: dict = {'evaluation': evaluation, 'results': results, 'evalNumber': EVAL_NUM, 'scenario': synth_scenario_id,
                                        'evalName': EVALUATION_NAME, 'adm_name': adm_name, 'synthetic': True,
                                        'probes': sent_probes, 'alignment_target': target}
            total_synthetic_adm_runs += 1
            all_synthethic_adm_runs.append(synthethic_adm_run)

    if HIT_TA1_SERVER:
        req_session.close()

    if WRITE_TO_DB:
        result = adm_collection.insert_many(all_synthethic_adm_runs)
        if total_synthetic_adm_runs != len(result.inserted_ids):
            print(f'Total runs mismatch: expected {total_synthetic_adm_runs} but wrote {len(result.inserted_ids)} documents to database instead.')
    else:
        print(f"{total_synthetic_adm_runs} synthetic ADM runs NOT uploaded to database.")

    print(f"Finished with a total of {error_count} error(s).  See logs for affected ADM runs.")


def main(mongo_db):
    print('\nReading probe sets from csv...')
    probe_sets: list = read_probe_sets()
    adm_collection = mongo_db['admTargetRuns']

    if WRITE_TO_DB:
        print('Deleting bad/aborted ADMs.')
        for adm_name in BAD_ADMS:
            adm_collection.delete_many({'evalNumber': EVAL_NUM, 'adm_name': adm_name})

    print('Getting ADM data from full Evaluation run...')
    load_adm_data(mongo_db)

    # Clear out any previous run of this script
    if WRITE_TO_DB:
        adm_collection.delete_many({'evalNumber': EVAL_NUM, 'alignment_target': {"$regex": "Feb2026-AF.-MF.-PS.-SS."}, 'synthetic': True})

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
