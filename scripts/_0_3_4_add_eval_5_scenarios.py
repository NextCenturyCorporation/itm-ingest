import os
import yaml

TA1_FOLDER = "phase1/scenarios/"

def main(mongoDB):
    ta1files = [f for f in os.listdir(TA1_FOLDER)]
    ta1files.sort()

    for file in ta1files:
        file_name = os.path.join(TA1_FOLDER, file)
        with open(file_name) as f: 
            yaml_obj = yaml.safe_load(f)
            yaml_obj["evalNumber"] = 5
            yaml_obj["evalName"] = "Phase 1 Evaluation"

            scenarios_collection = mongoDB["scenarios"]
            scenarios_collection.insert_one(yaml_obj)
            print("Loaded scenario: " + file_name)

    print("Finished loading TA1 Phase 1 scenario files.")


