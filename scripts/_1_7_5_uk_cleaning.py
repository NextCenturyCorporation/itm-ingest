from bson import ObjectId
def main(mongo_db):
    garbage = [ObjectId('6acf99c7f36fd6aacc67ff11'), ObjectId('6ad5f94030757b5281f9db6a')]

    result = mongo_db['surveyResults'].delete_many({'_id': {'$in': garbage}})
    print(f"Deleted {result.deleted_count} documents.")