import yaml
import os
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
        unstructured = starting_context if counter == 0 else scene['state']['unstructured']
        
        # template that contains supplies and character info 
        template_element = {
            'name': 'template ' + page['name'],
            'title': '',
            'type': 'medicalScenario',
            'unstructured': unstructured,
            'supplies': starting_supplies,
            'patients': scenario['state']['characters'] if counter == 0 else scene['state']['characters']
        }

        elements.append(template_element)

        # Gets the elements from the action mapping to create the possible actions for the user
        choices = []
        for action in scene['action_mapping']:
            choices.append(action['unstructured'])

        question_element = {
            'type': 'radiogroup',
            'choices': choices,
            'isRequired': True,
            'title': 'What action do you take?',
            'name': 'probe ' + page['name']
        }

        elements.append(question_element)

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

    mre_folder = 'mre-yaml-files'
    
    for filename in os.listdir(mre_folder):
        if filename.endswith('.yaml'):
            file_path = os.path.join(mre_folder, filename)
            with open(file_path, 'r') as file:
                scenario = yaml.safe_load(file)
                doc = partition_doc(scenario)
                doc['eval'] = 'mre'
                upload_config(doc, textbased_mongo_collection)
            print(f"Processed and uploaded: {filename}")

    dre_folder = 'dre-yaml-files'

    for filename in os.listdir(dre_folder):
        if filename.endswith('.yaml'):
            file_path = os.path.join(dre_folder, filename)
            with open(file_path, 'r') as file:
                scenario = yaml.safe_load(file)
                doc = partition_doc(scenario)
                doc['eval'] = 'dre'
                upload_config(doc, textbased_mongo_collection)
            print(f"Processed and uploaded: {filename}")

if __name__ == '__main__':
    main()
    