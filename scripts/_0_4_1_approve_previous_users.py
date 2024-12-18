'''
Marks all current users in the database as "approved"
'''

def main(mongo_db):
    user_collection = mongo_db['users']
    user_collection.update_many({}, {"$set": {'approved': True}})
