def main(mongo_db):
    text_based_configs = mongo_db['textBasedConfig'].find({'eval': 'Phase 2 July 2025 Collaboration'})

    for config in text_based_configs:
        del config['_id']
        config['eval'] = 'Phase 2 October 2025 Collaboration'
        mongo_db['textBasedConfig'].insert_one(config)