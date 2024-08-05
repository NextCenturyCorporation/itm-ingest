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
            'name': scene['action_mapping'][0]['probe_id'],
            'scenario_id': scenario_id,
            'elements': []
        }

        if previous_choices:
            conditions = []
            for prev_probe, choice, next_scene in previous_choices:
                if next_scene == scene.get('id', ''):
                    conditions.append(f"{{probe {prev_probe}}} == '{choice}'")
            if conditions:
                page['visibleIf'] = " and ".join(conditions)

        unstructured = scene.get('state', {}).get('unstructured', starting_context)
        current_supplies = scene.get('state', {}).get('supplies', starting_supplies)
        
        # Get characters for this scene
        scene_characters = get_scene_characters(scene)

        # Filter characters based on action_mapping
        action_character_ids = set(action['character_id'] for action in scene['action_mapping'] if 'character_id' in action)
        filtered_characters = [
            character for character in scene_characters
            if character['id'] in action_character_ids
        ]

        template_element = {
            'name': 'template ' + page['name'],
            'type': 'medicalScenario',
            'unstructured': unstructured,
            'supplies': current_supplies,
            'patients': filtered_characters
        }
        page['elements'].append(template_element)

        choices = [
            {
                "value": {'action': action['unstructured'], 'probe_id': action['probe_id'], 'choice': action['choice']},
                "text": action['unstructured']
            } for action in scene['action_mapping']
        ]

        question_element = {
            'type': 'radiogroup',
            'choices': choices,
            'isRequired': True,
            'title': 'What action do you take?',
            'name': 'probe ' + page['name']
        }
        page['elements'].append(question_element)

        return page

    def get_scene_characters(scene):
        nonlocal all_characters
        
        scene_characters = scene.get('state', {}).get('characters', [])
        
        if scene.get('persist_characters', False):
            # Create a dictionary of characters by ID for easy lookup and update
            char_dict = {char['id']: char for char in all_characters}
            
            # Update or add new characters
            for new_char in scene_characters:
                char_dict[new_char['id']] = new_char
            
            # Convert back to list
            all_characters = list(char_dict.values())
        else:
            # If persist_characters is false, use only the characters defined in this scene
            # If no characters are defined, fall back to initial characters
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

        # Process next scenes based on action_mapping
        for action in scene['action_mapping']:
            if 'next_scene' in action:
                new_choices = new_previous_choices + [(scene['action_mapping'][0]['probe_id'], action['choice'], action['next_scene'])]
                process_scene(action['next_scene'], new_choices)

        # If no next_scene is specified, move to the next sequential scene
        if not any('next_scene' in action for action in scene['action_mapping']):
            current_index = scenes.index(scene)
            if current_index + 1 < len(scenes):
                next_scene_id = scenes[current_index + 1].get('id', str(current_index + 1))
                process_scene(next_scene_id, new_previous_choices)

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