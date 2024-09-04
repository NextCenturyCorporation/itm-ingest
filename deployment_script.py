from pymongo import MongoClient
from decouple import config
import os
from scripts._0_1_9_add_evalIDs_to_data import load_data

VERSION_COLLECTION = "itm_version"
MONGO_URL = config('MONGO_URL')

# Change this version if running a new deploy script
db_version = "0.1.9"

def check_version(mongoDB):
    collection = mongoDB[VERSION_COLLECTION]
    version_obj = collection.find_one()
    if version_obj is None:
        return True 
    # return true if it is a newer db version
    return db_version > version_obj['version']

def update_db_version(mongoDB):
    collection = mongoDB[VERSION_COLLECTION]
    version_obj = collection.find_one()
    if version_obj is None:
        collection.insert_one({"version": db_version})
    else: 
        version_obj['version'] = db_version
        collection.replace_one({"_id": version_obj["_id"]}, version_obj)

def main():
    client = MongoClient(MONGO_URL)
    mongoDB = client['dashboard']
    if(check_version(mongoDB)):
        print("New db version, execute scripts")

        load_data(mongoDB)
    else:
        print("Script does not need to run on prod, already updated.")


if __name__ == "__main__":
    main()
