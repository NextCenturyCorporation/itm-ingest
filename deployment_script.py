from pymongo import MongoClient
import os
from scripts._0_0_3_add_eval_3_adm_data import add_eval_3_adm_data
from scripts._0_0_4_update_human_sim_records import update_hum_sim_order_avg_across_scenes
from scripts._0_0_5_remove_old_adm_data import remove_old_adm_records
from scripts._0_0_6_set_admin_users import add_admin_user_role
from scripts._0_0_7_update_scenario_index import update_scenario_index

VERSION_COLLECTION = "itm_version"

# Change this version if running a new deploy script
db_version = "0.0.7"


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
    client = MongoClient(
        "mongodb://simplemongousername:simplemongopassword@localhost:27030/?authSource=dashboard")
    mongoDB = client['dashboard']
    if(check_version(mongoDB)):
        print("New db version, execute scripts")

        # Place scripts here to run
        update_hum_sim_order_avg_across_scenes(mongoDB)
        remove_old_adm_records(mongoDB)
        add_eval_3_adm_data(mongoDB)
        add_admin_user_role(mongoDB)
        update_scenario_index(mongoDB)

        # Run Script for Probe Matching and importing human data
        os.system("python3 probe_matcher.py -i metrics-data/")

        # Now update db version
        update_db_version(mongoDB)
    else:
        print("Script does not need to run on prod, already updated.")


if __name__ == "__main__":
    main()
