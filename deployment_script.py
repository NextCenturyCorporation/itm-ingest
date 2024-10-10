from pymongo import MongoClient
from decouple import config
from scripts._0_2_8_human_to_adm_comparison import compare_probes
from scripts._0_2_9_percent_matching_probes import find_matching_probe_percentage
from scripts._0_3_0_remove_duplicate_text_entries import remove_duplicate_text_entries
VERSION_COLLECTION = "itm_version"
MONGO_URL = config('MONGO_URL')

# Change this version if running a new deploy script
db_version = "0.3.0"


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
        #compare_probes(mongoDB)
        #find_matching_probe_percentage(mongoDB)
        remove_duplicate_text_entries(mongoDB)
        update_db_version(mongoDB)
    else:
        print("Script does not need to run on prod, already updated.")


if __name__ == "__main__":
    main()
