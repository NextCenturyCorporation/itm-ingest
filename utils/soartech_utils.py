from utils.golden_arm import get_alignments
import pandas as pd
from random import randint

def convert_probes(probes, scenario_id):
    return pd.DataFrame(
        {
            'ScenarioID': [scenario_id for _ in range(len(probes))],
            'ProbeID': [probe['probe']['probe_id'] for probe in probes],
            'ChoiceID': [probe['probe']['choice'] for probe in probes]
        }
    )


def get_new_vol_alignment(target_probes, target_scenario_id, comparison_probes, comparison_scenario_id, random_seed = False):
    alignment_results = get_new_soartech_alignment(target_probes, target_scenario_id, comparison_probes,
                                                   comparison_scenario_id, ('PerceivedQuantityOfLivesSaved',), random_seed)
    return alignment_results.get('PerceivedQuantityOfLivesSaved')


def get_all_new_alignments(target_probes, target_scenario_id, comparison_probes, comparison_scenario_id, random_seed = False):
    return get_new_soartech_alignment(target_probes, target_scenario_id, comparison_probes, comparison_scenario_id,
                                      ('QualityOfLife', 'PerceivedQuantityOfLivesSaved', 'MissionSuccess', 'RiskTolerance'), random_seed)


def get_new_soartech_alignment(target_probes, target_scenario_id, comparison_probes, comparison_scenario_id, kdmas, random_seed = False):
    target_dataframe = convert_probes(target_probes, target_scenario_id)
    comparison_dataframe = convert_probes(comparison_probes, comparison_scenario_id)

    # compute alignment results
    alignment_results = get_alignments(target_dataframe, comparison_dataframe, scorecard_path='utils/scorecard.json',
                                       seed=(randint(0, 9999999999) if random_seed else 1849241845), kdmas=kdmas)
    return alignment_results
