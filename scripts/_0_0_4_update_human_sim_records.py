def update_hum_sim_order_avg_across_scenes(mongoDB):
    human_simulator_collection = mongoDB['humanSimulator']
    all_human_sim_records = human_simulator_collection.find({})

    for sim_record in all_human_sim_records:
        queryObj = {
            "pid": sim_record["pid"],
            "ta1": sim_record["ta1"],
            "env": {"$ne": sim_record["env"]}
        }
        matching_record = human_simulator_collection.find_one(queryObj)

        if matching_record is not None:
            if sim_record["timestamp"] < matching_record["timestamp"]:
                sim_record["simOrder"] = 1
            else:
                sim_record["simOrder"] = 2

            if sim_record["data"]["alignment"] is not None and matching_record["data"]["alignment"] is not None:
                if len(sim_record["data"]["alignment"]["kdma_values"]) > 0 and len(matching_record["data"]["alignment"]["kdma_values"]) > 0:
                    sim_record["avgKDMA"] = (sim_record['data']['alignment']['kdma_values'][0]["value"] + matching_record['data']['alignment']['kdma_values'][0]["value"]) / 2

            human_simulator_collection.replace_one({"_id": sim_record["_id"]}, sim_record)
