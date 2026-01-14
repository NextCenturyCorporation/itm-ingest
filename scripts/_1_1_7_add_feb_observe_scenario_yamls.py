import os, yaml

SCENARIOS_FOLDER = 'phase2/feb2026/admrun'

KEEP_BASELINE_ADMS = {
    'ALIGN-ADM-OutlinesBaseline-DeepSeek-R1-Distill-Llama-8B__6d9ffe7b-a882-4846-9d8d-95a1644c76c2',
    'ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3__89e3b322-6865-41d1-8392-818c727aee6d',
    'ALIGN-ADM-OutlinesBaseline-spectrum-Llama-3.1-8B-v1__9b3bef95-7ff8-4764-852e-1953cc75498e',
    'ALIGN-ADM-OutlinesBaseline-spectrum-Qwen3-14B-v1__353ae8ef-b2a7-4a54-b890-031858b8c9ce'
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
    
    deleted_count = 0
    for adm in adms:
        adm_name = adm.get('adm_name', '')
        
        if 'Baseline' in adm_name:
            # delete baseline runs that were before ta1 fix
            if adm_name not in KEEP_BASELINE_ADMS:
                result = mongo_db['admTargetRuns'].delete_one({'_id': adm['_id']})
                if result.deleted_count > 0:
                    print(f"Deleted: {adm_name}")
                    deleted_count += 1
    
    print(f"Finished deleting unwanted baseline ADMs. Total deleted: {deleted_count}")