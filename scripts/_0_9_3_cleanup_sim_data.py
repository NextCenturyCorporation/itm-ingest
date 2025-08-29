def main(mongo_db):
    sim_collection = mongo_db['humanSimulator']

    sim_collection.delete_many({'scenario_id': 'eval_open_world', 'evalNumber': {'$in': [8, 9]}})