from datetime import datetime

def main(mongo_db):
    adm_runs = mongo_db['admTargetRuns']

    adm_runs.update_many(
        {'evalNumber': {'$gte': 8}, 'adm_name': {'$regex': '__'}},
        [{'$set': {'adm_name': {'$arrayElemAt': [{'$split': ['$adm_name', '__']}, 0]}}}]
    )

    documents = adm_runs.find({'evalNumber': {'$gte': 8}})

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
