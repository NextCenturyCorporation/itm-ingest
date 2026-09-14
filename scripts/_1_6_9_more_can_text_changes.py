lang_dict = {
    'patrolling dismounted': 'dismounted patrolling'
}

def main(mongo_db):
    text_configs = list(mongo_db['textBasedConfig'].find({'eval': 'Phase 2 Canada Evaluation'}))
    survey = mongo_db['delegationConfig'].find_one({'_id': 'delegation_v13.0'})

    for config in text_configs:
        for page in config['pages']:
            for old_text, new_text in lang_dict.items():
                page['elements'][0]['probe_unstructured'] = page['elements'][0]['probe_unstructured'].replace(old_text, new_text)
        mongo_db['textBasedConfig'].update_one(
            {'_id': config['_id']},
            {'$set': {'pages': config['pages']}}
        )

    for page in survey['survey']['pages']:
        rows = page['elements'][0].get('rows')
        if rows is None:
            continue
        for row in rows:
            for old_text, new_text in lang_dict.items():
                row['probe_unstructured'] = row['probe_unstructured'].replace(old_text, new_text)
    mongo_db['delegationConfig'].update_one(
        {'_id': survey['_id']},
        {'$set': {'survey.pages': survey['survey']['pages']}}
    )