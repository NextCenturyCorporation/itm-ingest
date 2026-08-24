def main(mongo_db):
    june_configs = list(mongo_db['textBasedConfig'].find({
        'eval': 'Phase 2 June 2026 Evaluation'
    }))

    for config in june_configs:
        if 'trinary' in config['scenario_id']:
            continue
        del config['_id']
        config['eval'] = 'Phase 2 Canada Evaluation'
        mongo_db['textBasedConfig'].insert_one(config)
