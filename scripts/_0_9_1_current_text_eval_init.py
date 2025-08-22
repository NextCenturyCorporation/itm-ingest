def main(mongo_db):
    config_collection = mongo_db['surveyVersion']

    doc = config_collection.find_one({})

    config_collection.update_one(
        {'_id': doc['_id']},
        {
            '$set': {
                'lowPid': 202570100,
                'highPid': 202570299,
                'textScenarios': 'Phase 2 July 2025 Collaboration'
            }
        }
        )
