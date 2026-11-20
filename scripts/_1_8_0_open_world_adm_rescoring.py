import argparse
import random
import requests
from math import isnan
from pymongo import MongoClient
from decouple import config 
from typing import Tuple
from old_probe_matchers.ow_pt3_probe_matcher_rerun import main as ow_pt3_probe_matcher_rerun

"""
This script recalculates TA1/ADEPT session alignment results for all Open World ADM runs against the midpoint
alignment targets, then writes the recalculated result object (including KDMAs) back to admTargetRuns.results.
Note that it first re-runs the probe matcher on OW Part 3 runs (which deletes unwanted Mistral runs in the process).

This script was adapted from _1_2_4_feb_2026_rq2.py, which contained some of the necessary building blocks / logic.

Usage: _1_8_0_open_world_adm_rescoring.py [-h] [-k] [-n] [-v]

Recalculates midpoint-based Open World ADM runs and updates database.

Options:
  -h, --help       Show this help message and exit
  -k, --no_kdmas   Do not re-calculate KDMAs
  -n, --no_output  Do not write to the MongoDB
  -v, --verbose    Verbose logging
"""

# These are constants that cannot be overridden via the command line
EVALUATION_NAME = 'Open World Experiment'
ADEPT_URL = config("ADEPT_URL")
HIT_TA1_SERVER = True # Useful for testing or if you can't reach the TA1 server
FAIL_FAST = False # Exit program if there's an error getting session alignment

# These are default values that can be overridden via the command line
KDMAS = True
VERBOSE = False
WRITE_TO_DB = True

#ORPHAN_ADM = {'old_name': 'OLD', 'new_name': 'NEW'}
ORPHAN_ADM = None


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
    Respond to the probes based on the ADM's responses
    Calculate session alignment at the specified target
"""
def get_ta1_calculations(req_session, probes: list, adm_name: str, scenario_id: str, target: str) -> Tuple[str, float, list, str]:
    session_id = None
    if HIT_TA1_SERVER:
        try:
            session_id = req_session.post(f'{ADEPT_URL}/api/v1/new_session').text.replace('"', '').strip()
            send_probes(req_session, f'{ADEPT_URL}/api/v1/response', session_id, probes, scenario_id)
            session_alignment = req_session.get(f'{ADEPT_URL}/api/v1/alignment/session_midpoint?session_id={session_id}&target_id={target}&population=false').json()
            kdmas = req_session.get(f'{ADEPT_URL}api/v1/computed_kdma_profile_midpoint?session_id={session_id}').json() if KDMAS else []
            return session_id, session_alignment['score'], kdmas, session_alignment.get('alignment_warning')
        except Exception as ex:
            return session_id, None, None, None
    else:
        return 'random_ta1_id', random.random(), \
            [{'kdma': 'affiliation', 'value': random.random()}, {'kdma': 'merit', 'value': random.random()}] if KDMAS else [], None


def update_adm_runs(adm_collection): 
    query: dict = {'evalName': {"$regex": EVALUATION_NAME}, 'alignment_target': {"$regex": 'ADEPT-June2025-'}}
    adm_runs = list(adm_collection.find(query))
    num_adms = len(adm_runs)
    print(f"Retrieved {num_adms} matching docs from database.")
    print(f"Updating {EVALUATION_NAME} ADM runs...")
    adm_num = 0
    error_count = 0
    increase_count = 0
    decrease_count = 0
    same_count = 0
    nan_count = 0
    update_count = 0
    total_aligned_delta = 0
    aligned_increase_count = 0
    aligned_decrease_count = 0
    req_session = None
    warning_sent = False

    if HIT_TA1_SERVER:
        req_session = requests.Session()

    for adm_run in adm_runs:
        adm_num += 1
        if (adm_num % 100) == 0:
            print(f"Processing ADM #{adm_num}/{num_adms}.")
        scenario_id = adm_run['scenario']
        adm_name = adm_run['adm_name']
        target = adm_run['alignment_target']
        probes = []
        for h in adm_run['history']:
            if h['command'] == 'Respond to TA1 Probe':
                probes.append({'probe_id': h['parameters']['probe_id'], 'choice': h['parameters']['choice']})
        ta1_id, alignment_score, kdmas, warning = \
            get_ta1_calculations(req_session, probes, adm_name, scenario_id, target)
        docid = adm_run['_id']
        results = adm_run['results']
        old_score = results['alignment_score']
        old_kdmas = results['kdmas']
        is_mistral = 'Mistral' in adm_name
        if VERBOSE:
            print(f"  ADM {adm_name}, scenario {scenario_id}, target {target}, probes {probes}")
            print(f"  {docid}: Got alignment score of {alignment_score} with old score of {old_score}.")
            print(f"           Got kdmas of {kdmas}, with old kdmas of {old_kdmas}.")

        if alignment_score is None:
            print(f"--> Error: could not get alignment and/or kdmas for {adm_name} in scenario {scenario_id} at target {target}.")
            if FAIL_FAST:
                print("Aborting.")
                exit(1)
            error_count += 1
        elif isnan(alignment_score):
            nan_count += 1
        elif old_score == alignment_score:
            same_count += 1
        else:
            if HIT_TA1_SERVER and not VERBOSE:
                print(f"  {docid}: Got alignment score of {alignment_score} with old score of {old_score}.")
            is_aligned = is_mistral and 'Outlines' not in adm_name

            if is_aligned:
                total_aligned_delta += alignment_score - old_score
            if old_score < alignment_score:
                increase_count += 1
                aligned_increase_count += is_aligned
            else:
                decrease_count += 1
                aligned_decrease_count += is_aligned

        results['ta1_session_id'] = ta1_id
        results['alignment_score'] = alignment_score
        results['kdmas'] = kdmas
        results['alignment_warning'] = warning
        if WRITE_TO_DB:
            if not HIT_TA1_SERVER:
                if not warning_sent:
                    print("Refusing to write test data to database!")
                    warning_sent = True
                continue
            result = adm_collection.update_one({'_id': docid}, {'$set': {'new_results': results, 'hidden': not is_mistral}})
            if result.modified_count:
                update_count += 1
            else:
                print(f"  Error updating {docid}")
        else:
            update_count += 1

    if HIT_TA1_SERVER:
        req_session.close()

    print("Summary:")
    print(f"  Increased scores: {increase_count}")
    print(f"    Increased Mistral aligned ADM scores: {aligned_increase_count}")
    print(f"  Decreased scores: {decrease_count}")
    print(f"    Decreased Mistral aligned scores: {aligned_decrease_count}")
    print(f"  Same scores: {same_count}")
    print(f"  NaN scores: {nan_count}")
    print(f"  Net Average Mistral aligned delta: {(total_aligned_delta / (increase_count + decrease_count)):.4f} (doesn't include unchanged scores)")
    print(f"{update_count} ADM runs {'' if WRITE_TO_DB else 'NOT '}updated in database.")
    print(f"Finished with a total of {error_count} error(s).  See logs for affected ADM runs.")


def main(mongo_db):
    adm_collection = mongo_db['admTargetRuns']
    if WRITE_TO_DB:
        if VERBOSE:
            print('Re-running OW Part 3 probe matcher, which deletes unwanted Mistral ADMs.')
        ow_pt3_probe_matcher_rerun(mongo_db)
        if ORPHAN_ADM:
            adm_collection.update_one(
                    {'adm_name': ORPHAN_ADM['old_name']},
                    {'$set': {
                        'adm_name': ORPHAN_ADM['new_name'],
                        'evaluation.adm_name': ORPHAN_ADM['new_name']
                    }}
                )

    update_adm_runs(adm_collection)
    print('\nDone.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Recalculates midpoint-based Open World ADM runs and updates database.')
    parser.add_argument('-k', '--no_kdmas', action='store_true', required=False, default=False,
                        help='Do not re-calculate KDMAs')
    parser.add_argument('-n', '--no_output', action='store_true', required=False, default=False,
                        help='Do not write to the MongoDB')
    parser.add_argument('-v', '--verbose', action='store_true', required=False, default=False,
                        help='Verbose logging')

    args = parser.parse_args()
    if args.no_kdmas:
        KDMAS = False
    if args.verbose:
        VERBOSE = True
    if args.no_output:
        WRITE_TO_DB = False

    client = MongoClient(config('MONGO_URL'))
    main(client.dashboard)
