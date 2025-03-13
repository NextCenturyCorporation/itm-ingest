def main(mongoDB):
    scenarios_collection = mongoDB["scenarios"]
    all_scenarios = scenarios_collection.find({})
   
    for scenario in all_scenarios:
        if scenario["id"] == "ADEPT1" or scenario["id"] == "kickoff-demo-scenario-1":
            scenario["evalNumber"] = 1
            scenario["evalName"] = "MVP"
        else:
            scenario["evalNumber"] = 2
            scenario["evalName"] = "September Milestone"

        scenarios_collection.replace_one({"_id": scenario["_id"]}, scenario)

    print("All scenarios updated with eval information")

    test_collection = mongoDB["admTargetRuns"]
    all_test_records = test_collection.find({})

    for test_record in all_test_records:
        if isinstance( test_record["history"][0]["response"], dict):
            if test_record["history"][0]["response"]["id"]  == "ADEPT1" or test_record["history"][0]["response"]["id"]  == "kickoff-demo-scenario-1":
                test_record["evalNumber"] = 1
                test_record["evalName"] = "MVP"
        else:
            test_record["evalNumber"] = 2
            test_record["evalName"] = "September Milestone"

        test_collection.replace_one({"_id": test_record["_id"]}, test_record)

    print("All test records updated with eval information")