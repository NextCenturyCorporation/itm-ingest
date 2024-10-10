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
    
    for participant_id, participant_results in grouped_results.items():
        ids_to_keep = remove_duplicates(participant_id, participant_results)
        
        # Remove all documents for this participant that are not in ids_to_keep
        delete_query = {
            "participantID": participant_id,
            "evalNumber": 4,
            "_id": {"$nin": ids_to_keep}
        }
        text_collection.delete_many(delete_query)

    print("Duplicate removal complete.")