
import copy, re
def main(mongo_db):
    delegation_adms = mongo_db['delegationADMRuns']
    admMedics = mongo_db['admMedics']
    delegation_config = mongo_db['delegationConfig']
    survey_v5 = delegation_config.find_one({'_id': 'delegation_v5.0'})
    
    # only using MJ2, IO2, VOL3 (VOL2 used in text and there was no VOL1 for phase 1)
    # ADEPT scenarios paired with Kitware, ST paired with Parralax
    valid_scenarios = {'DryRunEval-MJ2-eval', 'vol-ph1-eval-3', 'DryRunEval-IO2-eval'}
    match_adm_delegation = {
        '$match': {
            'evalNumber': 5,
            'scenario': {'$in': list(valid_scenarios)},
            'ph1_in_dre_server_run': {'$exists': False},
            '$or': [
                {'scenario': {'$regex': '^DryRunEval'}, 'adm_name': {'$regex': 'ALIGN'}},
                {'scenario': 'vol-ph1-eval-3', 'adm_name': {'$regex': 'TAD'}}
            ]
        }
    }
    
    match_adm_medics = {
        '$match': {
            'evalNumber': 5,
            'scenarioIndex': {'$in': list(valid_scenarios)},
            '$or': [
                {'scenarioIndex': {'$regex': '^DryRunEval'}, 'admName': {'$regex': 'ALIGN'}},
                {'scenarioIndex': 'vol-ph1-eval-3', 'admName': {'$regex': 'TAD'}}
            ]
        }
    }

    pipeline = [
        match_adm_delegation,
        {'$set': {'evalNumber': 12}},
        {'$unset': '_id'},
        {'$merge': {'into': 'delegationADMRuns'}}
    ]
    delegation_adms.aggregate(pipeline)
    
    pipeline = [
        match_adm_medics,
        {'$set': {'evalNumber': 12}},
        {'$unset': '_id'},
        {'$merge': {'into': 'admMedics'}}
    ]
    admMedics.aggregate(pipeline)

    new_survey = {'survey': {}}
    # adding new survey
    old_pages = survey_v5['survey']['pages']
    new_pages = []

    for page in old_pages:
        # starter pages
        if 'scenarioIndex' not in page:
            new_pages.append(page)
        # only keep necessary pages
        elif page['scenarioIndex'] in valid_scenarios:
            adm_name = page.get('admName', '')
            scenario = page['scenarioIndex']
            
            if (scenario.startswith('DryRunEval') and 'ALIGN' in adm_name) or \
               (scenario == 'vol-ph1-eval-3' and 'TAD' in adm_name):
                new_page = copy.deepcopy(page)
                
                first_element = new_page['elements'][0]
                first_element['situation'] = first_element['situation'].replace('Blackhawk', 'helicopter')
                first_element['situation'] = re.sub(r'\bUS\b', 'British', first_element['situation'])
                first_element['mission']['unstructured'] = re.sub(r'\bUS\b', 'British', first_element['mission']['unstructured'])
                first_element['mission']['unstructured'] = first_element['mission']['unstructured'].replace('Blackhawk', 'helicopter')
                first_element['actions'] = [
                    re.sub(r'\bUS\b', 'British', action) 
                    for action in first_element['actions']
                ]
                # go through all scenes
                if 'scenes' in first_element and isinstance(first_element['scenes'], list):
                    for scene in first_element['scenes']:
                        if 'actions' in scene and isinstance(scene['actions'], list):
                            for action_obj in scene['actions']:
                                if isinstance(action_obj, dict) and 'text' in action_obj:
                                    action_obj['text'] = re.sub(r'\bUS\b', 'British', action_obj['text'])
                new_pages.append(new_page)


    new_survey['survey']['pages'] = new_pages
    new_survey['_id'] = 'delegation_v9.0'
    new_survey['survey']['title'] = 'ITM Delegation Survey'
    new_survey['survey']['logoPosition'] = 'right'
    new_survey['survey']['version'] = 9
    new_survey['survey']['completedHtml'] = '<h3>Thank you for completing the survey</h3>'
    new_survey['survey']['widthMode'] = 'responsive'
    new_survey['survey']['showTitle'] = False
    new_survey['survey']['showQuestionNumbers'] = False
    new_survey['survey']['showProgressBar'] = 'top'

    delegation_config.insert_one(new_survey)