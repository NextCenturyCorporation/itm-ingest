import csv
import argparse
import os
import re
import random
import requests
from pymongo import MongoClient
from decouple import config 
from dataclasses import dataclass
from typing import Tuple

# These are constants that cannot be overridden via the command line
EVALUATION_TYPE = 'July2025'
EVALUATION_NAME = 'Phase 2 4D Experiment'
EVAL_NUM = 11
DOMAIN = 'p2triage'
TA1_NAME = 'adept'
ADEPT_URL = config("ADEPT_URL")

# These are default values that can be overridden via the command line
VERBOSE = False
SEND_TO_MONGO = True
NUM_SUBSETS = 30
IGNORED_LIST = []

# Maps a kdma to its bin ranges, as provided by TA1
all_bin_ranges: dict = {
    'AF':    [0,  0.2, 0.35, 0.5, 0.65,  0.8, 1],
    'MF':    [0,  0.2, 0.35, 0.5, 0.65,  0.8, 1],
    'SS':    [0,  0.2, 0.35, 0.5,  0.6, 0.75, 1],
    'PS':    [0, 0.26,  0.4, 0.5, 0.66, 0.75, 1]
}

kdmas_info: list[dict] = [
    {'acronym': 'MF', 'full_name': 'Merit Focus', 'filename': f'{EVALUATION_TYPE}MeritFocus'},
    {'acronym': 'AF', 'full_name': 'Affiliation Focus', 'filename': f'{EVALUATION_TYPE}AffiliationFocus'},
    {'acronym': 'SS', 'full_name': 'Search vs Stay', 'filename': f'{EVALUATION_TYPE}SearchStay'},
    {'acronym': 'PS', 'full_name': 'Personal Safety Focus', 'filename': f'{EVALUATION_TYPE}PersonalSafety'}
    ]

expected_fields = ['scenario_id', 'scenario_name', 'probe_id', 'intro_text', 'probe_full_text', 'probe_question',
                   'patient_a_text', 'patient_b_text', 'pa_medical', 'pb_medical', 'pa_affiliation', 'pa_merit',
                   'pa_search', 'pa_personal_safety', 'pb_affiliation', 'pb_merit', 'pb_search', 'pb_personal_safety',
                   'choice1_text', 'choice2_text', 'probe_midpoint']

# Maps a kdma to a map of bin numbers to a list of probe IDs in that bin.
# A bin number is an int from 0 to the number of ranges-1.  This list is generated from all_bin_ranges and the csv file from TA1.
all_probe_bins: dict = {}
# e.g., { 'AF': {'AF0': ['Probe 1', 'Probe 5', 'Probe 25', 'Probe 29'], 'AF1': ['Probe 8', 'Probe 17', 'Probe 32', 'Probe 44']}}

# Maps a kdma to a list of Adm_data for that attribute
# Each entry in the list contains the probe responses for an ADM run (one per target, each of baseline and aligned)
all_adm_data: dict = {}
# e.g., {'AF': [{'name': 'baseline', 'text_session_id': '80585bba-ca11-46a0-b385-fd94ef8a7c19', 'probe_responses': {'Probe 1': "Response 1-A", ... }], ...}


@dataclass
class Adm_data:
    adm_name: str
    text_session_id: str
    human_kdmas: list
    scenario_id: str
    probe_responses: dict


# Get TA1 session ID from text survey with the target kdma values of the specified ADM run
def get_text_session_id(mongo_db, adm_entry):
    # First, get the KDMA values from the ADM's alignment target-- which originally comes from the human taking the text survey.
    target_text_kdmas: dict = {}
    for history_entry in adm_entry["history"]:
        if history_entry["command"] == "Alignment Target":
            #print(f"Found alignment target.")
            #raw_text_kdma_values = history_entry['response']['kdma_values']
            for kdma in history_entry['response']['kdma_values']:
                target_text_kdmas[kdma['kdma']] = kdma['value']
            break

    # Make sure we found it; otherwise something's badly wrong.
    if len(target_text_kdmas) == 0:
        print(f"Error: No KDMAs for {adm_entry['adm_name']} for scenario {adm_entry['scenario']} at target id {adm_entry['alignment_target']}.")
        exit(1)

    # Look up these KDMAs in the text scenario results to find its TA1 session ID
    text_scenarios = mongo_db['userScenarioResults']
    relevant_text_scenarios = text_scenarios.find({'evalNumber': 9}) # July

    for text_entry in relevant_text_scenarios:
        munged_scenario_id = re.sub(r'\d+-eval$', '-eval', text_entry.get('scenario_id')) # Remove subset from text scenario id
        if munged_scenario_id != adm_entry['scenario']:
            continue # Wrong scenario
        entry_kdmas = text_entry.get('kdmas')
        if not entry_kdmas:
            continue # No KDMAs for some reason

        def get_kdma_att(kdmas: list, att):
            '''
            Returns the kdma value for the requested attribute
            '''
            for kdma_obj in kdmas:
                if kdma_obj['kdma'] == att:
                    return kdma_obj['value']

        found = True
        # Look for the target kdmas
        for target_kdma_name in target_text_kdmas.keys():
            if target_text_kdmas[target_kdma_name] != get_kdma_att(text_entry['kdmas'], target_kdma_name):
                found = False # One of the kdmas didn't match, so this isn't the entry we're looking for
        if found: # Found the full set of matching KDMAs, so return the session ID
            return text_entry['combinedSessionId'], text_entry['kdmas']

    print(f"Warning: couldn't find KDMAs for ADM {adm_entry['adm_name']} with KDMAs {target_text_kdmas}.")
    return None


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
            text_session_id, human_kdmas = get_text_session_id(mongo_db, adm_run)
            adm_name = adm_run['evaluation']['adm_name']
            if 'Random' in adm_name:
                continue
            probe_responses = {}
            for h in adm_run['history']:
                if h['command'] == 'Respond to TA1 Probe':
                    probe_responses[h['parameters']['probe_id']] = h['parameters']['choice']
            adm_data = Adm_data(adm_name, text_session_id, human_kdmas, scenario_id, probe_responses)
            if VERBOSE:
                print(f"Adding {len(adm_data.probe_responses)} probe responses for {adm_data.adm_name} for text session {adm_data.text_session_id}")
            kdma_adm_data.append(adm_data)

        adm_cursor.close()
        all_adm_data[acronym] = kdma_adm_data
    print ("Stored all ADM data (probe responses)")


# Put probes in bins based on reading csvs
def populate_probe_bins():
    for kdma_info in kdmas_info:
        acronym: str = kdma_info['acronym']
        if acronym in IGNORED_LIST:
            continue

        full_name = kdma_info['full_name']
        filename = os.path.join('adept-csvs', EVALUATION_TYPE.lower(), f"{kdma_info['filename']}.csv")
        csvfile = open(filename, 'r', encoding='utf-8')
        reader: csv.DictReader = csv.DictReader(csvfile, fieldnames=expected_fields, restkey='junk')
        next(reader) # skip header
        bin_ranges = all_bin_ranges[acronym]
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
        all_probe_bins[acronym] = kdma_probe_map


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
    Create a ta1 session
    Respond to the random probes based on the adm_run's probe_responses
    Calculate session alignment against adm_data[target] and get kdma values
"""
def get_ta1_calculations(adm_data: Adm_data, probe_ids: list) -> Tuple[str, float, list]:
    session_id = requests.post(f'{ADEPT_URL}api/v1/new_session').text.replace('"', '').strip()
    probes = []
    for probe_id in probe_ids:
        probes.append({'probe_id': probe_id, 'choice': adm_data.probe_responses[probe_id]})
    send_probes(f'{ADEPT_URL}api/v1/response', session_id, probes, adm_data.scenario_id)
    comparison = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions?session_id_1={session_id}&session_id_2={adm_data.text_session_id}').json()
    kdmas = requests.get(f'{ADEPT_URL}api/v1/computed_kdma_profile?session_id={session_id}').json()
    return session_id, comparison['score'], kdmas


# Creating synthetic ADM runs based on random assessment probe subset
"""
  # Create synthetic ADM run for random assessment set
  clear out previous synthetic runs for this evaluation
  for each kdma
    for as many configurable subsets are desired
        select a random probe from each bin, or 1 from each bin per kdma if multi-attribute
        foreach adm_data[acronym] (n=22 or 8)
            Get alignment and kdmas from TA1 based on ADM choices to random probes
            create synthetic scenario id and name, e.g. "July2025-AFr23-eval" and "Affiliation Focus Random Set 23"
            create synthetic row in admTargetRuns populating it with content from adm_data[target], calculated session alignment, kdmas, and scenario id/name
"""
def create_synthetic_adm_runs(mongo_db):
    adm_collection = mongo_db['admTargetRuns']
    adm_collection.delete_many({'evalNumber': EVAL_NUM, 'synthetic': True})
    total_synthetic_adm_runs = 0
    for kdma_info in kdmas_info:
        acronym = kdma_info['acronym']
        if acronym in IGNORED_LIST:
            continue

        kdma_probe_map: dict = all_probe_bins[acronym]
        total_kdma_synthetic_adm_runs = 0

        for subset_num in range(1, NUM_SUBSETS + 1):
            random_probes: list = []
            for probe_ids in kdma_probe_map.values():
                random_probes.append(random.choice(probe_ids))
            if VERBOSE:
                print(f"Random probe subset #{subset_num}: {random_probes}")

            for adm_data in all_adm_data[acronym]:
                ta1_id, alignment_score, kdmas = get_ta1_calculations(adm_data, random_probes)
                synth_scenario_id = f"{EVALUATION_TYPE}-{acronym}r{subset_num}-eval" # e.g., "July2025-AFr23-eval"
                synth_scenario_name = f"{kdma_info['full_name']} Random Set {subset_num}" # e.g., "Search vs Stay Random Set 23"
                if VERBOSE:
                    print(f"  {synth_scenario_id}: Got alignment score of {alignment_score} and kdmas of {kdmas} for persisted session id {adm_data.text_session_id}")
                evaluation: dict = {'evalName': EVALUATION_NAME,
                                    'evalNumber': EVAL_NUM,
                                    'scenario_name': synth_scenario_name,
                                    'scenario_id': synth_scenario_id,
                                    'alignment_target_id': adm_data.text_session_id,
                                    'human_kdmas': adm_data.human_kdmas,
                                    'adm_name': adm_data.adm_name,
                                    'adm_profile': 'baseline' if 'baseline' in adm_data.adm_name.lower() else 'aligned',
                                    'domain': DOMAIN,
                                    'start_time': '-',
                                    'end_time': '-',
                                    'ta1_name': TA1_NAME,
                                    'ta3_session_id': 'N/A'}
                results: dict = {'ta1_session_id': ta1_id, 'alignment_score': alignment_score, 'kdmas': kdmas}
                synthethic_adm_run: dict = {'evaluation': evaluation, 'results': results, 'evalNumber': EVAL_NUM, 'scenario': synth_scenario_id,
                                            'evalName': EVALUATION_NAME, 'adm_name': adm_data.adm_name, 'synthetic': True,
                                            'probe_ids': random_probes, 'text_session_id': adm_data.text_session_id}
                total_kdma_synthetic_adm_runs += 1

                if (SEND_TO_MONGO):
                    adm_collection.insert_one(synthethic_adm_run)

        print(f"{total_kdma_synthetic_adm_runs} synthetic {acronym} ADM runs {'NOT ' if not SEND_TO_MONGO else ''}uploaded to database.")
        total_synthetic_adm_runs += total_kdma_synthetic_adm_runs

    print(f"{total_synthetic_adm_runs} synthetic ADM runs {'NOT ' if not SEND_TO_MONGO else ''}uploaded to database.")


def main(mongo_db):
    print('Getting ADM data from full run...')
    load_adm_data(mongo_db)
    print('\nPutting probes in bins based on TA1 csvs...')
    populate_probe_bins()
    print(f'\nCreating {NUM_SUBSETS} synthetic ADM runs based on random assessment probe subset...')
    create_synthetic_adm_runs(mongo_db)
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
        SEND_TO_MONGO = False
    if args.ignore:
        IGNORED_LIST = args.ignore

    client = MongoClient(config('MONGO_URL'))
    main(client.dashboard)
