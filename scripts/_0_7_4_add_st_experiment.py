import utils.soartech_utils as soartech_utils
from dataclasses import dataclass

"""
Add support for new experimental table for SoarTech scorecard alignment
For each vol scenario in the userScenarioResults collection (evalNumber 5-6), collect the probe responses, scenario id, and the pid.
Take the above pid and find the document in surveyResults that it maps to
- This is in results.pid if it exists, otherwise "results.Participant ID Page.questions.Participant ID.response".
Iterate through the keys until we find the objects with scenarioIndex containing "vol".
- There are four such objects, but we're ignoring the "comparison" pageType.
- The admName for these objects tell us the three VOL adms the participant saw.
Use the admName, admTarget, and scenarioIndex (which is the scenario name) to find the matching adm in admTargetRuns.
In admTargetRuns, collect the ADM responses by searching through history for "Respond to TA1 Probe" commands.
Use the new SoarTech endpoint to compare the probe response choices from the respective scenario for the ADM (target) to human/text based (aligner).
Store these three sets of alignment values (once for each seen ADM, four KDMAs per set) in the humanToADMComparison collection.

"""
UPDATE_DATABASE = True
VERBOSE_OUTPUT = False

@dataclass
class Pid_data:
    pid: str
    text_scenario_id: str
    text_probes: list
    adm_name: str = None
    adm_target: str = None
    adm_scenario_id: str = None

def collect_text_probe_responses(mongo_db):
    text_scenario_collection = mongo_db['userScenarioResults']
    phase1_text_results = text_scenario_collection.find({'evalNumber': {'$in': [5, 6]}})

    # For each vol scenario in the userScenarioResults collection (evalNumber 5-6), collect the probe responses, scenario id, and the pid.
    comparison_data = {} # maps a pid to a collection of data for that pid required to calculate all alignments
    for entry in phase1_text_results:
        text_scenario_id = entry.get('scenario_id')
        pid = entry.get('participantID')

        # Get SoarTech VOL probe responses
        if ('vol-ph1-eval' in text_scenario_id):
            text_probes = []
            for k in entry:
                if isinstance(entry[k], dict) and 'questions' in entry[k]:
                    if 'probe ' + k in entry[k]['questions'] and 'response' in entry[k]['questions']['probe ' + k] and 'question_mapping' in entry[k]['questions']['probe ' + k]:
                        response = entry[k]['questions']['probe ' + k]['response'].replace('.', '')
                        mapping = entry[k]['questions']['probe ' + k]['question_mapping']
                        if response in mapping:
                            text_probes.append({'probe': {'choice': mapping[response]['choice'], 'probe_id': mapping[response]['probe_id']}})
                        else:
                            print(f"Could not find response in mapping for pid {pid}!", response, list(mapping.keys()))
            comparison_data[pid] = Pid_data(pid, text_scenario_id, text_probes)
    print(f"Saved comparison data for {len(comparison_data)} pids.")
    return comparison_data


def main(mongo_db):
    comparison_data = collect_text_probe_responses(mongo_db)
    survey_results_collection = mongo_db['surveyResults']

    for pid in comparison_data.keys():
        if VERBOSE_OUTPUT:
            print()
        print(f"Processing PID '{pid}'.")
        # Take the above pid and find the documents in surveyResults that it maps to
        survey_results = survey_results_collection.find({'results.pid': pid})
        pid_data: Pid_data = comparison_data[pid]
        # Iterate through the keys in each result until we find the objects with scenarioIndex containing "vol"
        for survey_result in survey_results:
            for vol_obj in survey_result['results'].values():
                if not type(vol_obj) == dict:
                    continue
                adm_scenario_id = vol_obj.get('scenarioIndex')
                if not adm_scenario_id or 'vol' not in adm_scenario_id:
                    continue
                # There are four such objects, but we're ignoring the "comparison" pageType.
                elif vol_obj.get('pageType') == 'comparison':
                    continue
                # Use the admName, admTarget, and scenarioIndex (which is the scenario name) to find the matching adm in admTargetRuns
                pid_data.adm_name = vol_obj['admName']
                pid_data.adm_target = vol_obj['admTarget']
                pid_data.adm_scenario_id = adm_scenario_id
                if VERBOSE_OUTPUT:
                    print(f"-> Appending ADM info for pid={pid}: {pid_data.adm_name}, {pid_data.adm_target}, {adm_scenario_id}")
                process_pid(mongo_db, pid_data)


def process_pid(mongo_db, pid_data):
    adm_collection = mongo_db['admTargetRuns']
    comparison_collection = mongo_db['humanToADMComparison']
    adm_runs = adm_collection.find({'evalNumber': {'$in': [5, 6]}, 'adm_name': pid_data.adm_name, \
                                    'alignment_target': pid_data.adm_target, 'scenario': pid_data.adm_scenario_id})

    # In admTargetRuns, collect the ADM responses by searching through history for "Respond to TA1 Probe" commands.
    for adm_run in adm_runs:
        adm_probes = []
        for history_obj in adm_run['history']:
            if history_obj['command'] == 'Respond to TA1 Probe':
                probe = {'probe': {'choice': history_obj['parameters']['choice'], 'probe_id': history_obj['parameters']['probe_id']}}
                adm_probes.append(probe)
                #if VERBOSE_OUTPUT:
                #    print(f"Appending adm probe: {probe}")

        # Use the new SoarTech endpoint to compare the probe response choices from the respective scenario for the ADM (target) to human/text based (aligner).
        scores = soartech_utils.get_all_new_alignments(pid_data.text_probes, pid_data.text_scenario_id, adm_probes, pid_data.adm_scenario_id)
        if VERBOSE_OUTPUT:
            print(f"-> Got alignment scores: {scores}")

        # Store these three sets of alignment values (once for each seen ADM, four KDMAs per set) in the humanToADMComparison collection
        comparison_records = \
            comparison_collection.find({'pid': pid_data.pid, 'text_scenario': pid_data.text_scenario_id, 'adm_scenario': pid_data.adm_scenario_id,
                                        'adm_alignment_target': pid_data.adm_target})
        num_records = 0
        for comparison_record in comparison_records:
            num_records += 1
            if VERBOSE_OUTPUT:
                print(f"-> Updating id {comparison_record['_id']} with scores; pid: {pid_data.pid}; text_scenario: {pid_data.text_scenario_id}; adm_scenario: {pid_data.adm_scenario_id}; alignment target: {pid_data.adm_target}")
            if UPDATE_DATABASE:
                comparison_collection.update_one({'_id': comparison_record['_id']}, {'$set': {'calibration_scores': scores}})
        if num_records != 1: # Normally, there should only be 1
            print(f"NOTE: There are {num_records} comparison records.")
