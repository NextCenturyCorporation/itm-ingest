from delegation_survey.phase2_covert_adm_to_del_materials import main as convert_adms
from scripts._1_2_2_post_scenario_measures import main as post_scenario
from delegation_survey.update_survey_config import version12_setup
def main(mongo_db):
    SCENARIO_ADMS = {
        'June2026-AF-SS-observe': {
            "baseline": "ALIGN-ADM-OutlinesBaseline-DeepSeek-R1-Distill-Llama-8B__4b73ce57-c70f-407d-ac95-1b5d317aaccc",
            "aligned":  "ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-DeepSeek-R1-Distill-Llama-8B__475d3f70-11a5-4d51-9ccb-b241741f0f7c"
        },
        'June2026-AF-observe': {
            "baseline": "ALIGN-ADM-OutlinesBaseline-spectrum-Qwen3-14B-v1__25c09905-78fa-41f0-901a-dd9dd8bdfb7a",
            "aligned":  "ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-spectrum-Qwen3-14B-v1__572663f2-3b45-4295-ab2f-5f31dc1e910f"
        },
        'June2026-AF-observe-trinary': {
            "baseline": "ALIGN-ADM-OutlinesBaseline-DeepSeek-R1-Distill-Llama-8B__661d9a05-104e-4f1e-b3b5-37089ae9eb81",
            "aligned":  "ALIGN-ADM-Ph2-DirectRegression-Trinary-DeepSeek-R1-Distill-Llama-8B__3630c782-71d2-4e68-a1f5-72c9d65c34a8"
        },
        'June2026-PS-observe': {
            "baseline": "ALIGN-ADM-OutlinesBaseline-spectrum-Llama-3.1-8B-v1__bf0cd49f-64e0-4d78-b513-58a35b333a3b",
            "aligned":  "ALIGN-ADM-Ph2-DirectRegression-BertRelevance-spectrum-Llama-3.1-8B-v1__c449c8ae-73da-472b-8305-2d6c98d88411"
        },
        'June2026-PS-observe-trinary': {
            "baseline": "ALIGN-ADM-OutlinesBaseline-DeepSeek-R1-Distill-Llama-8B__661d9a05-104e-4f1e-b3b5-37089ae9eb81",
            "aligned":  "ALIGN-ADM-Ph2-DirectRegression-Trinary-DeepSeek-R1-Distill-Llama-8B__3630c782-71d2-4e68-a1f5-72c9d65c34a8"
        },
    }

    included_adms = []
    for scenario_id, adms in SCENARIO_ADMS.items():
        runs = mongo_db['admTargetRuns'].find({
            'evalNumber': 17,
            'scenario': scenario_id,
            'adm_name': {'$in': list(adms.values())}
        })
        included_adms.extend(runs)

    convert_adms(mongo_db, 17, 'june2026/admrun', included_adms)
    version12_setup(auto_confirm=True)
    post_scenario(mongo_db)