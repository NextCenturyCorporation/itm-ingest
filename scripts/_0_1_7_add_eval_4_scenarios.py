import os
import io
import json
import yaml

def load_json_file(folder: str, file_name: str) -> dict:
    """Read in a json file and decode into a dict.  Can
    be used for history, scene, or other json files."""
    with io.open(
            os.path.join(
                folder, file_name),
            mode='r',
            encoding='utf-8-sig') as json_file:
        return json.loads(json_file.read())
    
def main(ta1_folder, mongoDB):
    ta1files = [f for f in os.listdir(ta1_folder)]
    ta1files.sort()

    for file in ta1files:
        file_name = os.path.join(ta1_folder, file)
        with open(file_name) as f: 
            yaml_obj = yaml.safe_load(f)
            yaml_obj["evalNumber"] = 4
            yaml_obj["evalName"] = "Dry Run Evaluation"

            scenarios_collection = mongoDB["scenarios"]
            scenarios_collection.insert_one(yaml_obj)
            print("Loaded scenario: " + file_name)

    print("Finished load TA1 scene files.")


