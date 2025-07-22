from text_based_scenarios.convert_yaml_to_json_config_ph2 import main as add_phase_2_scenarios
from scripts._0_7_8_add_june_2025_scenarios import main as june_scenarios
import os, yaml
SCENARIOS_FOLDER = 'phase2/july2025'
def main(mongo_db):
    # first section uploads to scenarios collection to be used on adm results pages
    files = [f for f in os.listdir(SCENARIOS_FOLDER)]
    files.sort()

    for file in files:
        name = os.path.join(SCENARIOS_FOLDER, file)
        with open(name) as f: 
            yaml_obj = yaml.safe_load(f)
            yaml_obj["evalNumber"] = 9
            yaml_obj["evalName"] = "Phase 2 July 2025 Collaboration"

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

    print("Finished loading July 2025 evaluation scenarios.")

    # adds in missing june scenario
    june_scenarios(mongo_db)

    # generates new text based scenarios
    add_phase_2_scenarios(mongo_db)