import os, yaml
SCENARIOS_FOLDER = 'phase2/feb2026/admrun'
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