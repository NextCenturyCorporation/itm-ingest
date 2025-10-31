def main(mongo_db):
    survey_config_collection = mongo_db['delegationConfig']
    config = survey_config_collection.find_one({'_id': 'delegation_v9.0'})
    medic_target_map = {}
    for x in config['survey']['pages']:
        if 'Medic-' in x['name']:
            medic_target_map[x['name']] = x['admAlignment']


    survey_results_collection = mongo_db['surveyResults']
    eval12_results = survey_results_collection.find({'results.evalNumber': 12})
    for survey in eval12_results:
        res = survey.get('results', {})
        survey_id = survey['_id']
        for page_name in res.keys():
            if 'vs' in page_name or 'Medic' not in page_name:
                continue
            res[page_name]['admTarget'] = medic_target_map[page_name]
        survey_results_collection.update_one({'_id': survey_id}, {'$set': {'results': res}})