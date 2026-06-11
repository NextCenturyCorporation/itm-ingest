def main(mongo_db):
    counter = 0
    tcccResults = mongo_db['tcccResults']
    for doc in tcccResults.find(
        {"tccc_analysis.TCCC Triage Performance": {"$exists": True}}
    ):
        old_format = float(doc["tccc_analysis"]["TCCC Triage Performance"])
        new_format = str(old_format / 100)

        tcccResults.update_one({"_id": doc["_id"]}, 
            {"$set": {"tccc_analysis.TCCC Triage Performance": new_format}}
        )

        counter += 1
    
    print(f"Finished updating {counter} documents")