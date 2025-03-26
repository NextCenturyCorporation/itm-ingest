import os
import yaml
from scripts._0_5_1_test_collection_improvements import main as test_mod
SCENARIOS_FOLDER = 'phase1/scenarios'

def main(mongo_db):
    
    files = [f for f in os.listdir(SCENARIOS_FOLDER)]
    files.sort()

    for file in files:
        if 'adept' in file.lower():
            name = os.path.join(SCENARIOS_FOLDER, file)
            with open(name) as f: 
                yaml_obj = yaml.safe_load(f)
                yaml_obj["evalNumber"] = 7
                yaml_obj["evalName"] = "Multi-kdma Experiment"

                scenarios_collection = mongo_db["scenarios"]
                scenarios_collection.insert_one(yaml_obj)
                print("Loaded scenario: " + name)

    print("Finished loading ADEPT Multi-kdma scenario files.")
    
    test_mod(mongo_db)

    # remove test data leaked into p1
    adm_target_runs = mongo_db["admTargetRuns"]
    
    adm_names_to_delete = [
        "ALIGN-ADM-ComparativeRegression-ADEPT__b3da51ed-57ff-429b-8ae8-6ff9dc44b65d",
        "itm-893test",
        "itm-893test2",
        "ALIGN-ADM-RelevanceComparativeRegression-ADEPT__025ec10e-92fe-4db6-9502-3217868d0cdd"
    ]
    
    delete_query = {
        "evalNumber": 5,
        "adm_name": {"$in": adm_names_to_delete}
    }

    # goodbye
    result = adm_target_runs.delete_many(delete_query)
    
    print(f"Deleted {result.deleted_count} test documents from admTargetRuns collection")