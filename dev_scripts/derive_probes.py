from pymongo import MongoClient
from decouple import config

def derive_probes(doc):
    if doc.get('probes'):
        return [p['probe_id'] for p in doc['probes']]
    return [h['parameters']['probe_id'] for h in doc.get('history', []) if h['command'] == 'Respond to TA1 Probe' and 'probe_id' in h['parameters']]

def main(mongo_db, write_to_db=True):
    updated = 0
    skipped = 0
    adm_collection = mongo_db['admTargetRuns']
    missing_filter = {'$or': [{'probe_ids': {'$exists': False}}, {'probe_ids': []}]}
    for doc in adm_collection.find(missing_filter):
        ids = derive_probes(doc)
        if not ids:
            skipped += 1
            continue
        if write_to_db:
            adm_collection.update_one({'_id': doc['_id']}, {'$set': {'probe_ids': ids}})
        updated += 1
    print(updated, skipped)    
    print(adm_collection.count_documents(missing_filter))    

if __name__ == '__main__':
    client = MongoClient(config('MONGO_URL'))
    main(client.dashboard)