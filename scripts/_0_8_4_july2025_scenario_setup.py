from text_based_scenarios.convert_yaml_to_json_config_ph2 import main as add_phase_2_scenarios
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
            scenarios_collection.insert_one(yaml_obj)
            print("Loaded scenario: " + name)

    print("Finished loading July 2025 evaluation scenarios.")

    # generates new text based scenarios
    add_phase_2_scenarios(mongo_db)