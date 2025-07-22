import os
import yaml

SCENARIOS_FOLDER = 'phase2/june2025'
def main(mongo_db):
    files = [f for f in os.listdir(SCENARIOS_FOLDER)]
    files.sort()

    for file in files:
        name = os.path.join(SCENARIOS_FOLDER, file)
        with open(name) as f: 
            yaml_obj = yaml.safe_load(f)
            yaml_obj["evalNumber"] = 8
            yaml_obj["evalName"] = "Phase 2 June 2025 Collaboration"

            scenarios_collection = mongo_db["scenarios"]
            scenario_id = yaml_obj.get("id")
            if scenario_id:
                result = scenarios_collection.replace_one(
                    {"id": scenario_id},
                    yaml_obj,
                    upsert=True  
                )