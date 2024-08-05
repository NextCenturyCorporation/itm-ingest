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
    initial_characters = scenario['state'].get('characters', [])

    doc = {
        'scenario_id': scenario_id,
        'name': scenario['name'],
        'pages': []
    }

    scene_map = {scene.get('id', str(i)): scene for i, scene in enumerate(scenes)}
    processed_scenes = set()
    all_characters = initial_characters.copy()  # Start with initial characters

    def create_page(scene, previous_choices=None):
        page = {
            'name': scene.get('id') or scene['action_mapping'][0].get('probe_id', f"scene_{len(doc['pages'])}"),
            'scenario_id': scenario_id,
            'scenario_name': scenario['name'],
            'elements': []
        }

        if previous_choices:
            conditions = []
            for prev_scene, choice, next_scene in previous_choices:
                if next_scene == scene.get('id', ''):
                    conditions.append(f"{{probe {prev_scene}}} == '{choice}'")
            if conditions:
                page['visibleIf'] = " and ".join(conditions)

        unstructured = scene.get('state', {}).get('unstructured', starting_context)
        current_supplies = scene.get('state', {}).get('supplies', starting_supplies)
        
        scene_characters = get_scene_characters(scene)

        action_character_ids = set(action.get('character_id') for action in scene['action_mapping'] if 'character_id' in action)
        filtered_characters = [
            character for character in scene_characters
            if character['id'] in action_character_ids
        ]

        # Extract event information from probe_config
        event = None
        if 'probe_config' in scene and scene['probe_config']:
            event = scene['probe_config'][0].get('description')

        template_element = {
            'name': 'template ' + str(page['name']),
            'type': 'medicalScenario',
            'unstructured': unstructured,
            'supplies': current_supplies,
            'patients': filtered_characters,
            'events': [{'message': event}] if event else []  # Add event as a list item if it exists
        }
        page['elements'].append(template_element)

        choices = [
            {
                "value": action.get('choice', action.get('action_id', '')),
                "text": action['unstructured']
            } for action in scene['action_mapping']
        ]

        question_element = {
            'type': 'radiogroup',
            'choices': choices,
            'isRequired': True,
            'title': 'What action do you take?',
            'name': 'probe ' + str(page['name']),
            'probe_id': scene['action_mapping'][0]['probe_id']
        }
        page['elements'].append(question_element)

        return page

    def get_scene_characters(scene):
        nonlocal all_characters
        
        scene_characters = scene.get('state', {}).get('characters', [])
        
        if scene.get('persist_characters', False):
            char_dict = {char['id']: char for char in all_characters}
            for new_char in scene_characters:
                char_dict[new_char['id']] = new_char
            all_characters = list(char_dict.values())
        else:
            all_characters = scene_characters if scene_characters else initial_characters.copy()
        
        return all_characters

    def process_scene(scene_id, previous_choices=None):
        if scene_id in processed_scenes:
            return
        processed_scenes.add(scene_id)

        scene = scene_map[scene_id]
        if not scene['action_mapping']:
            return

        page = create_page(scene, previous_choices)
        doc['pages'].append(page)

        new_previous_choices = previous_choices or []

        for action in scene['action_mapping']:
            next_scene = action.get('next_scene')
            if next_scene:
                new_choices = new_previous_choices + [(page['name'], action.get('choice', action.get('action_id', '')), next_scene)]
                process_scene(next_scene, new_choices)

        if not any('next_scene' in action for action in scene['action_mapping']):
            current_index = scenes.index(scene)
            if current_index + 1 < len(scenes):
                next_scene_id = scenes[current_index + 1].get('id', str(current_index + 1))
                process_scene(next_scene_id, new_previous_choices)

    # Start with the first scene
    first_scene_id = scenario.get('first_scene') or next(iter(scene_map))
    process_scene(first_scene_id)

    doc = add_surveyjs_configs(doc)
    return doc

def upload_config(doc, textbased_mongo_collection):
    textbased_mongo_collection.insert_one(doc)

def main():
    client = MongoClient(config('MONGO_URL'))
    db = client.dashboard
    textbased_mongo_collection = db['textBasedConfig']

    current_dir = os.path.dirname(os.path.abspath(__file__))
    mre_folder = os.path.join(current_dir, 'mre-yaml-files')
    dre_folder = os.path.join(current_dir, 'dre-yaml-files')

    for folder, eval_type in [(mre_folder, 'mre'), (dre_folder, 'dre')]:
        if not os.path.exists(folder):
            print(f"Warning: {folder} does not exist.")
            continue

        for filename in os.listdir(folder):
            if filename.endswith('.yaml'):
                file_path = os.path.join(folder, filename)
                try:
                    with open(file_path, 'r') as file:
                        scenario = yaml.safe_load(file)
                    doc = partition_doc(scenario)
                    doc['eval'] = eval_type
                    upload_config(doc, textbased_mongo_collection)
                    print(f"Processed and uploaded: {filename}")
                except Exception as e:
                    print(f"Error processing {filename}: {str(e)}")

if __name__ == '__main__':
    main()