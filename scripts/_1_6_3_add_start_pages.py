#I forgot to add the pid warning, pid entry, intro etc. pages to the canada survey
def main(mongo_db):
    v12_survey = mongo_db['delegationConfig'].find_one({'_id': 'delegation_v12.0'})

    intro_pages = v12_survey['survey']['pages'][:5]

    v13_survey = mongo_db['delegationConfig'].find_one({'_id': 'delegation_v13.0'})

    v13_survey['survey']['pages'][:0] = intro_pages

    mongo_db['delegationConfig'].replace_one(
        {'_id': 'delegation_v13.0'},
        v13_survey
    )