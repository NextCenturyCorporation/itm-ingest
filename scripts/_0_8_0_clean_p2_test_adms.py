'''
Removes test adms runs from database
'''
def main(mongo_db):
    adm_collec = mongo_db['admTargetRuns']
    
    delete_result = adm_collec.delete_many({
        "evalNumber": 8,
        "$or": [
            {"adm_name": {"$regex": "test", "$options": "i"}},  
            {"adm_name": {"$regex": "Random", "$options": "i"}},
            {"adm_name": {"$regex": "6d0829ad-4e3c-4a03-8f3d-472cc549888f"}}  
        ]
    })
    
    print(f"Deleted {delete_result.deleted_count} documents from admTargetRuns collection")