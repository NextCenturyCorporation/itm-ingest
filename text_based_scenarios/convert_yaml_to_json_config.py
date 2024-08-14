import yaml
import os
import json
from collections import OrderedDict
from decouple import config 
from pymongo import MongoClient
import difflib

def add_surveyjs_configs(doc):
    doc['showQuestionNumbers'] = False
    doc['showPrevButton'] = False
    doc['title'] = doc['scenario_id']
    doc['logoPosition'] = 'right'
    doc['completedHtml'] = '<h3>Thank you for completing the scenario</h3>'
    doc['widthMode'] = 'responsive'
    doc['showProgressBar'] = 'top'
    return doc

def get_text_difference(old_text, new_text):
    # Find the difference between old_text and new_text.
    differ = difflib.Differ()
    diff = list(differ.compare(old_text.splitlines(), new_text.splitlines()))
    new_lines = [line[2:] for line in diff if line.startswith('+ ')]
    return '\n'.join(new_lines)

def partition_doc(scenario):
    scenario_id = scenario['id']
    scenes = scenario['scenes']
    starting_context = scenario['state']['unstructured']
    starting_supplies = scenario['state']['supplies']
    initial_characters = scenario['state'].get('characters', [])
    initial_events = scenario['state'].get('events', [])

    doc = {
        'scenario_id': scenario_id,
        'name': scenario['name'],
        'pages': []
    }

    for i, scene in enumerate(scenes):
        if 'id' not in scene:
            scene['id'] = f"scene_{i+1}"

    scene_map = OrderedDict((scene['id'], scene) for scene in scenes)
    processed_scenes = set()
    all_characters = initial_characters.copy()
    scene_conditions = {}
    previous_unstructured = starting_context

    def create_page(scene, is_first_scene):
        nonlocal previous_unstructured

        page = {
            'name': scene['id'],
            'scenario_id': scenario_id,
            'scenario_name': scenario['name'],
            'elements': []
        }

        if not is_first_scene:
            conditions = scene_conditions.get(scene['id'], [])
            if conditions:
                page['visibleIf'] = " or ".join(conditions)

        current_unstructured = scene.get('state', {}).get('unstructured', starting_context)
        new_unstructured = get_text_difference(previous_unstructured, current_unstructured)
        previous_unstructured = current_unstructured

        current_supplies = scene.get('state', {}).get('supplies', starting_supplies)
        
        scene_characters = get_scene_characters(scene)

        action_character_ids = set(action.get('character_id') for action in scene['action_mapping'] if 'character_id' in action)
        filtered_characters = [
            character for character in scene_characters
            if character['id'] in action_character_ids
        ]

        events = scene.get('state', {}).get('events', []) if not is_first_scene else initial_events

        event_messages = [{
            'message': event['unstructured'],
            'type': event.get('type'),
            'source': event.get('source'),
            'object': event.get('object', ''),
            'action_id': event.get('action_id', ''),
            'relevant_state': event.get('relevant_state', [])
        } for event in events]

        template_element = {
            'name': 'template ' + str(page['name']),
            'title': ' ',
            'type': 'medicalScenario',
            'unstructured': new_unstructured if new_unstructured else "No new information.",
            'supplies': current_supplies,
            'patients': filtered_characters,
            'events': event_messages
        }
        page['elements'].append(template_element)

        choices = []
        question_mapping = {}
        for action in scene['action_mapping']:
            choices.append({
                "value": action['unstructured'],
                "text": action['unstructured']
            })
            question_mapping[action['unstructured']] = {
                "probe_id": action['probe_id'],
                "choice": action.get('choice', '')
            }

        question_element = {
            'type': 'radiogroup',
            'choices': choices,
            'isRequired': True,
            'title': 'What action do you take?',
            'name': 'probe ' + str(page['name']),
            'probe_id': scene['action_mapping'][0]['probe_id'] if scene['action_mapping'] else '',
            'question_mapping': question_mapping
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
        
        visible_characters = [char for char in all_characters if not char.get('unseen', False)]

        return visible_characters

    def process_scene(scene_id, is_first_scene):
        if scene_id in processed_scenes:
            return
        processed_scenes.add(scene_id)

        scene = scene_map[scene_id]
        if not scene.get('action_mapping'):
            return

        page = create_page(scene, is_first_scene)
        doc['pages'].append(page)

        for action in scene['action_mapping']:
            next_scene = action.get('next_scene')
            if next_scene:
                condition = f"{{probe {scene['id']}}} = '{action['unstructured']}'"
                if next_scene not in scene_conditions:
                    scene_conditions[next_scene] = []
                scene_conditions[next_scene].append(condition)

    for scene_id in scene_map.keys():
        is_first_scene = (scene_id == scenario.get('first_scene') or (not scenario.get('first_scene') and scene_id == next(iter(scene_map))))
        process_scene(scene_id, is_first_scene)

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