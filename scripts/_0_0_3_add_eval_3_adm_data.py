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
    
def load_ta1_yaml_files(ta1_folder, mongoDB):
    ta1files = [f for f in os.listdir(ta1_folder)]
    ta1files.sort()

    for file in ta1files:
        file_name = os.path.join(ta1_folder, file)
        with open(file_name) as f: 
            yaml_obj = yaml.safe_load(f)
            yaml_obj["evalNumber"] = 3
            yaml_obj["evalName"] = "Metrics Evaluation"

            scenarios_collection = mongoDB["scenarios"]
            scenarios_collection.insert_one(yaml_obj)

    print("Finished load TA1 scene files.")


def main(mongoDB):
    adm_folder_name = "metrics-adm-data"
    adm_files = [f for f in os.listdir(adm_folder_name)]
    adm_files.sort()

    for file in adm_files:
        adm_history = load_json_file(adm_folder_name, file)
        adm_history["evalNumber"] = 3
        adm_history["evalName"] = "Metrics Evaluation"

        test_collection = mongoDB["admTargetRuns"]
        test_collection.insert_one(adm_history)

    print("Finished loading ADM files")

    load_ta1_yaml_files("adept-evals", mongoDB)
    load_ta1_yaml_files("soartech-evals", mongoDB)
