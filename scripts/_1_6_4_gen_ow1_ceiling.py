import argparse
import random
import requests
from math import isnan
from pymongo import MongoClient
from decouple import config 
from scripts._1_2_4_feb_2026_rq2 import send_probes
import itertools
import pprint

"""
Calculate the "empirically calculated, globally optimal ceiling" for the Open World Part 1 probes.
This is the high-level algorithm:
1. Create a map of scenario ids to lists of probe ids in that scenario.
2. Collect the alignment score for every possible response set for each scenario at every target.
   2a. Get the subset of probe_ids that are relevant to the alignment target.
   2b. Generate the choices for each string.
   2c. Get every combination of those choices.
   2d. Pair each combination back to the original probe_ids.
   2e. For every combination of responses, calculate session alignment at every relevant alignment target.
3. Calculate and save the high score at each alignment target for each scenario.
4. Add the high score back into the admTargetRuns database.
"""

# These are constants that cannot be overridden via the command line
ADEPT_URL = config("ADEPT_URL")
HIT_TA1_SERVER = True # Useful for testing or if you can't reach the TA1 server

# These are default values that can be overridden via the command line
VERBOSE = False
WRITE_TO_DB = True


"""
    Calculate and return session alignment for the specified session at the specified alignment target.
"""
def get_alignment(req_session, session_id: str, alignment_target: str) -> float:
    if HIT_TA1_SERVER:
        try:
            session_alignment = req_session.get(f'{ADEPT_URL}api/v1/alignment/session?session_id={session_id}&target_id={alignment_target}').json()
            return session_alignment['score']
        except Exception:
            print(f"--> Error: could not get alignment for target {alignment_target}.")
            return None
    else:
        return random.uniform(0.0, 1.0)


def calc_alignments(data: dict, scenario_id: str, response_set: dict, target_ids: list) -> int:
    error_count = 0
    req_session = None
    session_id = None

    if HIT_TA1_SERVER:
        req_session = requests.Session()
        session_id = req_session.post(f'{ADEPT_URL}api/v1/new_session').text.replace('"', '').strip()
        probes = [{'probe_id': probe_id, 'choice': response_set[probe_id]} for probe_id in response_set]
        send_probes(req_session, f'{ADEPT_URL}api/v1/response', session_id, probes, scenario_id)

    # Calculate and save the session alignment for the specified response set at every target alignment.
    for target_id in target_ids:
        alignment_score = get_alignment(req_session, session_id, target_id)
        if not alignment_score or isnan(alignment_score):
            error_count += 1
            alignment_score = None
            print(f"  Got error calculating alignment for {scenario_id} at target {target_id} for responses {response_set}.")
        else:
            data[scenario_id][target_id].append(alignment_score)

    if HIT_TA1_SERVER:
        req_session.close()

    return error_count


def main(mongo_db):
    adm_collection = mongo_db['admTargetRuns']

    # 1. Create a map of scenario ids to lists of probe ids in that scenario.
    #    Note this will include both AF and MF probes, which will later be separated out.
    #    1a. Also determine the list of AF and MF alignment targets present in the data.
    adm_cursor = adm_collection.find({'evalName': {"$regex": "Open World Experiment Part 1"}, "alignment_target": {"$regex": "ADEPT-June2025"}})
    adm_runs = list(adm_cursor)
    print(f"Retrieved {len(adm_runs)} OW1 adm runs from database.")

    scenario_map: dict = {}
    af_alignment_targets = []
    mf_alignment_targets = []
    for adm_run in adm_runs:
        scenario_id = adm_run['scenario']
        target = adm_run['alignment_target']
        if scenario_id not in scenario_map:
            scenario_map[scenario_id] = adm_run['probe_ids']
        if 'affiliation' in target and target not in af_alignment_targets:
            af_alignment_targets.append(target)
        if 'merit' in target and target not in mf_alignment_targets:
            mf_alignment_targets.append(target)
    af_alignment_targets.sort()
    mf_alignment_targets.sort()

    # 2. Collect the alignment score for every possible response set for each scenario at every target.
    #    e.g., {'June2025-OW_desert': {'ADEPT-June2025-affiliation-0.0': [0.25, 0.52, 0.33], 'ADEPT-June2025-affiliation-0.2': [0.52, 0.77]}, ... }
    data = {
        scenario_id: {target: [] for target in af_alignment_targets + mf_alignment_targets}
        for scenario_id in scenario_map
    }
    error_count = 0
    print("\nCalculating alignments...")
    for scenario_id in scenario_map:
        for kdma in ['AF', 'MF']:
            # 2a. Get the subset of probe_ids that are relevant to the alignment target.
            probe_ids = [probe_id for probe_id in scenario_map[scenario_id] if kdma in probe_id]
            if VERBOSE:
                print(f"--> Probe IDs for {scenario_id} {kdma} targets:")
                pprint.pprint(probe_ids)

            # 2b. Generate the choices for each string.
            all_choices: list = [(f"Response {probe_id.split()[-1]}-A", f"Response {probe_id.split()[-1]}-B") for probe_id in probe_ids]

            # 2c. Get every combination of those choices.
            all_combinations: list = itertools.product(*all_choices)

            # 2d. Pair each combination back to the original probe_ids.
            response_sets: dict = [dict(zip(probe_ids, combo)) for combo in all_combinations]

            if VERBOSE:
                print("--> Response Sets:")
                pprint.pprint(response_sets)

            # 2e. For every combination of responses, calculate session alignment at every relevant alignment target.
            for response_set in response_sets:
                error_count += calc_alignments(data, scenario_id, response_set,
                                               af_alignment_targets if kdma == 'AF' else mf_alignment_targets)

    print(f"--> Total error count: {error_count}.\n")

    # 3. Calculate and save the high score at each alignment target for each scenario.
    for scenario_id in data:
        for target in data[scenario_id]:
            data[scenario_id][target] = max(data[scenario_id][target])

    if VERBOSE:
        pprint.pprint(data)

    adm_collection.update_many({}, {"$unset": {"ceiling alignment": ""}})

    # 4. Add the high score back into the admTargetRuns database.
    print(f"Adding ceiling alignment to {len(adm_runs)} documents:")
    for adm_run in adm_runs:
        scenario_id = adm_run['scenario']
        target_id = adm_run['alignment_target']
        highscore = data.get(scenario_id, {}).get(target_id, 0)
        if WRITE_TO_DB:
            adm_collection.update_one({"_id": adm_run["_id"]}, {"$set": {"ceiling_alignment": highscore}})

        print(f"  {scenario_id} at {target_id}: {'NOT ' if not WRITE_TO_DB else ''} setting highscore to {highscore}.")

    print('\nDone.')


"""
   Calculate the "empirically calculated, globally optimal ceiling" for the Open World Part 1 probes.
"""
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generates synthetic ADM results for random RQ2 probe subsets.')
    parser.add_argument('-n', '--no_output', action='store_true', required=False, default=False,
                        help='Do not write to the MongoDB')
    parser.add_argument('-v', '--verbose', action='store_true', required=False, default=False,
                        help='Verbose logging')

    args = parser.parse_args()
    if args.verbose:
        VERBOSE = True
    if args.no_output:
        WRITE_TO_DB = False

    client = MongoClient(config('MONGO_URL'))
    main(client.dashboard)
