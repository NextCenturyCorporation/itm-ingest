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
        