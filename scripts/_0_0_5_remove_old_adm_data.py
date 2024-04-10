def remove_old_adm_records(mongoDB):
    adm_collection = mongoDB['test']
    adm_collection.delete_many({"evalNumber": 3})

    print("Finished removing old ADM records.")