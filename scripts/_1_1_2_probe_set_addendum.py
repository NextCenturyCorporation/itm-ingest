import argparse
import random
import requests
from pymongo import MongoClient
from decouple import config 
from dataclasses import dataclass
from typing import Tuple

"""
This scripts adds the July assessment subsets to the probe set experiment (Eval 14) with their same original set names,
but using Kitware's latest ADM runs.  It Calculates all the session KDMAs and alignment scores as per Eval 14.

It was adapted from _1_1_0_adaptive_experiment.py.
"""


# These are constants that cannot be overridden via the command line
EVALUATION_TYPE = 'July2025'
EVALUATION_NAME = 'Phase 2 Adaptive Experiment'
EVAL_NUM = 14
DOMAIN = 'p2triage'
TA1_NAME = 'adept'
ADEPT_URL = config("ADEPT_URL")
NUM_SUBSETS = 3
HIT_TA1_SERVER = True # Useful for testing or if you can't reach the TA1 server

# These are default values that can be overridden via the command line
VERBOSE = False
WRITE_TO_DB = True
IGNORED_LIST = []

# The July assessment subsets
july_assessment_sets: dict = {
    'AF1': ['101',  '29', '18', '15',   '9',   '5'],
    'AF2': ['106',  '36', '34', '21',  '39',   '6'],
    'AF3': ['107', '113', '48', '31',  '40', '111'],
    'MF1': ['101',  '41', '21', '27',  '56',   '1'],
    'MF2': ['102',  '43', '22', '30', '107', '109'],
    'MF3': ['103',  '44', '61', '68', '108', '110'],
    'PS1': [ '14',   '1',  '7',  '8',   '4',   '3'],
    'PS2': [ '13',  '16', '17', '22',   '5',   '9'],
    'PS3': [ '19',  '20', '24', '23',  '21',  '11'],
    'SS1': [  '2',   '6', '13', '15',  '33',  '42'],
    'SS2': [  '4',  '14', '26', '21',  '39',  '45'],
    'SS3': [ '11',  '16', '38', '41',  '43',  '51']
    }

kdmas_info: list[dict] = [
    {'acronym': 'AF', 'full_name': 'Affiliation Focus'},
    {'acronym': 'MF', 'full_name': 'Merit Focus'},
    {'acronym': 'PS', 'full_name': 'Personal Safety Focus'},
    {'acronym': 'SS', 'full_name': 'Search vs Stay'}
    ]

# Maps a kdma to a list of Adm_data for that attribute
# Each entry in the list contains the probe responses for an ADM run (one per target, each of baseline and aligned)
all_adm_data: dict = {}
# e.g., {'AF': [{'adm_name': 'baseline', 'alignment_target_id': 'ADEPT-July2025-affiliation-0.3', 'scenario_id': 'July2025-AFr12-eval',
#                'probe_responses': {'Probe 1': "Response 1-A", ... }], ...}


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
  Create synthetic ADM run for all assessment (observation) sets:
  for each kdma
    for as many assessment subsets as there are (per kdma)
        select the set of probes (probe_ids) based on the kdma and the subset number
        foreach adm_data[acronym] (n=22)
            Get alignment and kdmas from TA1 based on ADM choices to the selected set of probes
            create synthetic scenario id and name, e.g. "July2025-AF2-eval" and "Affiliation Focus Set 2"
            create synthetic row in admTargetRuns populating it with content from adm_data[target], calculated session alignment, kdmas, and scenario id/name
"""
def create_synthetic_adm_runs(mongo_db):
    adm_collection = mongo_db['admTargetRuns']
    total_synthetic_adm_runs = 0
    for kdma_info in kdmas_info:
        acronym = kdma_info['acronym']
        if acronym in IGNORED_LIST:
            continue

        total_kdma_synthetic_adm_runs = 0
        for subset_num in range(1, NUM_SUBSETS + 1):
            probe_set: list = [f'Probe {probe_id_num}' for probe_id_num in july_assessment_sets[f"{acronym}{subset_num}"]]
            set_construction = f'P2July Observation Set {subset_num}'
            if VERBOSE:
                print(f"Assessment subset {acronym}{subset_num}: {probe_set}")

            for adm_data in all_adm_data[acronym]:
                ta1_id, alignment_score, kdmas = get_ta1_calculations(adm_data, probe_set)
                synth_scenario_id = f"{EVALUATION_TYPE}-{acronym}{subset_num}-eval" # e.g., "July2025-AF2-eval"
                synth_scenario_name = f"{kdma_info['full_name']} Set {subset_num}" # e.g., "Search vs Stay Set 2"
                probeset_responses: list = [{probe_id: adm_data.probe_responses[probe_id]} for probe_id in adm_data.probe_responses if probe_id in probe_set]
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
                                            'probe_ids': probe_set, 'probe_responses': probeset_responses, 'alignment_target': adm_data.alignment_target_id}
                total_kdma_synthetic_adm_runs += 1

                if (WRITE_TO_DB):
                    adm_collection.insert_one(synthethic_adm_run)

        print(f"{total_kdma_synthetic_adm_runs} synthetic {acronym} ADM runs {'NOT ' if not WRITE_TO_DB else ''}uploaded to database.")
        total_synthetic_adm_runs += total_kdma_synthetic_adm_runs

    print(f"{total_synthetic_adm_runs} synthetic ADM runs {'NOT ' if not WRITE_TO_DB else ''}uploaded to database.")


def main(mongo_db):
    print('Getting ADM data from full run...')
    load_adm_data(mongo_db)

    # Clear out any previous run
    if WRITE_TO_DB:
        mongo_db['admTargetRuns'].delete_many({'evalNumber': EVAL_NUM, 'synthetic': True,
                                               "evaluation.set_construction" : {"$regex" : "Observation"}})

    print(f"\nCreating synthetic ADM runs for P2July Observation Sets...")
    create_synthetic_adm_runs(mongo_db)
    print('\nDone.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generates ADM results for synthetically created random assessment subsets.')
    parser.add_argument('-v', '--verbose', action='store_true', required=False, default=False,
                        help='Verbose logging')
    parser.add_argument('-n', '--no_output', action='store_true', required=False, default=False,
                        help='Do not write to the MongoDB')
    parser.add_argument('-i', '--ignore', nargs='+', metavar='ignore', required=False, type=str,
                        help="Acronyms of attributes to ignore (AF, MF, PS, SS)")

    args = parser.parse_args()
    if args.verbose:
        VERBOSE = True
    if args.no_output:
        WRITE_TO_DB = False
    if args.ignore:
        IGNORED_LIST = args.ignore

    client = MongoClient(config('MONGO_URL'))
    main(client.dashboard)
