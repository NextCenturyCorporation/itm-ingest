remove_adm = 'ALIGN-ADM-RelevanceComparativeRegression-ADEPT__4e570b6d-8f9e-4e3c-8d0f-ffcde73a5792'
relevance = 'ALIGN-ADM-RelevanceComparativeRegression-ADEPT'
comparative = 'ALIGN-ADM-ComparativeRegression-ADEPT'
def main(mongo_db):
    adm_collection = mongo_db['admTargetRuns']
    eval_7_adms = adm_collection.find({'evalNumber': 7})

    for adm in eval_7_adms:
        if adm['adm_name'] == remove_adm:
            # remove the extra adm results from mj2
            adm_collection.delete_one({'_id': adm['_id']})
            continue
        # remove the uuid portion of the adm names
        elif relevance in adm['adm_name']:
            adm_collection.update_one(
                {'_id': adm['_id']},
                {'$set': {'adm_name': relevance}}
            )
        elif comparative in adm['adm_name']:
            adm_collection.update_one(
                {'_id': adm['_id']},
                {'$set': {'adm_name': comparative}}
            )
        
        # go through history and clean adm names
        for i, history_entry in enumerate(adm['history']):
                if 'parameters' in history_entry and 'adm_name' in history_entry['parameters']:
                    param_adm_name = history_entry['parameters']['adm_name']
                    if relevance in param_adm_name:
                        update_field = f'history.{i}.parameters.adm_name'
                        adm_collection.update_one(
                            {'_id': adm['_id']},
                            {'$set': {update_field: relevance}}
                        )
                    elif comparative in param_adm_name:
                        update_field = f'history.{i}.parameters.adm_name'
                        adm_collection.update_one(
                            {'_id': adm['_id']},
                            {'$set': {update_field: comparative}}
                        )
    multi_kdma_collect = mongo_db['multiKdmaData']
    multi_kdma_collect.delete_many({'admName': remove_adm})
    multi_kdma_docs = multi_kdma_collect.find({})
    for doc in multi_kdma_docs:
        if 'admName' in doc:
            if relevance in doc['admName']:
                multi_kdma_collect.update_one(
                    {'_id': doc['_id']},
                    {'$set': {'admName': relevance}}
                )
            elif comparative in doc['admName']:
                multi_kdma_collect.update_one(
                    {'_id': doc['_id']},
                    {'$set': {'admName': comparative}}
                )
        