def remove_duplicates(pid, results):
    seen = set()
    filtered_results = []
    ids_to_keep = []

    for result in results:
        start_time = result.get('startTime')
        scenario_id = result.get('scenario_id')
        
        key = (start_time, scenario_id)
        
        if key not in seen:
            seen.add(key)
            filtered_results.append(result)
            ids_to_keep.append(result['_id'])
        
    return ids_to_keep

def remove_duplicate_text_entries(mongo_db):
    text_collection = mongo_db['userScenarioResults']
    eval_4_results = list(text_collection.find({"evalNumber": 4}))

    grouped_results = {}
    for result in eval_4_results:
        participant_id = result.get('participantID')
        if participant_id not in grouped_results:
            grouped_results[participant_id] = []
        grouped_results[participant_id].append(result)
    
    total_deleted = 0
    for participant_id, participant_results in grouped_results.items():
        ids_to_keep = remove_duplicates(participant_id, participant_results)
        
        delete_query = {
            "participantID": participant_id,
            "evalNumber": 4,
            "_id": {"$nin": ids_to_keep}
        }
        delete_result = text_collection.delete_many(delete_query)
        total_deleted += delete_result.deleted_count

    suzy_delete_result = text_collection.delete_many({"participantID": "suzy"})
    total_deleted += suzy_delete_result.deleted_count

    specific_delete_query = {
        "participantID": "202409115",
        "evalNumber": {"$ne": 4}
    }

    specific_delete_result = text_collection.delete_many(specific_delete_query)
    total_deleted += specific_delete_result.deleted_count

    ewfsdfsd_delete_result = text_collection.delete_many({"participantID": "ewfsdfsd"})
    total_deleted += ewfsdfsd_delete_result.deleted_count

    delete_202409116_result = text_collection.delete_many({"participantID": "202409116"})
    total_deleted += delete_202409116_result.deleted_count

    print(f"Duplicate removal complete. Total documents deleted: {total_deleted}")