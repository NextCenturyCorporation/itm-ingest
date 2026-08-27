
land_dict = {
    'They are a US warfighter from a different branch of the military than you.': 'They are Canadian military from a different branch than you.',
    'They are a warfighter in the same military unit as you.': 'They are Canadian military in the same unit as you.',
    'They are a foreign civilian contractor who works for the US military, but not your unit.': 'They are a foreign civilian contractor who works for the Canadian military, but not your unit.',
    'They are a warfighter in the same branch of the military as you, but not in the same unit.': 'They are Canadian military in the same branch as you, but not in the same unit.'
}


def main(mongo_db):
    survey_12 = mongo_db['delegationConfig'].find_one({'_id': 'delegation_v12.0'})
    survey_10 = mongo_db['delegationConfig'].find_one({'_id': 'delegation_v10.0'})

    new_pages = []

    #grab june 2026 pages
    for page in survey_12['survey']['pages']:
        scenario = page.get('scenarioIndex', '')
        adm = page.get('admName', '')

        if scenario == '' or adm == '': continue

        if scenario == 'June2026-PS-observe' or scenario == 'June2026-AF-observe':
            new_pages.append(page)

    #grab feb 2026 pages
    for page in survey_10['survey']['pages']:
        scenario = page.get('scenarioIndex', '')
        adm = page.get('admName', '')
        
        if scenario == '' or adm == '': continue

        if scenario == 'Feb2026-MF3-observe':
            new_pages.append(page)

        if scenario == 'Feb2026-MF-SS1-observe' and 'Mistral' in adm:
            new_pages.append(page)

        if scenario == 'Feb2026-AF-PS1-observe' and 'Mistral' in adm:
            new_pages.append(page)

    #update eval num and change text as needed
    for page in new_pages:
        page['evalNumber'] = 18
        for row in page['elements'][0]['rows']:
            for old_text, new_text in land_dict.items():
                row['probe_unstructured'] = row['probe_unstructured'].replace(old_text, new_text)


    survey_config_doc = {
        'title': 'ITM Delegation Survey',
        'logoPosition': 'right',
        'version': 13,
        'completedHtml': '<h3>Thank you for completing the survey</h3>',
        'pages': new_pages,
        'widthMode': 'responsive',
        'showTitle': False,
        'showQuestionNumbers': False,
        'showProgressBar': 'top'
    }

    mongo_db['delegationConfig'].insert_one({
        '_id': 'delegation_v13.0',
        'survey': survey_config_doc
    })