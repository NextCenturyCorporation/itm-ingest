from datetime import datetime
def main(mongo_db):
    adm_runs = mongo_db['admTargetRuns']
    bad_boys = [
            'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-DeepSeek-R1-Distill-Llama-8B__07e67dd0-79b8-48bf-823b-939ca04d9574',
            'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-DeepSeek-R1-Distill-Llama-8B__34052bf2-c99e-4528-9acc-5ec1e3c7fa59'
        ]

    adm_runs.update_many(
        {
            "evalNumber": 17,
            "adm_name": {"$in": bad_boys},
        },
        {
            "$set": {
                "adm_name": "ALIGN-ADM-Ph2-DirectRegression-Mistral-7B-Instruct-v0.3",
                "evaluation.adm_name": "ALIGN-ADM-Ph2-DirectRegression-Mistral-7B-Instruct-v0.3",
            }
        },
    )

    # get rid of junk run
    adm_runs.delete_many(
        {'evalNumber': 17, 'adm_name': {'$regex': 'Random', '$options': 'i'}}
    )

    # strip UUID
    adm_runs.update_many(
        {"evalNumber": 17},
        [{'$set': {'adm_name': {'$arrayElemAt': [{'$split': ['$adm_name', '__']}, 0]}}}]
    )

    documents = adm_runs.find({'evalNumber': {'$gte': 17}})

    for doc in documents:
        current_name = doc.get('adm_name', '')
        start_time_str = doc.get('evaluation', {}).get('start_time', '')

        if start_time_str and start_time_str.strip() and start_time_str != '-':
            dt = datetime.strptime(start_time_str.split('.')[0], "%Y-%m-%d %H:%M:%S")
            expected_token = f"_{dt.month}_{dt.day}"

            base_name = current_name
            token_len = len(expected_token)
            while token_len > 0 and base_name.endswith(expected_token):
                base_name = base_name[:-token_len]

            new_name = f"{base_name}{expected_token}"

            if new_name != current_name:
                adm_runs.update_one(
                    {'_id': doc['_id']},
                    {'$set': {'adm_name': new_name}}
                )
