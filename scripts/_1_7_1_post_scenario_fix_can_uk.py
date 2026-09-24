def main(mongo_db):
    canada = mongo_db['delegationConfig'].find_one({
        '_id': 'delegation_v13.0'
    })

    uk = mongo_db['delegationConfig'].find_one({
        '_id': 'delegation_v14.0'
    })

    v12 = mongo_db['delegationConfig'].find_one({
        '_id': 'delegation_v12.0'
    })

    pages = v12['survey']['pages']
    post_scenario = next((x for x in pages if 'Post-Scenario Measures' in x['name']), None)

    canada['survey']['pages'].append(post_scenario)
    uk['survey']['pages'].append(post_scenario)

    mongo_db['delegationConfig'].update_one(
        {'_id': 'delegation_v13.0'},
        {'$set': {'survey.pages': canada['survey']['pages']}}
    )
    mongo_db['delegationConfig'].update_one(
        {'_id': 'delegation_v14.0'},
        {'$set': {'survey.pages': uk['survey']['pages']}}
    )