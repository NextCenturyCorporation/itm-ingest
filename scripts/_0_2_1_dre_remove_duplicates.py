def main(mongoDB):
    results_collection = mongoDB['test']

    adm_names_to_remove = [
        "TAD-baseline",
        "TAD",
        "ALIGN-ADM-Random__9e0997cb-70cb-4f5d-a085-10f359636517",
        "ALIGN-ADM-HybridRegression__065fac00-4446-4e9c-895f-83691abc7f49",
        "ALIGN-ADM-ComparativeRegression+ICL+Template__cb273914-de37-472d-9c3b-4bc0d96cec3a"
    ]

    for adm_name in adm_names_to_remove:
        results_collection.delete_many({"evalNumber": 4, "history.parameters.adm_name": adm_name})

    print("All unused DRE ADMs have been removed.")

    # DELETE TAD-ALIGNED runs that aren't from a certain day
    results_collection.delete_many({"evalNumber": 4, "history.parameters.adm_name": "TAD-aligned", "evaluation.created": {"$ne": "2024-08-30 20:37:42.197138"}})

    adm_update_names = [
        {"current_name": "ALIGN-ADM-ComparativeRegression+ICL+Template__3f624e78-4e27-4be2-bec0-6736a34152c2",
         "new_name": "ALIGN-ADM-ComparativeRegression-ICL-Template"},
        {"current_name": "ALIGN-ADM-ComparativeRegression+ICL+Template__462987bd-77f8-47a3-8efe-22e388b5f858",
         "new_name": "ALIGN-ADM-ComparativeRegression-ICL-Template"},
        {"current_name": "ALIGN-ADM-OutlinesBaseline__458d3d8a-d716-4944-bcc4-d20ec0a9d98c",
         "new_name": "ALIGN-ADM-OutlinesBaseline"},
        {"current_name": "ALIGN-ADM-OutlinesBaseline__486af8ca-fd13-4b16-acc3-fbaa1ac5b69b",
         "new_name": "ALIGN-ADM-OutlinesBaseline"},
        {"current_name": "TAD-aligned",
         "new_name": "TAD-aligned"},
        {"current_name": "TAD-severity-baseline",
         "new_name": "TAD-severity-baseline"}
    ]

    adept_to_remove_from_one_kitware_run = [
        'DryRunEval-MJ2-eval',
        'DryRunEval-MJ4-eval',
        'DryRunEval-MJ5-eval'
    ]

    for adm_record_name in adm_update_names:
        non_duplicate_records = []
        duplicate_records = []
        adm_records = results_collection.find({"evalNumber": 4, "history.parameters.adm_name": adm_record_name["current_name"]})
        for record in adm_records:
            is_duplicate = False
            for dup_check_record in non_duplicate_records:
                history_length = len(record["history"])
                dup_history_length = len(dup_check_record["history"])
                if len(non_duplicate_records) > 0 and history_length == dup_history_length:
                    if record["history"][history_length-1]["response"]["alignment_source"][0]["scenario_id"] == dup_check_record["history"][dup_history_length-1]["response"]["alignment_source"][0]["scenario_id"] and record["history"][history_length-1]["parameters"]["target_id"] == dup_check_record["history"][dup_history_length-1]["parameters"]["target_id"]:
                        is_duplicate = True

            # Kitware wants these ADEPT runs replaced
            if adm_record_name["current_name"] == "ALIGN-ADM-OutlinesBaseline__486af8ca-fd13-4b16-acc3-fbaa1ac5b69b":
                if record["history"][len(record["history"])-1]["response"]["alignment_source"][0]["scenario_id"] in adept_to_remove_from_one_kitware_run:
                    is_duplicate = True
                    
            if is_duplicate:
                duplicate_records.append(record["_id"])
            else:
                non_duplicate_records.append(record)    

        results_collection.delete_many({'_id': {'$in': duplicate_records}})

        for non_dup_record in non_duplicate_records:
            for history_record in non_dup_record["history"]:
                if "adm_name" in history_record["parameters"]:
                    if history_record["parameters"]["adm_name"] == adm_record_name["current_name"]:
                        history_record["parameters"]["adm_name"] = adm_record_name["new_name"]
            results_collection.replace_one({'_id': non_dup_record['_id']}, non_dup_record)
