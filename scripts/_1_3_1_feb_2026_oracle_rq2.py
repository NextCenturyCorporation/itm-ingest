import argparse
import random
import requests
from datetime import datetime
from math import isnan
from pymongo import MongoClient
from decouple import config 
from _1_2_4_feb_2026_rq2 import read_probe_sets
from _1_2_4_feb_2026_rq2 import send_probes

"""
This script serves as a postscript for scripts 124 and 129 to add a field to RQ2 for the oracle alignment.
It reads in the probe set csv file, creates a session for each probe set / alignment target combination
(always choosing choice A since it's ignored by the API anyway), then asks for oracle alignment.

It adds a column to the synthetic adm runs that contains the oracle alignment for that run,
serving as a "ceiling" alignment for that row.
"""

# These are constants that cannot be overridden via the command line
EVALUATION_TYPE = 'Feb2026'
EVALUATION_NAME = 'Phase 2 February 2026 Evaluation'
EVAL_NUM = 15
DOMAIN = 'p2triage'
TA1_NAME = 'adept'
ADEPT_URL = config("ADEPT_URL")
HIT_TA1_SERVER = True # Useful for testing or if you can't reach the TA1 server

# These are default values that can be overridden via the command line
NUM_SUBSETS = 25
VERBOSE = False
WRITE_TO_DB = True


kdma_abbreviations: list = ['AF', 'MF', 'PS', 'SS']


"""
    Calculate and return oracle session alignment for the specified probes in the specified scenario
    at the specified alignment target.
"""
def get_oracle_alignment(req_session, scenario_id: str, alignment_target: str, probe_ids: list) -> float:
    probes = []
    for probe_id in probe_ids:
        response = f"Response {probe_id.split()[-1]}-A"
        probes.append({'probe_id': probe_id, 'choice': response})
    if HIT_TA1_SERVER:
        try:
            session_id = req_session.post(f'{ADEPT_URL}api/v1/new_session').text.replace('"', '').strip()
            send_probes(req_session, f'{ADEPT_URL}api/v1/response', session_id, probes, scenario_id)
            session_alignment = req_session.get(f'{ADEPT_URL}api/v1/alignment/oracle_session?session_id={session_id}&target_id={alignment_target}').json()
            return session_alignment['score']
        except Exception:
            print(f"--> Error: could not get oracle alignment for target {alignment_target}.")
            return None
    else:
        return random.uniform(-3.0, 3.0)


"""
  Update synthetic ADM runs with an extra column: "oracle_alignment":
  For every aligned non-4D synthetic ADM
    Get the oracle alignment for that synthetic ADM's set and alignment target from `oracle_alignments`
      Update the synthetic ADM's database document to add the oracle alignment field
"""
def update_synthetic_adm_runs(adm_collection, oracle_alignments: dict):
    error_count = 0
    total_updated = 0
    adm_cursor = adm_collection.find({'evalNumber': EVAL_NUM, 'evaluation.adm_profile': 'aligned'})
    synth_adms = list(adm_cursor)
    if VERBOSE:
        print(f"Retrieved {len(synth_adms)} aligned synthetic ADM runs for evaluation {EVAL_NUM} from database.")

    for synth_adm in synth_adms:
        if synth_adm['evaluation']['set_construction'] == '4D':
            continue # Don't want 4D targets
        setnum = int(synth_adm['evaluation']['scenario_name'][-2:])
        if setnum > NUM_SUBSETS:
            continue # Not considering all subsets (generally only in testing)
        alignment_target = synth_adm['alignment_target']
        oracle_alignment = oracle_alignments[(setnum, alignment_target)]
        if VERBOSE:
            print(f"--> Got oracle alignment {oracle_alignment} for set {setnum} at target {alignment_target}.")
        if oracle_alignment:
            if WRITE_TO_DB:
                result = adm_collection.update_one({"_id": synth_adm["_id"]}, {"$set": {"oracle_alignment": oracle_alignment}})
                total_updated += result.modified_count
            else:
                total_updated += 1
        else:
            error_count += 1

    adm_cursor.close()
    print(f"{total_updated} synthetic ADM runs {'NOT ' if not WRITE_TO_DB else ''}updated in database.")
    print(f"Finished with a total of {error_count} error(s).  See logs for affected ADM runs.")


# Devise a list of non-4D alignment targets for the Evaluation by iterating through the synthetic ADMs.
def get_alignment_targets(adm_collection) -> list:
    alignment_targets = set()
    # This query was faster than others that were more precise.
    adm_cursor = adm_collection.find({'evalNumber': EVAL_NUM, 'synthetic': True})
    adm_runs = list(adm_cursor)
    if VERBOSE:
        print(f"In calculating alignment targets, we're considering {len(adm_runs)} ADMs.")
    for adm_run in adm_runs:
        alignment_target = adm_run['alignment_target']
        if len(alignment_target.split('-')) < 4: # Don't want 4D targets
            alignment_targets.add(alignment_target)
    adm_cursor.close()
    print(f"There are {len(alignment_targets)} targets.")
    return alignment_targets


"""
Get oracle alignments from TA1 server:
For each RQ2 subset
  For each Feb2026 non-4D alignment target
    Create a probe set with only the probes relevant to the alignment target
    Call the TA1 oracle alignment endpoint for the subset's probes and the current alignment target
    Save it in a dictionary of (setnum, target) -> float alignment
"""
def get_oracle_alignments(probe_sets: list, alignment_targets: list) -> dict:
    oracle_alignments = {}
    error_count = 0
    req_session = None

    if HIT_TA1_SERVER:
        req_session = requests.Session()

    for subset_num in range(1, NUM_SUBSETS + 1):
        orig_probe_set: list = probe_sets[subset_num-1] # Get the nth probeset
        print(f"Processing probe subset #{subset_num} at {datetime.now()}:")

        # For every alignment target from above list
        for alignment_target in alignment_targets:
            # Determine which probes should be in the session
            acronyms = [acronym for acronym in kdma_abbreviations if acronym in alignment_target]
            new_probe_set = [probe_id for probe_id in orig_probe_set if any(kdma in probe_id for kdma in acronyms)]
            if VERBOSE:
                print(f"---> Probe set for target {alignment_target}")
                print(new_probe_set)

            # Get oracle alignment score from TA1
            oracle_alignment = get_oracle_alignment(req_session, 'Feb2026-eval', alignment_target, new_probe_set)
            if not oracle_alignment or isnan(oracle_alignment):
                error_count += 1
                oracle_alignments[(subset_num, alignment_target)] = None
            else:
                oracle_alignments[(subset_num, alignment_target)] = oracle_alignment

    if HIT_TA1_SERVER:
        req_session.close()

    print(f"Got {error_count} errors calculating oracle alignment")
    return oracle_alignments

"""
Add oracle alignment to RQ2:
  Read probe sets from csv
  Get list of relevant alignment targets
  Calculate oracle alignments (via TA1 server)
  Update relevant synthetic ADMs with oracle alignment
"""
def main(mongo_db):
    print('\nReading probe sets from csv...')
    probe_sets: list = read_probe_sets()
    adm_collection = mongo_db['admTargetRuns']

    print("\nGetting list of alignment targets...")
    alignment_targets = get_alignment_targets(adm_collection)
    print("\nCalculating oracle alignments:")
    oracle_alignments = get_oracle_alignments(probe_sets, alignment_targets)
    if VERBOSE:
        print("--> Oracle alignments:")
        print(oracle_alignments)

    print(f"\nUpdating synthetic ADM runs with oracle alignment.")
    update_synthetic_adm_runs(adm_collection, oracle_alignments)
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
