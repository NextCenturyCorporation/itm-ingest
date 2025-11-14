from copy import deepcopy

def main(mongo_db):
    adm_runs_collection = mongo_db['admTargetRuns']

    # -------------------------------- Update the aligned ADM runs --------------------------------
    aligned_filter = {
        "adm_name": "ALIGN-ADM-DirectRegression-Mistral-7B-Instruct-v0.3__d2217c78-78ac-453a-833c-bf3a8ae9f831"
    }

    aligned_update = {
        "$set": {
            "evalNumber": 14,
            "evalName": "October 2025 ADM re-run",
            "adm_name": "ALIGN-ADM-DirectRegression-Mistral-7B-Instruct-v0.3_10_29",
            "evaluation.adm_name": "ALIGN-ADM-DirectRegression-Mistral-7B-Instruct-v0.3_10_29",
            "evaluation.evalNumber": 14,
            "evaluation.evalName": "October 2025 Aligned ADM re-run",
        }
    }

    aligned_result = adm_runs_collection.update_many(aligned_filter, aligned_update)
    print(f"Updated {aligned_result.modified_count} aligned ADM runs to Eval 14.")

    # --------- Check if baseline ADM runs for Eval 14 already exist; if so, skip duplication -----
    existing_eval14_baselines = adm_runs_collection.count_documents({
        "evalNumber": 14,
        "adm_name": {"$regex": "^ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3_8_8"}
    })

    if existing_eval14_baselines > 0:
        print(
            f"Eval 14 already contains {existing_eval14_baselines} baseline runs. "
            "Skipping duplication from Eval 9."
        )
        return

    # ----------------- Duplicate the basline adm runs from Eval 9 into Eval 14 -------------------
    baseline_runs = list(adm_runs_collection.find({
        "evalNumber": 9,
        "adm_name": {"$regex": "^ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3_8_8"}
    }))

    print(f"Found {len(baseline_runs)} baseline runs from Eval 9.")

    duplicate_runs = []

    for run in baseline_runs:
        new_run = deepcopy(run)

        # Remove the Mongo id so that Mongo can generate a new one
        new_run.pop("_id", None)

        # Update fields
        new_run["evalNumber"] = 14
        new_run["evaluation"]["evalNumber"] = 14
        new_run["evalName"] = "October 2025 ADM re-run"
        new_run["evaluation"]["evalName"] = "October 2025 ADM re-run"
        new_run["evaluation"]["adm_name"] = run["adm_name"]

        duplicate_runs.append(new_run)

    # Insert the duplicate runs into the DB
    if duplicate_runs:
        result = adm_runs_collection.insert_many(duplicate_runs)
        print(f"Inserted {len(result.inserted_ids)} duplicated baseline runs into Eval 14.")
    else:
        print("No baseline runs found to duplicate.")
