import os, json

excluded= [
    'What was the biggest influence on your delegation decision between different medics?',
    'As I was reading through the scenarios and Medic decisions, I actively thought about how I would handle the same situation',
    'I had enough information in this presentation to make the ratings for the questions asked on the previous pages about the DMs'
]

def main(mongo_db):
    text_configs = mongo_db['textBasedConfig']
    
    json_file_path = 'delegation_survey/survey-configs/postScenarioPhase2.json'
    with open(json_file_path, 'r') as file:
        measures = json.load(file)
    
    elements = []
    page = measures['pages'][0]
    for element in page['elements']:
        if element['name'] not in excluded:
            elements.append(element)

    updated_page = {
        'name': "Post-Scenario Measures",
        "elements": elements
    }

    doc = {
        'name': 'Post-Scenario Measures Phase 2',
        'pages': updated_page,
        'showQuestionNumbers': False,
        'showPrevButton': False,
        'title': 'Post-Scenario Measures Phase 2',
        'logoPosition': 'right',
        'completedHtml': '<h3>Thank you for completing the scenario</h3>',
        'widthMode': 'responsive',
    }

    text_configs.insert_one(doc)