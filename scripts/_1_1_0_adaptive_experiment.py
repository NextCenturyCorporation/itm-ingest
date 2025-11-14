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
The purpose of this experiment is to see if certain probe set constructions yield higher alignment scores overall
(because one of the limiting factors is just the ability of a set of probes to represent the "true" KDMA of a respondent
based on the fact that we are setting targets based on 1/10 intervals but the sets don't necessarily (mathematically)
allow you to get a KDMA exactly at 1/10 of a whole number). This is less a test of the ADM alignment capability and
more a test of how best to construct probe sets to get the information we need, using ADMs we already know to align really well.

We need to create new probe sets to generate alignment scores. The probe sets need to be constructed according to one
of the following conditions:
- "6probe":  6 probes, 1 per current bin
- "10probe":  10 probes, 1 per current extreme bin, 2 per current middle bins
  - For bins named 0-5, the probes are taken from 0, 1, 1, 2, 2, 3, 3, 4, 4, 5 = 10 probes
- "8probe":  8 probes, 1 per current upper and lower bins, 2 per current middle bins
  - For bins named 0-5, the probes are taken from 0, 1, 2, 2, 3, 3, 4, 5 = 8 probes
- "Adapt6":  Adaptive1: 6 probes, 4 from new 4 bins, 2 adaptive
- "Adapt8":  Adaptive2: 8 probes, 6 from current bins, 2 adaptive
- "New6":  6 probes, 1 per new upper and lower new 4 bins, 2 per new middle bins
  - For new bins named 0-3, the probes are taken from 0, 1, 1, 2, 2, 3 = 6 probes

For each of those conditions, we need 25 sets constructed per target (as opposed to 100 in July).
The first condition is the same as the July RQ2 selection criteria.
The next two use the same bins as July RQ2 but more probes and different selection.
The adaptive conditions will vary based on previous choices.  TBD how to handle this.
The "new 4 bins" have cut points at 0.3, 0.5, and 0.7. They are used for one of the adaptive conditions
and the last static condition.
"""


# These are constants that cannot be overridden via the command line
EVALUATION_TYPE = 'July2025'
EVALUATION_NAME = 'Phase 2 Adaptive Experiment'
EVAL_NUM = 14
DOMAIN = 'p2triage'
TA1_NAME = 'adept'
ADEPT_URL = config("ADEPT_URL")
HIT_TA1_SERVER = True # Useful for testing or if you can't reach the TA1 server

# These are default values that can be overridden via the command line
VERBOSE = False
WRITE_TO_DB = True
NUM_SUBSETS = 25
IGNORED_LIST = []

# Maps a kdma to its bin ranges, as provided by TA1 in July
july_bin_ranges: dict = {
    'AF':    [0,  0.2, 0.35, 0.5, 0.65,  0.8, 1],
    'MF':    [0,  0.2, 0.35, 0.5, 0.65,  0.8, 1],
    'PS':    [0, 0.26,  0.4, 0.5, 0.66, 0.75, 1],
    'SS':    [0,  0.2, 0.35, 0.5,  0.6, 0.75, 1]
}

# Right now all ranges are the same, but that could change
new_bin_ranges: dict = {
    'AF':    [0,  0.3, 0.5, 0.7, 1],
    'MF':    [0,  0.3, 0.5, 0.7, 1],
    'PS':    [0,  0.3, 0.5, 0.7, 1],
    'SS':    [0,  0.3, 0.5, 0.7, 1]
}

kdmas_info: list[dict] = [
    {'acronym': 'AF', 'full_name': 'Affiliation Focus', 'filename': f'{EVALUATION_TYPE}AffiliationFocus'},
    {'acronym': 'MF', 'full_name': 'Merit Focus', 'filename': f'{EVALUATION_TYPE}MeritFocus'},
    {'acronym': 'PS', 'full_name': 'Personal Safety Focus', 'filename': f'{EVALUATION_TYPE}PersonalSafety'},
    {'acronym': 'SS', 'full_name': 'Search vs Stay', 'filename': f'{EVALUATION_TYPE}SearchStay'}
    ]

expected_fields = ['scenario_id', 'scenario_name', 'probe_id', 'intro_text', 'probe_full_text', 'probe_question',
                   'patient_a_text', 'patient_b_text', 'pa_medical', 'pb_medical', 'pa_affiliation', 'pa_merit',
                   'pa_search', 'pa_personal_safety', 'pb_affiliation', 'pb_merit', 'pb_search', 'pb_personal_safety',
                   'choice1_text', 'choice2_text', 'probe_midpoint']

# Maps a kdma to a map of bin numbers to a list of probe IDs in that bin.
# A bin number is an int from 0 to the number of ranges-1.  This list is generated from all_bin_ranges and the csv file from TA1.
july_probe_bins: dict = {}
new_probe_bins: dict = {}
# e.g., { 'AF': {'AF0': ['Probe 1', 'Probe 5', 'Probe 25', 'Probe 29'], 'AF1': ['Probe 8', 'Probe 17', 'Probe 32', 'Probe 44']}}

# Maps a kdma to a list of Adm_data for that attribute
# Each entry in the list contains the probe responses for an ADM run (one per target, each of baseline and aligned)
all_adm_data: dict = {}
# e.g., {'AF': [{'name': 'baseline', 'alignment_target_id': 'ADEPT-July2025-affiliation-0.3', 'probe_responses': {'Probe 1': "Response 1-A", ... }], ...}


@dataclass
class Adm_data:
    adm_name: str
    alignment_target_id: str
    scenario_id: str
    probe_responses: dict


# Get ADM data from full run and store probe responses locally
def load_adm_data(mongo_db):
    adm_collection = mongo_db['admTargetRuns']
    for kdma_info in kdmas_info:
        acronym = kdma_info['acronym']
        if acronym in IGNORED_LIST:
            continue

        scenario_id = f"{EVALUATION_TYPE}-{acronym}-eval"
        adm_cursor = adm_collection.find({'evalNumber': EVAL_NUM, 'scenario': scenario_id})
        adm_runs = list(adm_cursor)
        print(f"Retrieved {len(adm_runs)} adm {acronym} runs from database.")

        # A list of all probe responses for all adm runs for this attribute (one per target/adm type combination)
        kdma_adm_data: list = [] 
        for adm_run in adm_runs:
            alignment_target_id = adm_run['evaluation']['alignment_target_id']
            adm_name = adm_run['evaluation']['adm_name']
            if 'Random' in adm_name:
                continue
            probe_responses = {}
            for h in adm_run['history']:
                if h['command'] == 'Respond to TA1 Probe':
                    probe_responses[h['parameters']['probe_id']] = h['parameters']['choice']
            adm_data = Adm_data(adm_name, alignment_target_id, scenario_id, probe_responses)
            if VERBOSE:
                print(f"Adding {len(adm_data.probe_responses)} probe responses for {adm_data.adm_name} at alignment {adm_data.alignment_target_id}")
            kdma_adm_data.append(adm_data)

        adm_cursor.close()
        all_adm_data[acronym] = kdma_adm_data
    print ("Stored all ADM data (probe responses)")


# Put probes in bins based on reading csvs
def populate_probe_bins(ranges: dict, output_bin: dict):
    for kdma_info in kdmas_info:
        acronym: str = kdma_info['acronym']
        if acronym in IGNORED_LIST:
            continue

        full_name = kdma_info['full_name']
        filename = os.path.join('adept-csvs', EVALUATION_TYPE.lower(), f"{kdma_info['filename']}.csv")
        csvfile = open(filename, 'r', encoding='utf-8')
        reader: csv.DictReader = csv.DictReader(csvfile, fieldnames=expected_fields, restkey='junk')
        next(reader) # skip header
        bin_ranges = ranges[acronym]
        num_ranges = len(bin_ranges) - 1
        kdma_probe_map: dict = {} # maps a bin number to the list of probe IDs in that bin
        kdmas: list = acronym.split('-')
        for kdma in kdmas: # initialize all bins
            for bin_num in range(num_ranges):
                kdma_probe_map[f"{kdma}{bin_num}"] = []

        # Process the csv file
        print(f"\nProcessing {full_name} ({acronym}) from {filename}.")
        for line in reader:
            if not line or not line['scenario_id'] or 'train' in line['scenario_id']:
                continue
            probe_id = line['probe_id']
            midpoint: float = float(line['probe_midpoint'])

            """
            Find probe_id's bin:  "For random selection from bin ranges, please use X >= low end, X < high end
            (except at the very top, you can use <= 1.0), so that the entire possible span of 0-1 is covered."
            Each pass through this for loop fills the next bin with all probes in that bin.
            """
            for kdma in kdmas:
                if len(kdmas) > 1 and f"-{kdma}-" not in probe_id:
                    continue # Don't put 2d probes in bins for both kdmas
                for this_index in range(num_ranges):
                    next_index = this_index + 1
                    if (midpoint >= bin_ranges[this_index]) and \
                        (midpoint < bin_ranges[next_index] if this_index < num_ranges - 1 else \
                        midpoint <= bin_ranges[next_index]):
                        if VERBOSE:
                            print(f"Adding {probe_id} to bin {kdma}{this_index} because its midpoint was {midpoint}.")
                        kdma_probe_map[f"{kdma}{this_index}"].append(probe_id) # Add the probe to the correct bin

        csvfile.close()
        for bin, map in kdma_probe_map.items():
            print(f"  Added {len(map)} probes to bin {bin}.")
        if VERBOSE:
            print(f"\nFull probe map for {acronym}:")
            for bin, map in kdma_probe_map.items():
                print(f"  {bin}: {map}")

        # Add to the full list of probe bins mapped to the kdma
        output_bin[acronym] = kdma_probe_map


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
def get_ta1_calculations(adm_data: Adm_data, probe_ids: list) -> Tuple[str, float, list]:
    if HIT_TA1_SERVER:
        session_id = requests.post(f'{ADEPT_URL}api/v1/new_session').text.replace('"', '').strip()
        probes = []
        for probe_id in probe_ids:
            probes.append({'probe_id': probe_id, 'choice': adm_data.probe_responses[probe_id]})
        send_probes(f'{ADEPT_URL}api/v1/response', session_id, probes, adm_data.scenario_id)
        session_alignment = requests.get(f'{ADEPT_URL}api/v1/alignment/session?session_id={session_id}&target_id={adm_data.alignment_target_id}&population=false').json()
        kdmas = requests.get(f'{ADEPT_URL}api/v1/computed_kdma_profile?session_id={session_id}').json()
        return session_id, session_alignment['score'], kdmas
    else:
        return 'foobar', random.random(), \
            [{'kdma': 'affiliation', 'value': random.random()}, {'kdma': 'merit', 'value': random.random()},
             {'kdma': 'personal_safety', 'value': random.random()}, {'kdma': 'search', 'value': random.random()}
             ]


"""
  Create synthetic ADM run for random assessment set:
  clear out previous synthetic runs for this evaluation
  for each kdma
    for as many configurable subsets are desired
        select a set of probes (probe_ids) according to behavior encapsulated in the specified randomizer
        foreach adm_data[acronym] (n=22 or 8)
            Get alignment and kdmas from TA1 based on ADM choices to random probes
            create synthetic scenario id and name, e.g. "July2025-AFr23-eval" and "Affiliation Focus Random Set 23"
            create synthetic row in admTargetRuns populating it with content from adm_data[target], calculated session alignment, kdmas, and scenario id/name
"""
def create_synthetic_adm_runs(mongo_db, probe_bins: dict, randomizer, set_construction):
    adm_collection = mongo_db['admTargetRuns']
    total_synthetic_adm_runs = 0
    for kdma_info in kdmas_info:
        acronym = kdma_info['acronym']
        if acronym in IGNORED_LIST:
            continue

        kdma_probe_map: dict = probe_bins[acronym]
        total_kdma_synthetic_adm_runs = 0

        for subset_num in range(1, NUM_SUBSETS + 1):
            random_probes: list = randomizer(kdma_probe_map, acronym)
            if VERBOSE:
                print(f"Random probe subset #{subset_num}: {random_probes}")

            for adm_data in all_adm_data[acronym]:
                ta1_id, alignment_score, kdmas = get_ta1_calculations(adm_data, random_probes)
                synth_scenario_id = f"{EVALUATION_TYPE}-{acronym}r{subset_num}-eval" # e.g., "July2025-AFr23-eval"
                synth_scenario_name = f"{kdma_info['full_name']} Random Set {subset_num}" # e.g., "Search vs Stay Random Set 23"
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
                                            'probe_ids': random_probes, 'alignment_target': adm_data.alignment_target_id}
                total_kdma_synthetic_adm_runs += 1

                if (WRITE_TO_DB):
                    adm_collection.insert_one(synthethic_adm_run)

        print(f"{total_kdma_synthetic_adm_runs} synthetic {acronym} ADM runs {'NOT ' if not WRITE_TO_DB else ''}uploaded to database.")
        total_synthetic_adm_runs += total_kdma_synthetic_adm_runs

    print(f"{total_synthetic_adm_runs} synthetic ADM runs {'NOT ' if not WRITE_TO_DB else ''}uploaded to database.")

# "6probe":  6 probes, 1 per current bin
def randomizer_6probe(probe_map: dict, acronym: str) -> list:
    random_probes: list = []
    for probe_ids in probe_map.values():
        random_probes.append(random.choice(probe_ids))
    return random_probes

# "10probe":  10 probes, 1 per current extreme bin, 2 per current middle bins
#   For bins named 0-5, the probes are taken from 0, 1, 1, 2, 2, 3, 3, 4, 4, 5 = 10 probes
def randomizer_10probe(probe_map: dict, acronym: str) -> list:
    random_probes: list = []
    random_probes.append(random.choice(probe_map[f"{acronym}0"]))
    random_probes.append(random.choice(probe_map[f"{acronym}1"]))
    random_probes.append(random.choice(probe_map[f"{acronym}1"]))
    random_probes.append(random.choice(probe_map[f"{acronym}2"]))
    random_probes.append(random.choice(probe_map[f"{acronym}2"]))
    random_probes.append(random.choice(probe_map[f"{acronym}3"]))
    random_probes.append(random.choice(probe_map[f"{acronym}3"]))
    random_probes.append(random.choice(probe_map[f"{acronym}4"]))
    random_probes.append(random.choice(probe_map[f"{acronym}4"]))
    random_probes.append(random.choice(probe_map[f"{acronym}5"]))
    return random_probes

# "8probe":  8 probes, 1 per current upper and lower bins, 2 per current middle bins
#   For bins named 0-5, the probes are taken from 0, 1, 2, 2, 3, 3, 4, 5 = 8 probes
def randomizer_8probe(probe_map: dict, acronym: str) -> list:
    random_probes: list = []
    random_probes.append(random.choice(probe_map[f"{acronym}0"]))
    random_probes.append(random.choice(probe_map[f"{acronym}1"]))
    random_probes.append(random.choice(probe_map[f"{acronym}2"]))
    random_probes.append(random.choice(probe_map[f"{acronym}2"]))
    random_probes.append(random.choice(probe_map[f"{acronym}3"]))
    random_probes.append(random.choice(probe_map[f"{acronym}3"]))
    random_probes.append(random.choice(probe_map[f"{acronym}4"]))
    random_probes.append(random.choice(probe_map[f"{acronym}5"]))
    return random_probes

# "Adapt6":  Adaptive1: 6 probes, 4 from new 4 bins, 2 adaptive
def randomizer_Adapt6(probe_map: dict, acronym: str) -> list:
    random_probes: list = []
    for probe_ids in probe_map.values():
        random_probes.append(random.choice(probe_ids))

    # Insert adaptive probes here
    pass

    return random_probes

# "Adapt8":  Adaptive2: 8 probes, 6 from current bins, 2 adaptive
def randomizer_Adapt8(probe_map: dict, acronym: str) -> list:
    random_probes: list = randomizer_6probe(probe_map, acronym)
    # Insert adaptive probes here
    pass

    return random_probes

# "New6":  6 probes, 1 per new upper and lower new 4 bins, 2 per new middle bins
#   For new bins named 0-3, the probes are taken from 0, 1, 1, 2, 2, 3 = 6 probes
def randomizer_New6(probe_map: dict, acronym: str) -> list:
    random_probes: list = []
    random_probes.append(random.choice(probe_map[f"{acronym}0"]))
    random_probes.append(random.choice(probe_map[f"{acronym}1"]))
    random_probes.append(random.choice(probe_map[f"{acronym}1"]))
    random_probes.append(random.choice(probe_map[f"{acronym}2"]))
    random_probes.append(random.choice(probe_map[f"{acronym}2"]))
    random_probes.append(random.choice(probe_map[f"{acronym}3"]))
    return random_probes


def main(mongo_db):
    print('Getting ADM data from full run...')
    load_adm_data(mongo_db)
    print('\nPutting probes in July bins based on TA1 csvs...')
    populate_probe_bins(july_bin_ranges, july_probe_bins)
    print('\nPutting probes in new bins based on TA1 csvs...')
    populate_probe_bins(new_bin_ranges, new_probe_bins)

    # Clear out any previous run
    if WRITE_TO_DB:
        mongo_db['admTargetRuns'].delete_many({'evalNumber': EVAL_NUM, 'synthetic': True})

    print(f"\nCreating {NUM_SUBSETS} synthetic ADM runs based on '6probe' set construction...")
    create_synthetic_adm_runs(mongo_db, july_probe_bins, randomizer_6probe, '6probe')
    print(f"\nCreating {NUM_SUBSETS} synthetic ADM runs based on '10probe' set construction...")
    create_synthetic_adm_runs(mongo_db, july_probe_bins, randomizer_10probe, '10probe')
    print(f"\nCreating {NUM_SUBSETS} synthetic ADM runs based on '8probe' set construction...")
    create_synthetic_adm_runs(mongo_db, july_probe_bins, randomizer_8probe, '8probe')
    """
    print(f"\nCreating {NUM_SUBSETS} synthetic ADM runs based on 'Adapt6' set construction...")
    create_synthetic_adm_runs(mongo_db, new_probe_bins, randomizer_Adapt6, 'Adapt6')
    print(f"\nCreating {NUM_SUBSETS} synthetic ADM runs based on 'Adapt8' set construction...")
    create_synthetic_adm_runs(mongo_db, july_probe_bins, randomizer_Adapt8, 'Adapt8')
    """
    print(f"\nCreating {NUM_SUBSETS} synthetic ADM runs based on 'New6' set construction...")
    create_synthetic_adm_runs(mongo_db, new_probe_bins, randomizer_New6, 'New6')
    print('\nDone.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generates ADM results for synthetically created random assessment subsets.')
    parser.add_argument('-v', '--verbose', action='store_true', required=False, default=False,
                        help='Verbose logging')
    parser.add_argument('-n', '--no_output', action='store_true', required=False, default=False,
                        help='Do not write to the MongoDB')
    parser.add_argument('-c', '--count', metavar='count', required=False, type=int, default=NUM_SUBSETS,
                        help=f"How many scenarios to generate per KDMA  (default {NUM_SUBSETS})")
    parser.add_argument('-i', '--ignore', nargs='+', metavar='ignore', required=False, type=str,
                        help="Acronyms of attributes to ignore (AF, MF, PS, SS)")

    args = parser.parse_args()
    if args.count:
        NUM_SUBSETS = args.count
    if args.verbose:
        VERBOSE = True
    if args.no_output:
        WRITE_TO_DB = False
    if args.ignore:
        IGNORED_LIST = args.ignore

    client = MongoClient(config('MONGO_URL'))
    main(client.dashboard)
