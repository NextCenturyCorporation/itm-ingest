def main(mongo_db):
    keep = [
        'What was the biggest influence on your delegation decision between different medics?',
        'As I was reading through the scenarios and Medic decisions, I actively thought about how I would handle the same situation',
        'I had enough information in this presentation to make the ratings for the questions asked on the previous pages about the DMs'
    ]

    survey_doc = mongo_db['delegationConfig'].find_one({'_id': 'delegation_v10.0'})
    pages = survey_doc['survey']['pages']
    page_index = next(i for i, p in enumerate(pages) if p['name'] == 'Post-Scenario Measures')
    
    filtered = [el for el in pages[page_index]['elements'] if any(el['name'].startswith(k) for k in keep)]
    
    mongo_db['delegationConfig'].update_one(
        {'_id': 'delegation_v10.0'},
        {'$set': {f'survey.pages.{page_index}.elements': filtered}}
    )