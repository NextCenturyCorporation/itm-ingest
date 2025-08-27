from ph2_repop import main as ph2_repop

def main(mongo_db):
    adm_runs = mongo_db['admTargetRuns']

    adm_runs.update_many(
        {'evalNumber': 8, 'adm_name': {'$regex': '__'}},
        [{'$set': {'adm_name': {'$arrayElemAt': [{'$split': ['$adm_name', '__']}, 0]}}}]
    )
        
    # repopulate ta1 server
    ph2_repop(mongo_db)
