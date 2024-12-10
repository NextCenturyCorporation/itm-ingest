def main(mongoDB):
    text_scenario_collection = mongoDB['userScenarioResults']

    # only delete data that doesn't have a participantID (all dummy, unused data)
    text_scenario_collection.delete_many(
        {"participantID": {"$exists": False}}
    )

    print("Extraneous textbased results removed.")