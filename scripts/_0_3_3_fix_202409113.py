def fix_pid(mongo_db):
    text_scenario_results = mongo_db['userScenarioResults']

    documents = list(text_scenario_results.find(
        {"participantID": "202409113"}
    ).sort("startTime", 1))  
    
    unique_times = sorted(set(doc["startTime"] for doc in documents))
    if len(unique_times) != 2:
        print(f"Warning: Found {len(unique_times)} unique start times instead of expected 2")
        return
        
    text_scenario_results.update_many(
        {
            "participantID": "202409113",
            "startTime": unique_times[0]
        },
        {"$set": {"participantID": "202409113A"}}
    )
    
    text_scenario_results.update_many(
        {
            "participantID": "202409113",
            "startTime": unique_times[1]
        },
        {"$set": {"participantID": "202409113B"}}
    )
    