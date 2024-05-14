def fix_survey_results_table(mongoDB):
    survey_results_collection = mongoDB['surveyResults']
    survey_results = survey_results_collection.find({})

    for result in survey_results:
        if ('results' not in result or 'surveyVersion' not in result['results'] or result['results']['surveyVersion'] != 2):
            continue
        pages = result['results']
        if 'Participant ID Page' in pages:
            intro_page = pages['Participant ID Page']['questions']
            if 'Condition' in intro_page:
                intro_page['VR Scenarios Completed'] = intro_page.pop('Condition')

                survey_results_collection.update_one(
                    {'_id': result['_id']},
                    {'$set': {'results.Participant ID Page.questions': intro_page}}
                )
        if 'Post-Scenario Measures' in pages:
            exit_questions = pages['Post-Scenario Measures']['questions']
            if 'What is your current role (choose all that apply):' in exit_questions:
                if 'response' in exit_questions['What is your current role (choose all that apply):']:
                    target = "Military Background (Branch, level of training, Active/Retired, etc)"
                    replacement = "Military Background"
                    response = exit_questions['What is your current role (choose all that apply):']['response']
                    if isinstance(response, list):
                        response = [replacement if i == target else i for i in response]
                        exit_questions['What is your current role (choose all that apply):']['response'] = response
                    
                    survey_results_collection.update_one(
                        {'_id': result['_id']},
                        {'$set': {'results.Post-Scenario Measures.questions': exit_questions}}
                    )
                    
