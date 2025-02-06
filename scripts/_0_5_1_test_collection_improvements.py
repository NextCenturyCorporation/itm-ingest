def main(mongo_db):
    test_collection = mongo_db['test']
    tests = test_collection.find({})
    updated_count = 0
    for test in tests:
        # anything before mre is irrelevant, mre is probably irrelevant as well but follows same structure so why not
        if test['evalNumber'] < 3:
            continue
        adm_name = None
        scenario = None
        alignment_target = None
        history = test['history']
        for el in history:
            if el['command'] == 'Start Scenario':
                adm_name = el['parameters']['adm_name']
                scenario = el['response']['id']
            if el['command'] == 'Alignment Target':
                alignment_target = el['response']['id']
            
            if all([adm_name, scenario, alignment_target]):
                test_collection.update_one(
                    {'_id': test['_id']},
                    {'$set': {
                        'adm_name': adm_name,
                        'scenario': scenario,
                        'alignment_target': alignment_target
                    }}
                )
                updated_count += 1
                break
    print(f"Updated {updated_count} documents")