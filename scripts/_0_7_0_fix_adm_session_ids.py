def main(mongo_db):
    adms = mongo_db['admTargetRuns']
    eval5_adms = adms.find({'evalNumber': 5})
    for adm in eval5_adms:
        # get most up-to-date ta1 session id
        ta1_session_id = adm['history'][-1]['parameters']['session_id']
        history = adm['history']
        found = 0
        for x in history:
            if x['command'] == "TA1 Session ID":
                x['response'] = ta1_session_id
                found += 1
            if x['command'] == 'Alignment Target':
                x['parameters']['session_id'] = ta1_session_id
                found += 1
            if found == 2:
                break
        adms.update_one({'_id': adm['_id']}, {'$set': {'history': history}})

