from copy import deepcopy

def main(mongo_db):
    adm_runs_collection = mongo_db['admTargetRuns']

    # Find all baseline runs from Eval 9
    baseline_runs = list(adm_runs_collection.find({
        "evalNumber": 9,
        "adm_name": { "$regex": "^ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3_8_8" }
    }))

    print(f"Found {len(baseline_runs)} baseline runs from Eval 9.")

    duplicate_runs =[]

    for run in baseline_runs:
        new_run = deepcopy(run)

        # Remove the Mongo id so that Mongo can generate a new one
        new_run.pop("_id", None)

        # Update fields
        new_run["evalNumber"] = 14
        new_run["evaluation"]["evalNumber"] = 14

        duplicate_runs.append(new_run)

    # Insert the duplicate runs into the DB
    if duplicate_runs:
        result = adm_runs_collection.insert_many(duplicate_runs)
        print(f"Inserted {len(result.inserted_ids)} duplicated baseline runs into Eval 14.")
    else:
        print("No baseline runs found to duplicate.")