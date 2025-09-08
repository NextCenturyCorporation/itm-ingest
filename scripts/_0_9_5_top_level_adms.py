'''
One-time run to move adm_name, alignment_target, and scenario to the 
top level of evals 1 and 2 (MVP and September Milestone) in admTargetRuns.

Also removes duplicate scenarios from the scenarios collection for evals 1 and 2
'''

def main(mongo_db):
    query_to_update = {'evalNumber': {'$in': [1, 2]}}

    adm_collection = mongo_db['admTargetRuns']
    adms = adm_collection.find(query_to_update)
    updated = 0
    for adm in adms:
        last_elem = adm['history'][-1]
        alignment = last_elem['response']['alignment_source']
        if 'scenario_id' in alignment:
            scenario = alignment['scenario_id']
        else:
            scenario = alignment[0]['scenario_id']
        target = last_elem['response']['alignment_target_id']
        adm_name = adm['history'][0]['parameters']['ADM Name']

        updates = {
            'adm_name': adm_name,
            'alignment_target': target,
            'scenario': scenario
        }

        adm_collection.update_one({'_id': adm['_id']}, {'$set': updates})
        updated += 1
    print(f'Updated {updated} adms in admTargetRuns')

    scenario_collection = mongo_db['scenarios']
    scenarios = scenario_collection.find(query_to_update)
    found = []
    deleted = 0
    for scenario in scenarios:
        if scenario['id'] in found:
            scenario_collection.delete_one({'_id': scenario['_id']})
            deleted += 1
        else:
            found.append(scenario['id'])
    print(f'Deleted {deleted} duplicate scenarios')
