from ph2_repop import main as ph2_repop
from datetime import datetime

def main(mongo_db):
    adm_runs = mongo_db['admTargetRuns']

    adm_runs.update_many(
        {'evalNumber': 8, 'adm_name': {'$regex': '__'}},
        [{'$set': {'adm_name': {'$arrayElemAt': [{'$split': ['$adm_name', '__']}, 0]}}}]
    )
    
    documents = adm_runs.find({'evalNumber': 8})
    
    for doc in documents:
        current_name = doc.get('adm_name', '')
        start_time_str = doc.get('evaluation', {}).get('start_time', '')
        
        if start_time_str and start_time_str.strip() and start_time_str != '-':
            dt = datetime.strptime(start_time_str.split('.')[0], "%Y-%m-%d %H:%M:%S")
            new_name = f"{current_name}_{dt.month}_{dt.day}"
            
            adm_runs.update_one(
                {'_id': doc['_id']},
                {'$set': {'adm_name': new_name}}
            )
    
    
    # repopulate ta1 server
    ph2_repop(mongo_db)