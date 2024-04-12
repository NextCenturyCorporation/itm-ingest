def update_scenario_index(mongoDB):
    survey_collection = mongoDB['surveyResults']

    survey_collection.update_many(
        {"results.Omnibus: Medic-A vs Medic-B": {"$exists": True}},
        {"$set": {"results.Omnibus: Medic-A vs Medic-B.scenarioIndex": 9}}
    )

    survey_collection.update_many(
        {"results.Omnibus: Medic-C vs Medic-D": {"$exists": True}},
        {"$set": {"results.Omnibus: Medic-C vs Medic-D.scenarioIndex": 10}}
    )

    print("Updates completed successfully.")