import os, yaml

SCENARIOS_FOLDER = 'phase2/feb2026/admrun'

KEEP_BASELINE_ADMS = {
    'ALIGN-ADM-OutlinesBaseline-DeepSeek-R1-Distill-Llama-8B__6d9ffe7b-a882-4846-9d8d-95a1644c76c2',
    'ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3__89e3b322-6865-41d1-8392-818c727aee6d',
    'ALIGN-ADM-OutlinesBaseline-spectrum-Llama-3.1-8B-v1__9b3bef95-7ff8-4764-852e-1953cc75498e',
    'ALIGN-ADM-OutlinesBaseline-spectrum-Qwen3-14B-v1__353ae8ef-b2a7-4a54-b890-031858b8c9ce'
}

KEEP_ALIGNED_ADMS = {
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-DeepSeek-R1-Distill-Llama-8B__7f71beec-af02-41cf-9ddc-94616769750f',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-Mistral-7B-Instruct-v0.3__bf7d613c-f38c-42de-8eef-cec5868cccb1',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-spectrum-Llama-3.1-8B-v1__f3e4cce5-933f-4a49-a27b-c15a08b76492',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-spectrum-Qwen3-14B-v1__783573b5-96c9-485b-a4f6-eb81ddc550d5',
    'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-Mistral-7B-Instruct-v0.3__596c459d-b735-4a7a-8bf6-815d804e4092'
}

def main(mongo_db):
    files = [f for f in os.listdir(SCENARIOS_FOLDER)]
    files.sort()

    for file in files:
        name = os.path.join(SCENARIOS_FOLDER, file)
        with open(name) as f: 
            yaml_obj = yaml.safe_load(f)
            yaml_obj["evalNumber"] = 15
            yaml_obj["evalName"] = "Phase 2 February 2026 Collaboration"

            scenarios_collection = mongo_db["scenarios"]
            scenario_id = yaml_obj.get("id")
            if scenario_id:
                # Replace instead of adding new
                result = scenarios_collection.replace_one(
                    {"id": scenario_id},
                    yaml_obj,
                    upsert=True 
                )
                
                if result.matched_count > 0:
                    print(f"Replaced: {name} in scenarios collection")
                else:
                    print(f"Uploaded: {name} to scenarios collection")

    print("Finished ingesting July 2026 observation scenarios.")

    adms = mongo_db['admTargetRuns'].find({'evalNumber': 15})
    
    deleted_baseline_count = 0
    deleted_regression_count = 0
    
    for adm in adms:
        adm_name = adm.get('adm_name', '')
        
        # Delete baseline runs that were before TA1 fix
        if 'Baseline' in adm_name:
            if adm_name not in KEEP_BASELINE_ADMS:
                result = mongo_db['admTargetRuns'].delete_one({'_id': adm['_id']})
                if result.deleted_count > 0:
                    print(f"Deleted Baseline: {adm_name}")
                    deleted_baseline_count += 1
        
        # Delete regression runs that were before TA1 fix
        elif 'Regression' in adm_name:
            if adm_name not in KEEP_ALIGNED_ADMS:
                result = mongo_db['admTargetRuns'].delete_one({'_id': adm['_id']})
                if result.deleted_count > 0:
                    print(f"Deleted Regression: {adm_name}")
                    deleted_regression_count += 1
    
    print(f"Finished deleting unwanted ADMs.")
    print(f"Total Baseline ADMs deleted: {deleted_baseline_count}")
    print(f"Total Regression ADMs deleted: {deleted_regression_count}")