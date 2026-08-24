def main(mongo_db):
    june_configs = list(mongo_db['textBasedConfig'].find({
        'eval': 'Phase 2 June 2026 Evaluation'
    }))

    for config in june_configs:
        if 'trinary' in config['scenario_id']:
            continue
        del config['_id']
        config['eval'] = 'Phase 2 Canada Evaluation'

        for page in config['pages']:
            page['elements'][0]['probe_unstructured'] = page['elements'][0]['probe_unstructured'].replace('They are a US warfighter from a different branch of the military than you.', 'They are Canadian military from a different branch than you.')
            page['elements'][0]['probe_unstructured'] = page['elements'][0]['probe_unstructured'].replace('They are a warfighter in the same military unit as you.', 'They are Canadian military in the same unit as you.')
            page['elements'][0]['probe_unstructured'] = page['elements'][0]['probe_unstructured'].replace('They are a foreign civilian contractor who works for the US military, but not your unit.', 'They are a foreign civilian contractor who works for the Canadian military, but not your unit.')
            page['elements'][0]['probe_unstructured'] = page['elements'][0]['probe_unstructured'].replace('They are a warfighter in the same branch of the military as you, but not in the same unit.', 'They are Canadian military in the same branch as you, but not in the same unit.')
        mongo_db['textBasedConfig'].insert_one(config)
