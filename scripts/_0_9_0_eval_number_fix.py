def main(mongo_db):
    adm_runs_collection = mongo_db['admTargetRuns']
    adm_runs_collection.update_many(
        {'evalNumber': '9'},
        {"$set": {"evalNumber": 9}}  
    )