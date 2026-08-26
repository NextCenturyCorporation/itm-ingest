def main(mongo_db):
    survey_12 = mongo_db['delegationConfig'].find_one({'_id': 'delegation_v12.0'})
    survey_10 = mongo_db['delegationConfig'].find_one({'_id': 'delegation_v10.0'})

    new_pages = []

    for page in survey_12['survey']['pages']:
        scenario = page.get('scenarioIndex', '')
        adm = page.get('admName', '')

        if scenario == '' or adm == '': continue

        if scenario == 'June2026-PS-observe' or scenario == 'June2026-AF-observe':
            new_pages.append(page)

    for page in survey_10['survey']['pages']:
        scenario = page.get('scenarioIndex', '')
        adm = page.get('admName', '')
        
        if scenario == '' or adm == '': continue

        if scenario == 'Feb2026-MF3-observe':
            new_pages.append(page)

        if scenario == 'Feb2026-MF-SS1-observe' and '' in adm:
            new_pages.append(page)

        if scenario == 'Feb2026-AF-PS1-observe' and 'DirectRegression' in adm:
            new_pages.append(page)