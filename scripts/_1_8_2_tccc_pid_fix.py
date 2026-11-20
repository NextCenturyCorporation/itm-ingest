def main(mongo_db):
    tcccResults = mongo_db['tcccResults']

    for old_pid in ["202909162", "202909167"]:
        doc = tcccResults.find_one({"_id": old_pid})

        new_pid = "2026" + old_pid[4:]
        doc["_id"] = new_pid
        doc["pid"] = new_pid
        doc["eval"] = doc["eval"].replace("2029", "2026")

        tcccResults.insert_one(doc)
        tcccResults.delete_one({"_id": old_pid})
        print(f"Updated {old_pid} -> {new_pid}")