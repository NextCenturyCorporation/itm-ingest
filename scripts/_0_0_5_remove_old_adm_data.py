def main(mongoDB):
    adm_collection = mongoDB['admTargetRuns']
    adm_collection.delete_many({"evalNumber": 3})

    print("Finished removing old ADM records.")