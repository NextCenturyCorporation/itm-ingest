from pymongo import MongoClient
from decouple import config 
import utils.soartech_utils as soartech_utils
from copy import deepcopy
from random import randint

"""
Test SoarTech "golden arm" alignment implementation.
For each vol scenario in the userScenarioResults collection, collect the probe responses, then create random ADM probe responses,
and send those to the new alignment endpoint.
At the end, run SoarTech's example to show getting the same values as SoarTech (0.967194).
"""
def main(mongo_db):
    text_scenario_collection = mongo_db['userScenarioResults']
    text_scenario_to_update = text_scenario_collection.find({"evalNumber": 6})
    num_scores = 0
    total_score = 0
    for entry in text_scenario_to_update:
        scenario_id = entry.get('scenario_id')

        # Get SoarTech VOL probe responses
        if ('vol-ph1-eval' in scenario_id):
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
            adm_probes = deepcopy(text_probes)
            # Create random ADM probe responses (but some probes only have two choices, so keep our options limited)
            for probe_num in range(6):
                adm_probes[probe_num]['probe']['choice'] = f"choice-{randint(0, 1)}"
            adm_scenario_id = scenario_id # These don't have to be the same, but for the sake of testing, let's keep them the same.
            score = soartech_utils.get_new_vol_alignment(adm_probes, adm_scenario_id, text_probes, scenario_id)
            print(f"New VOL Score is {score}.")
            total_score += score
            num_scores += 1

            # Try kdma-generic call with random seed
            kdma = 'PerceivedQuantityOfLivesSaved' if 'vol-ph1-eval' in scenario_id else 'QualityOfLife'
            scores = soartech_utils.get_new_soartech_alignment(adm_probes, adm_scenario_id, text_probes, scenario_id, (kdma,), True)
            print(f"Score is {scores}.")
            print(f"VOL score is {scores['PerceivedQuantityOfLivesSaved'] if scores.get('PerceivedQuantityOfLivesSaved') else 'n/a'}")
            print(f"QOL score is {scores['QualityOfLife'] if scores.get('QualityOfLife') else 'n/a'}")

            # Try "all scores" call with random seed
            scores = soartech_utils.get_all_new_alignments(adm_probes, adm_scenario_id, text_probes, scenario_id, True)
            print(f"Scores are {scores}.")

    print(f"\nTotal score for {num_scores} probe sets is {total_score / num_scores}.")
    print(f"\nSoarTech example:")
    # These probe responses were generated by consulting the DB for the
    # ADM run with TA1 session_id = 2be7bade-b628-42b0-8429-d1457685cafa
    # and delegator TA1 session_id = 020727f4-6647-4b87-bda0-e68a5184f2ee
    adm_scenario_id = 'vol-ph1-eval-2'
    adm_probes = [{'probe': {'choice': 'choice-0', 'probe_id': 'vol-ph1-eval-2-Probe-1'}},
                  {'probe': {'choice': 'choice-3', 'probe_id': 'vol-ph1-eval-2-Probe-2'}},
                  {'probe': {'choice': 'choice-1', 'probe_id': 'vol-ph1-eval-2-Probe-3'}},
                  {'probe': {'choice': 'choice-2', 'probe_id': 'vol-ph1-eval-2-Probe-4'}},
                  {'probe': {'choice': 'choice-0', 'probe_id': 'vol-ph1-eval-2-Probe-5'}},
                  {'probe': {'choice': 'choice-0', 'probe_id': 'vol-ph1-eval-2-Probe-6'}}]
    text_scenario_id = 'vol-ph1-eval-3'
    text_probes = [{'probe': {'choice': 'choice-2', 'probe_id': 'vol-ph1-eval-3-Probe-1'}},
                   {'probe': {'choice': 'choice-2', 'probe_id': 'vol-ph1-eval-3-Probe-2'}},
                   {'probe': {'choice': 'choice-1', 'probe_id': 'vol-ph1-eval-3-Probe-3'}},
                   {'probe': {'choice': 'choice-1', 'probe_id': 'vol-ph1-eval-3-Probe-4'}},
                   {'probe': {'choice': 'choice-0', 'probe_id': 'vol-ph1-eval-3-Probe-5'}},
                   {'probe': {'choice': 'choice-1', 'probe_id': 'vol-ph1-eval-3-Probe-6'}}]
    score = soartech_utils.get_new_vol_alignment(adm_probes, adm_scenario_id, text_probes, text_scenario_id)
    print(f"New VOL Score is {score}.")
    print(f"This {'matches' if score == 0.9671935933915454 else 'does not match'} the SoarTech Jupyter notebook value.")

    # Test random choices for vol3 for ADM and Human, using a random seed each time
    print("\nTesting random ADM and Human responses (this will take a few minutes):")
    lowest_score :float = 1.0
    total_score = 0
    num_tests = 10000
    for test_num in range(0, num_tests):
        adm_scenario_id = 'vol-ph1-eval-3'
        adm_probes = [{'probe': {'choice': f"choice-{randint(0, 4)}", 'probe_id': 'vol-ph1-eval-3-Probe-1'}},
                    {'probe': {'choice': f"choice-{randint(0, 3)}", 'probe_id': 'vol-ph1-eval-3-Probe-2'}},
                    {'probe': {'choice': f"choice-{randint(0, 1)}", 'probe_id': 'vol-ph1-eval-3-Probe-3'}},
                    {'probe': {'choice': f"choice-{randint(0, 2)}", 'probe_id': 'vol-ph1-eval-3-Probe-4'}},
                    {'probe': {'choice': f"choice-{randint(0, 1)}", 'probe_id': 'vol-ph1-eval-3-Probe-5'}},
                    {'probe': {'choice': f"choice-{randint(0, 1)}", 'probe_id': 'vol-ph1-eval-3-Probe-6'}}]
        text_scenario_id = 'vol-ph1-eval-3'
        text_probes = [{'probe': {'choice': f"choice-{randint(0, 4)}", 'probe_id': 'vol-ph1-eval-3-Probe-1'}},
                    {'probe': {'choice': f"choice-{randint(0, 3)}", 'probe_id': 'vol-ph1-eval-3-Probe-2'}},
                    {'probe': {'choice': f"choice-{randint(0, 1)}", 'probe_id': 'vol-ph1-eval-3-Probe-3'}},
                    {'probe': {'choice': f"choice-{randint(0, 2)}", 'probe_id': 'vol-ph1-eval-3-Probe-4'}},
                    {'probe': {'choice': f"choice-{randint(0, 1)}", 'probe_id': 'vol-ph1-eval-3-Probe-5'}},
                    {'probe': {'choice': f"choice-{randint(0, 1)}", 'probe_id': 'vol-ph1-eval-3-Probe-6'}}]
        score = soartech_utils.get_new_vol_alignment(adm_probes, adm_scenario_id, text_probes, text_scenario_id, True)
        total_score += score
        if test_num > 0 and test_num % 1000 == 0:
            print(f"Completed test #{test_num} of {num_tests}.")
        if score < lowest_score:
            lowest_score = score
            lowest_text_probes = deepcopy(text_probes)
            lowest_adm_probes = deepcopy(adm_probes)
    print(f"\nAfter {num_tests} runs, the average score was {total_score / num_tests} and the lowest score was {lowest_score}.")
    if lowest_score < 1.0:
        print(f"\n--> ADM/target Probe responses for lowest alignment score: {lowest_adm_probes}")
        print(f"--> Human/aligner Probe responses for lowest alignment score: {lowest_text_probes}")

    # Test opposite choices (wrt KDMA values) for ADM (high VOL) and human (low VOL), fixed seed.
    adm_scenario_id = 'vol-ph1-eval-3'
    adm_probes = [{'probe': {'choice': f"choice-0", 'probe_id': 'vol-ph1-eval-3-Probe-1'}},
                {'probe': {'choice': f"choice-2", 'probe_id': 'vol-ph1-eval-3-Probe-2'}},
                {'probe': {'choice': f"choice-1", 'probe_id': 'vol-ph1-eval-3-Probe-3'}},
                {'probe': {'choice': f"choice-1", 'probe_id': 'vol-ph1-eval-3-Probe-4'}},
                {'probe': {'choice': f"choice-0", 'probe_id': 'vol-ph1-eval-3-Probe-5'}},
                {'probe': {'choice': f"choice-1", 'probe_id': 'vol-ph1-eval-3-Probe-6'}}]
    text_scenario_id = 'vol-ph1-eval-3'
    text_probes = [{'probe': {'choice': f"choice-2", 'probe_id': 'vol-ph1-eval-3-Probe-1'}},
                {'probe': {'choice': f"choice-3", 'probe_id': 'vol-ph1-eval-3-Probe-2'}},
                {'probe': {'choice': f"choice-0", 'probe_id': 'vol-ph1-eval-3-Probe-3'}},
                {'probe': {'choice': f"choice-2", 'probe_id': 'vol-ph1-eval-3-Probe-4'}},
                {'probe': {'choice': f"choice-1", 'probe_id': 'vol-ph1-eval-3-Probe-5'}},
                {'probe': {'choice': f"choice-0", 'probe_id': 'vol-ph1-eval-3-Probe-6'}}]
    score = soartech_utils.get_new_vol_alignment(adm_probes, adm_scenario_id, text_probes, text_scenario_id)
    print(f"\nWith 'opposite' choices (ADM lowest VOL; human highest VOL), the alignment was {score}.")
    score = soartech_utils.get_new_vol_alignment(text_probes, adm_scenario_id, adm_probes, text_scenario_id)
    print(f"With 'opposite' choices (ADM highest VOL; human lowest VOL), the alignment was {score}.")

if __name__ == '__main__':
    client = MongoClient(config('MONGO_URL'))
    db = client.dashboard
    main(db)
