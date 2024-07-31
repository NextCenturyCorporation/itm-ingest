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

    scene_map = {scene.get('id', str(i)): scene for i, scene in enumerate(scenes)}
    processed_scenes = set()

    def create_page(scene, previous_choices=None):
        page = {}
        elements = []
        probe_id = scene['action_mapping'][0]['probe_id']
        page['name'] = probe_id

        if previous_choices:
            conditions = []
            for prev_probe, choice, next_scene in previous_choices:
                if next_scene == scene.get('id', ''):
                    conditions.append(f"{{probe {prev_probe}}} == '{choice}'")
            if conditions:
                page['visibleIf'] = " or ".join(conditions)

        unstructured = scene.get('state', {}).get('unstructured', starting_context)
        
        # Filter characters based on action_mapping
        action_character_ids = set(action['character_id'] for action in scene['action_mapping'] if 'character_id' in action)
        filtered_characters = [
            character for character in scene.get('state', {}).get('characters', scenario['state']['characters'])
            if character['id'] in action_character_ids
        ]

        template_element = {
            'name': 'template ' + probe_id,
            'title': '',
            'type': 'medicalScenario',
            'unstructured': unstructured,
            'supplies': starting_supplies,
            'patients': filtered_characters
        }

        elements.append(template_element)

        choices = []
        for action in scene['action_mapping']:
            choices.append(action['unstructured'])

        question_element = {
            'type': 'radiogroup',
            'choices': choices,
            'isRequired': True,
            'title': 'What action do you take?',
            'name': 'probe ' + probe_id
        }

        elements.append(question_element)

        page['elements'] = elements
        return page

    def process_scene(scene_id, previous_choices=None):
        if scene_id in processed_scenes:
            return
        processed_scenes.add(scene_id)

        scene = scene_map[scene_id]
        page = create_page(scene, previous_choices)
        doc['pages'].append(page)

        new_previous_choices = previous_choices or []
        for action in scene['action_mapping']:
            if 'next_scene' in action:
                new_choices = new_previous_choices + [(scene['action_mapping'][0]['probe_id'], action['unstructured'], action['next_scene'])]
                process_scene(action['next_scene'], new_choices)

    # Start with the first scene
    process_scene(next(iter(scene_map)))

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
    