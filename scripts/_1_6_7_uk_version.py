# modifies the canada text and delegation materials for the UK
lang_dict = {
    'They are a PW': 'They are a POW',
    'They are a Canadian civilian contractor who works for the Canadian military': 'They are a British civilian contractor who works for the British military.',
    'They are Canadian military from a different branch than you.': 'They are British military from a different branch than you.',
    'They are Canadian military in the same unit as you.': 'They are British military in the same unit as you.',
    'They are a foreign civilian contractor who works for the Canadian military, but not your unit.': 'They are a foreign civilian contractor who works for the British military, but not your unit.',
    'They are Canadian military in the same branch as you, but not in the same unit.': 'They are British military in the same branch as you, but not in the same unit.',
}

def main(mongo_db):
    text_configs = list(mongo_db['textBasedConfig'].find({'eval': 'Phase 2 Canada Evaluation'}))

    for config in text_configs: 
        del config['_id']
        config['eval'] = 'Phase 2 UK Evaluation'
        for page in config['pages']:
            for old_text, new_text in lang_dict.items():
                page['elements'][0]['probe_unstructured'] = page['elements'][0]['probe_unstructured'].replace(old_text, new_text)
        mongo_db['textBasedConfig'].insert_one(config)

    survey = mongo_db['delegationConfig'].find_one({'_id': 'delegation_v13.0'})
    survey['_id'] = 'delegation_v14.0'
    survey['survey']['version'] = 14
    for page in survey['survey']['pages']:
        page['evalNumber'] = 19
        rows = page['elements'][0].get('rows')
        if rows is None:
            continue
        for row in rows:
            for old_text, new_text in lang_dict.items():
                row['probe_unstructured'] = row['probe_unstructured'].replace(old_text, new_text)

    mongo_db['delegationConfig'].insert_one(survey)