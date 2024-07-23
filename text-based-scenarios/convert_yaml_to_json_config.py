import yaml
from decouple import config 
from pymongo import MongoClient

def add_surveyjs_configs(doc):
    doc['showQuestionNumbers'] = False
    doc['showPrevButton'] = False
    doc['title'] = doc['scenario_id']
    doc['logoPosition'] = 'right'
    doc['completedHtml'] = '<h3>Thank you for completing the scenario</h3>'
    doc['widthMode'] = 'responsive'
    doc['showProgressBar'] = 'top'

    return doc

def partition_doc(scenario):
    scenario_id = scenario['id']
    scenes = scenario['scenes']
    starting_context = scenario['state']['unstructured']
    starting_supplies = scenario['state']['supplies']

    doc = {}

    doc['scenario_id'] = scenario_id
    doc['name'] = scenario['name']
    doc['pages'] = []

    counter = 0
    for scene in scenes:
        # skip over dummy scene 
        if len(scene['action_mapping']) <= 0:
            continue
        page = {}
        elements = []
        page['name'] = scene['action_mapping'][0]['probe_id']
        
        # context for probe
        context = None
        if counter == 0:
            context = starting_context
        else:
            context = scene['state']['unstructured']
        
        if context:
            question = {
                'name': 'context ' + page['name'],
                'type': 'expression',
                'description': context
            }

            elements.append(question)
        page['elements'] = elements
        doc['pages'].append(page)
        counter += 1

    # SURVEY JS CONFIGS
    doc = add_surveyjs_configs(doc)

    return doc

def upload_config(doc, textbased_mongo_collection):
    textbased_mongo_collection.insert_one(doc)

def main():
    client = MongoClient(config('MONGO_URL'))
    db = client.dashboard
    textbased_mongo_collection = db['textBasedConfig']

    with open('desert.yaml', 'r') as file:
        scenario = yaml.safe_load(file)

    doc = partition_doc(scenario)

    upload_config(doc, textbased_mongo_collection)

if __name__ == '__main__':
    main()
    