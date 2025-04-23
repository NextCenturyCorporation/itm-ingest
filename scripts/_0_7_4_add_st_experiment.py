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
UPDATE_DATABASE = False
def main(mongo_db):
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
                            print('Could not find response in mapping!', response, list(mapping.keys()))
            comparison_data[pid] = Pid_data(pid, text_scenario_id, text_probes)
            print(f"Saving comparison data for pid={pid}: {comparison_data[pid]}")

    survey_results_collection = mongo_db['surveyResults']
    adm_collection = mongo_db['admTargetRuns']
    comparison_collection = mongo_db['humanToADMComparison']

    for pid in comparison_data.keys():
        # Take the above pid and find the documents in surveyResults that it maps to
        survey_results = survey_results_collection.find({'results.pid': pid})
        pid_data: Pid_data = comparison_data[pid]
        # Iterate through the keys in each result until we find the objects with scenarioIndex containing "vol"
        for survey_result in survey_results:
            for key in survey_result['results']:
                vol_obj = key.find({'scenarioIndex': {'$regex': 'vol'}})
                #vol_obj = key.find({'scenarioIndex': {'$in': ['vol-ph1-eval-2', 'vol-ph1-eval-3', 'vol-ph1-eval-4']}})
                # There are four such objects, but we're ignoring the "comparison" pageType.
                if vol_obj.get('pageType') == 'comparison':
                    continue
                # Use the admName, admTarget, and scenarioIndex (which is the scenario name) to find the matching adm in admTargetRuns
                adm_name = vol_obj['admName']
                adm_target = vol_obj['admTarget']
                adm_scenario = vol_obj['scenarioIndex']
                pid_data.adm_info.append((vol_obj['admName'], vol_obj['admTarget'], vol_obj['scenarioIndex']))
                print(f"Appending adm_info for pid={pid}: {(vol_obj['admName'], vol_obj['admTarget'], vol_obj['scenarioIndex'])}")

                # In admTargetRuns, collect the ADM responses by searching through history for "Respond to TA1 Probe" commands.
                adm_runs = adm_collection.find({'evalNumber': {'$in': [5, 6]}, 'adm_name': adm_name, \
                                                'alignment_target': adm_target, 'scenario': adm_scenario})
                for adm_run in adm_runs:
                    adm_probes = []
                    for history_obj in adm_run['history']:
                        if history_obj['command'] == 'Respond to TA1 Probe':
                            parms = history_obj['parameters']
                            # adm_probes = [{'probe': {'choice': 'choice-0', 'probe_id': 'vol-ph1-eval-2-Probe-1'}},
                            adm_probes.append({'probe': {'choice': parms['choice'], 'probe_id': parms['probe_id']}})
                            print(f"Appending adm probes: {{'probe': {'choice': parms['choice'], 'probe_id': parms['probe_id']}}}")

                            # Use the new SoarTech endpoint to compare the probe response choices from the respective scenario for the ADM (target) to human/text based (aligner).
                            scores = soartech_utils.get_all_new_alignments(pid_data.text_probes, pid_data.text_scenario_id, adm_probes, adm_scenario)
                            print(f"Got alignment scores: {scores}")
                            # Store these three sets of alignment values (once for each seen ADM, four KDMAs per set) in the humanToADMComparison collection
                            comparison_records = \
                                comparison_collection.find({'pid': pid, 'text_scenario': pid_data.text_scenario_id, 'adm_scenario': adm_scenario,
                                                            'adm_alignment_target': adm_target})
                            print(f"There are {len(comparison_records)} comparison records.")
                            if UPDATE_DATABASE:
                                for comparison_record in comparison_records: # should only be 1?
                                    comparison_collection.update_one({'_id': comparison_record['_id']}, {'$set': {'calibration_scores': scores}})


@dataclass
class Pid_data:
    pid: str
    text_scenario_id: str
    text_probes: list
    adm_info = []