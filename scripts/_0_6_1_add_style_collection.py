def main(mongo_db):
    ui_collection = mongo_db['uiStyle']
    ui_collection.insert_one({'version': 'updated'})