

def add_scenario_names(mongoDB):
    survey_results_collection = mongoDB['surveyResults']
    survey_results = survey_results_collection.find({})

    index_map = {
        1: 'SoarTech Submarine',
        2: 'SoarTech Jungle',
        3: 'SoarTech Desert',
        4: 'SoarTech Urban',
        5: 'Adept Submarine',
        6: 'Adept Jungle',
        7: 'Adept Desert',
        8: 'Adept Urban',
        9: 'SoarTech Omnibus',
        10: 'Adept Omnibus'
    }

    for result in survey_results:
        if ('results' not in result or 'surveyVersion' not in result['results'] or result['results']['surveyVersion'] != 2):
            continue
        
        # all pages with scenarioIndex field
        pages = [page for page in result['results'].values() if isinstance(page, dict) and 'scenarioIndex' in page]
        for page in pages:
            scenario_index = page['scenarioIndex']
            if scenario_index in index_map:
                page['scenarioName'] = index_map[scenario_index]
                # add field to existing omnibus results for surveyResults page
                if scenario_index in (9, 10):
                    page['pageType'] = 'singleMedic'
                

        survey_results_collection.update_one(
                {'_id': result['_id']},
                {'$set': result}
            )
    print("Scenario names added, omnibus pages updated")


    