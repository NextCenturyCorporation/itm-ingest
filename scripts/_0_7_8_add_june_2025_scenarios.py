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
            yaml_obj["evalName"] = "June 2025 Collaboration"

            scenarios_collection = mongo_db["scenarios"]
            scenarios_collection.insert_one(yaml_obj)
            print("Loaded scenario: " + name)

    print("Finished loading June 2025 evaluation scenarios.")