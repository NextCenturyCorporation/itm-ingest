def fix_pid(mongo_db):
    text_scenario_results = mongo_db['userScenarioResults']

    documents = list(text_scenario_results.find(
        {"participantID": "202409113"}
    ).sort("startTime", 1))  
    
    unique_times = sorted(set(doc["startTime"] for doc in documents))
    if len(unique_times) == 2:
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

    participant_log = mongo_db['participantLog']
    
    original_entry = participant_log.find_one({"ParticipantID": 202409113})
    
    if original_entry:
        entry_a = original_entry.copy()
        entry_b = original_entry.copy()
        
        entry_a["ParticipantID"] = "202409113A"
        entry_a["textEntryCount"] = 5
        entry_b["ParticipantID"] = "202409113B"
        entry_b["textEntryCount"] = 5
        
        entry_a.pop('_id', None)
        entry_b.pop('_id', None)
        
        participant_log.insert_one(entry_a)
        participant_log.insert_one(entry_b)
        
        participant_log.delete_one({"ParticipantID": 202409113})
    else:
        print("Warning: Original participant log entry not found")