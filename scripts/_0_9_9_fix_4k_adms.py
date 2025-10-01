def main(mongo_db):
    adm_target_runs= mongo_db['admTargetRuns']
 
    query = {
        "evalNumber": 9,
        "adm_name": "ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3__3d1ccf2f-4ff1-4229-b346-ce1d28680c58"
    }

    update = {
        "$set": {
            "evalNumber": 11,
            "evaluation.evalNumber": 11,
            "evalName": "Phase 2 4D Experiment",
            "evaluation.evalName": "Phase 2 4D Experiment",
            "adm_name": "ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3",
            "evaluation.adm_name": "ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3"
        }
    }

    print("Updating baseline ADM entries.")
    result = adm_target_runs.update_many(query, update)
    print(f'Updated {result.modified_count} ADM entries.')

    query['adm_name'] = "ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-Mistral-7B-Instruct-v0.3__f630203b-f376-4cfa-8c74-8fa91a66e34b"
    update['$set']['adm_name'] = "ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-Mistral-7B-Instruct-v0.3"
    update['$set']['evaluation.adm_name'] = "ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-Mistral-7B-Instruct-v0.3"
    print("Updating aligned ADM entries.")
    result = adm_target_runs.update_many(query, update)
    print(f'Updated {result.modified_count} ADM entries.')
