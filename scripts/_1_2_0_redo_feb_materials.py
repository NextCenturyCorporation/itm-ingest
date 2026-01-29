from scripts._1_1_8_feb_del_materials import main as make_new_survey

def main(mongo_db):
    # delete the old survey version 10
    mongo_db["delegationConfig"].delete_one({"_id": "delegation_v10.0"})
    print("Deleted old survey version 10 config file.")
    mongo_db['admMedics'].delete_many({'evalNumber': 15})
    make_new_survey(mongo_db)