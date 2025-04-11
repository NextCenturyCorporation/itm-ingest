from utils.golden_arm import get_alignments
import pandas as pd

def convert_probes(probes, scenario_id):
    return pd.DataFrame(
        {
            'ScenarioID': [scenario_id for _ in range(len(probes))],
            'ProbeID': [probe['probe']['probe_id'] for probe in probes],
            'ChoiceID': [probe['probe']['choice'] for probe in probes]
        }
    )


def get_new_vol_alignment(target_probes, target_scenario_id, comparison_probes, comparison_scenario_id):
    alignment_results = get_new_soartech_alignment(target_probes, target_scenario_id, comparison_probes, comparison_scenario_id, ('PerceivedQuantityOfLivesSaved',))
    return alignment_results.get('PerceivedQuantityOfLivesSaved')


def get_new_soartech_alignment(target_probes, target_scenario_id, comparison_probes, comparison_scenario_id, kdmas):
    target_dataframe = convert_probes(target_probes, target_scenario_id)
    comparison_dataframe = convert_probes(comparison_probes, comparison_scenario_id)

    # compute alignment results
    # TODO: Determine whether we need to randomize the seed
    alignment_results = get_alignments(target_dataframe, comparison_dataframe, scorecard_path='utils/scorecard.json', seed=1849241845, kdmas=kdmas)
    return alignment_results
