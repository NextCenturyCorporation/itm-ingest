def main(mongo_db):
    adm_runs_collection = mongo_db['admTargetRuns']
    adm_runs_collection.update_many(
        {'adm_name': 'ALIGN-ADM-DirectRegression-Mistral-7B-Instruct-v0.3__d2217c78-78ac-453a-833c-bf3a8ae9f831'},
        {"$set": {"evalNumber": 14}},
        {"$set": {"evalName": "October 2025 Aligned ADM re-run"}},
        {"$set": {"adm_name": "ALIGN-ADM-DirectRegression-Mistral-7B-Instruct-v0.3_10_29"}}
    )