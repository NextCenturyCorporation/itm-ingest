def main(mongo_db):
    adm_collection = mongo_db['admTargetRuns']
    RENAME_ADM = [
        {'old_name': 'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-DeepSeek-R1-Distill-Llama-8B__027f85b6-f3d7-457d-a9db-8c518b34a00b',
         'new_name': 'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-Mistral-7B-Instruct-v0.3__027f85b6-f3d7-457d-a9db-8c518b34a00b'},
        {'old_name': 'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-DeepSeek-R1-Distill-Llama-8B__68fa949a-697c-4179-94f0-0a67dce8d234',
         'new_name': 'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-Mistral-7B-Instruct-v0.3__68fa949a-697c-4179-94f0-0a67dce8d234'},
        {'old_name': 'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-DeepSeek-R1-Distill-Llama-8B__8782bd97-7e37-4ffd-97df-b0754328c137',
         'new_name': 'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-Mistral-7B-Instruct-v0.3__8782bd97-7e37-4ffd-97df-b0754328c137'}
    ]

    for pair in RENAME_ADM:
        query = {'$or': [
            {'adm_name': pair['old_name']},
            {'evaluation.adm_name': pair['old_name']}
        ]}
        n = adm_collection.count_documents(query)
        result = adm_collection.update_many(query, {'$set': {
            'adm_name': pair['new_name'],
            'evaluation.adm_name': pair['new_name']
        }})
        print(f"{pair['old_name']}: matched {n}, modified {result.modified_count}")