from bson import ObjectId
def main(mongo_db):
    to_remove = ['6a3ac97162f0ee4fb635f453', '6a3ac97162f0eef84a35f450', '6a3ac8c262f0ee51c335f44a',
                 '6a3ac8c262f0ee185335f448', '6a3ac8c262f0ee5e3035f446', '6a3ac8c262f0ee304935f444']
    
    text_scenario_collection = mongo_db['userScenarioResults']

    result = text_scenario_collection.delete_many({
        '_id': {'$in': [ObjectId(id) for id in to_remove]}
    })

    print(f"Deleted {result.deleted_count} spurious text documents")
