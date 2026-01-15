import os
import yaml
from datetime import datetime

SCENARIOS_FOLDER = 'phase2/feb2026/admrun'

KEEP_BASELINE_ADMS = {
    'ALIGN-ADM-OutlinesBaseline-DeepSeek-R1-Distill-Llama-8B__6d9ffe7b-a882-4846-9d8d-95a1644c76c2',
    'ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3__89e3b322-6865-41d1-8392-818c727aee6d',
    'ALIGN-ADM-OutlinesBaseline-spectrum-Llama-3.1-8B-v1__9b3bef95-7ff8-4764-852e-1953cc75498e',
    'ALIGN-ADM-OutlinesBaseline-spectrum-Qwen3-14B-v1__353ae8ef-b2a7-4a54-b890-031858b8c9ce',
    'ALIGN-ADM-OutlinesBaseline-DeepSeek-R1-Distill-Llama-8B__654f723a-a594-4b32-874a-833540067564',
    'ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3__7013f3b9-6c32-4c5a-b140-0ee5a375db54',
    'ALIGN-ADM-OutlinesBaseline-spectrum-Llama-3.1-8B-v1__babcf1ca-0489-4426-be9e-bf2947f3a2f9',
    'ALIGN-ADM-OutlinesBaseline-spectrum-Qwen3-14B-v1__d37bf24d-273b-4133-b469-b6a5caef3635'
}

KEEP_ALIGNED_ADMS = {
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-DeepSeek-R1-Distill-Llama-8B__7f71beec-af02-41cf-9ddc-94616769750f',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-Mistral-7B-Instruct-v0.3__bf7d613c-f38c-42de-8eef-cec5868cccb1',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-spectrum-Llama-3.1-8B-v1__f3e4cce5-933f-4a49-a27b-c15a08b76492',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-spectrum-Qwen3-14B-v1__783573b5-96c9-485b-a4f6-eb81ddc550d5',
    'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-Mistral-7B-Instruct-v0.3__596c459d-b735-4a7a-8bf6-815d804e4092',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-DeepSeek-R1-Distill-Llama-8B__30b1f803-cd61-4eaa-a9de-ed18cd944067',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-Mistral-7B-Instruct-v0.3__84d41345-5964-4f15-92bc-2b839911c546',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-spectrum-Llama-3.1-8B-v1__b1403cb2-d254-40c9-9793-315adf98d1f3',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-spectrum-Qwen3-14B-v1__3d831590-27ae-4be8-a81f-722e193cdce3',
    'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-Mistral-7B-Instruct-v0.3__89d49877-0eb0-4919-aac1-92860615d131'
}

def rename_adm(adm_doc):
    old_name = adm_doc.get('adm_name', '')
    evaluation = adm_doc.get('evaluation', {})
    start_time = evaluation.get('start_time')

    if not old_name or '__' not in old_name or not start_time:
        return None

    base = old_name.split('__')[0]
    dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S.%f")
    suffix = f"{dt.month:02d}_{dt.day:02d}"
    return f"{base}_{suffix}"

def main(mongo_db):
    files = sorted(os.listdir(SCENARIOS_FOLDER))

    for file in files:
        path = os.path.join(SCENARIOS_FOLDER, file)
        with open(path) as f:
            yaml_obj = yaml.safe_load(f)
            yaml_obj["evalNumber"] = 15
            yaml_obj["evalName"] = "Phase 2 February 2026 Collaboration"

            scenarios = mongo_db["scenarios"]
            scenario_id = yaml_obj.get("id")

            if scenario_id:
                result = scenarios.replace_one(
                    {"id": scenario_id},
                    yaml_obj,
                    upsert=True
                )
                if result.matched_count:
                    print(f"Replaced: {file}")
                else:
                    print(f"Uploaded: {file}")

    print("Finished ingesting Feb 2026 observation scenarios.")

    adms = mongo_db['admTargetRuns'].find({'evalNumber': 15})

    deleted_baseline = 0
    deleted_regression = 0
    deleted_no_underscore = 0

    for adm in adms:
        original_adm_name = adm.get('adm_name', '')

        if '__' not in original_adm_name:
            mongo_db['admTargetRuns'].delete_one({'_id': adm['_id']})
            deleted_no_underscore += 1
            print(f"Deleted ADM (no '__'): {original_adm_name}")
            continue

        should_delete = False

        if 'Baseline' in original_adm_name:
            if original_adm_name not in KEEP_BASELINE_ADMS:
                should_delete = True
                deleted_baseline += 1

        elif 'Regression' in original_adm_name:
            if original_adm_name not in KEEP_ALIGNED_ADMS:
                should_delete = True
                deleted_regression += 1

        if should_delete:
            mongo_db['admTargetRuns'].delete_one({'_id': adm['_id']})
            print(f"Deleted ADM: {original_adm_name}")
            continue

        new_name = rename_adm(adm)
        if new_name and new_name != original_adm_name:
            mongo_db['admTargetRuns'].update_one(
                {'_id': adm['_id']},
                {'$set': {
                    'adm_name': new_name,
                    'evaluation.adm_name': new_name
                }}
            )
            print(f"Renamed ADM: {original_adm_name} -> {new_name}")

    print("Finished deleting unwanted ADMs.")
    print(f"Total Baseline ADMs deleted: {deleted_baseline}")
    print(f"Total Regression ADMs deleted: {deleted_regression}")
    print(f"Deleted test runs: {deleted_no_underscore}")