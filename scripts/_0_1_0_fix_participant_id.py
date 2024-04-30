def fix_participant_id(mongoDB):
    text_scenario_collection = mongoDB['userScenarioResults']

    text_scenario_collection.update_many(
        {"participantID": "2021216"},
        {"$set": {"participantID": "2024216"}}
    )

    text_scenario_collection.update_many(
        {"participantID": "202402"},
        {"$set": {"participantID": "2024202"}}
    )

    text_scenario_collection.update_many(
        {"participantID": "202417"},
        {"$set": {"participantID": "2024217"}}
    )

    text_scenario_collection.update_many(
        {"participantID": "202419"},
        {"$set": {"participantID": "2024219"}}
    )

    print("Completed updating text scenario participant ID.")