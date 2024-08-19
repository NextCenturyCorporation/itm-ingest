import yaml
import os
from collections import OrderedDict
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

def process_unstructured_text(text):
    parts = text.split('$')
    return parts[1].strip() if len(parts) > 1 else text.strip()

def get_scene_text(scene, is_first_scene, starting_context):
    if is_first_scene:
        return starting_context
    
    if 'probe_config' in scene:
        probe_config = scene['probe_config']
        if isinstance(probe_config, list) and probe_config and 'description' in probe_config[0]:
            return probe_config[0]['description']
    
    return scene.get('state', {}).get('unstructured', '')

def partition_doc(scenario, transition_scenes):
    scenario_id = scenario['id']
    scenes = scenario['scenes']
    starting_context = scenario['state']['unstructured']
    starting_mission = scenario['state'].get('mission', {})
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

    scene_conditions = {}
    all_characters = initial_characters.copy()

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

    def create_page(scene, is_first_scene, transition_info=None):
        page = {
            'name': scene['id'],
            'scenario_id': scenario_id,
            'scenario_name': scenario['name'],
            'elements': []
        }

        unstructured = get_scene_text(scene, is_first_scene, starting_context)
        processed_unstructured = process_unstructured_text(unstructured)
        current_supplies = scene.get('state', {}).get('supplies', starting_supplies)
        
        scene_characters = get_scene_characters(scene)

        action_character_ids = set(action.get('character_id') for action in scene['action_mapping'] if 'character_id' in action)
        filtered_characters = [
            character for character in scene_characters
            if character['id'].lower() in {id.lower() for id in action_character_ids}
        ]

        blocked_vitals = []
        for character in filtered_characters:
            for action in scene['action_mapping']:
                if action['action_type'] == 'CHECK_ALL_VITALS' and action['character_id'].lower() == character['id'].lower():
                    blocked_vitals.append(character['id'])
                    break 

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
            'title': str(page['name']),
            'type': 'medicalScenario',
            'unstructured': processed_unstructured,
            'supplies': current_supplies,
            'patients': filtered_characters,
            'events': event_messages,
            'blockedVitals': blocked_vitals
        }

        if transition_info:
            template_element['transitionInfo'] = transition_info

        mission = starting_mission if is_first_scene else scene.get('state', {}).get('mission', {})
        if mission:
            template_element['mission'] = {
                'roe': mission.get('roe', ''),
                'medical_policies': mission.get('medical_policies', []),
                'unstructured': mission.get('unstructured', '')
            }
        else:
            template_element['mission'] = None

        page['elements'].append(template_element)

        # Separate actions with and without action_conditions
        regular_actions = []
        conditional_actions = {}

        for action in scene['action_mapping']:
            if 'action_conditions' in action and 'probe_responses' in action['action_conditions']:
                probe_response = action['action_conditions']['probe_responses'][0]
                if probe_response not in conditional_actions:
                    conditional_actions[probe_response] = []
                conditional_actions[probe_response].append(action)
            else:
                regular_actions.append(action)

        # Create the main question
        choices = []
        question_mapping = {}
        for action in regular_actions:
            choices.append({
                "value": action['unstructured'],
                "text": action['unstructured']
            })
            question_mapping[action['unstructured']] = {
                "probe_id": action['probe_id'],
                "choice": action.get('choice', '')
            }
            if 'next_scene' in action:
                question_mapping[action['unstructured']]['next_scene'] = action['next_scene']
                next_scene = action['next_scene']
                condition = f"{{probe {scene['id']}}} = '{action['unstructured']}'"
                if next_scene not in scene_conditions:
                    scene_conditions[next_scene] = []
                scene_conditions[next_scene].append(condition)

        main_question_element = {
            'type': 'radiogroup',
            'choices': choices,
            'isRequired': True,
            'title': 'What action do you take?',
            'name': 'probe ' + str(page['name']),
            'probe_id': regular_actions[0]['probe_id'] if regular_actions else '',
            'question_mapping': question_mapping
        }
        page['elements'].append(main_question_element)

        # Create conditional questions
        for i, (probe_response, actions) in enumerate(conditional_actions.items()):
            corresponding_action = next(
                (a for a in regular_actions if a.get('choice') == probe_response),
                None
            )

            if corresponding_action:
                choices = []
                question_mapping = {}
                for action in actions:
                    choices.append({
                        "value": action['unstructured'],
                        "text": action['unstructured']
                    })
                    question_mapping[action['unstructured']] = {
                        "probe_id": action['probe_id'],
                        "choice": action.get('choice', '')
                    }
                    if 'next_scene' in action:
                        question_mapping[action['unstructured']]['next_scene'] = action['next_scene']
                        next_scene = action['next_scene']
                        condition = f"({{probe {scene['id']}}} = '{corresponding_action['unstructured']}') and ({{probe {corresponding_action['probe_id']}}} = '{action['unstructured']}')"
                        if next_scene not in scene_conditions:
                            scene_conditions[next_scene] = []
                        scene_conditions[next_scene].append(condition)

                conditional_question_element = {
                    'type': 'radiogroup',
                    'choices': choices,
                    'isRequired': True,
                    'title': 'Why did you choose the previous action?',
                    'name': f'probe {corresponding_action["probe_id"]}',
                    'probe_id': corresponding_action['probe_id'],
                    'question_mapping': question_mapping,
                    'visibleIf': f'{{probe {page["name"]}}} = "{corresponding_action["unstructured"]}"'
                }
                page['elements'].append(conditional_question_element)

        return page

    # Process scenes in order
    for scene in scenes:
        if scenario_id in transition_scenes and scene['id'] in transition_scenes[scenario_id]:
            transition_info = {
                'unstructured': process_unstructured_text(scene['state']['unstructured']),
                'action': scene['action_mapping'][0]['unstructured']
            }
            # Skip creating a page for this transition scene
            continue

        is_first_scene = (scene['id'] == scenario.get('first_scene') or (not scenario.get('first_scene') and scene == scenes[0]))
        page = create_page(scene, is_first_scene)
        doc['pages'].append(page)

    # Apply visibility conditions
    for page in doc['pages']:
        if page['name'] in scene_conditions:
            page['visibleIf'] = " or ".join(scene_conditions[page['name']])

    doc = add_surveyjs_configs(doc)
    return doc

def upload_config(docs, textbased_mongo_collection):
    textbased_mongo_collection.delete_many({})
    if docs:
        textbased_mongo_collection.insert_many(docs)

def main():
    client = MongoClient(config('MONGO_URL'))
    db = client.dashboard
    textbased_mongo_collection = db['textBasedConfig']

    current_dir = os.path.dirname(os.path.abspath(__file__))
    mre_folder = os.path.join(current_dir, 'mre-yaml-files')
    dre_folder = os.path.join(current_dir, 'dre-yaml-files')

    transition_scenes = {
        'DryRunEval-MJ5-eval': ['Scene 2'],
        'DryRunEval-MJ4-eval': ['Transition to Scene 2']
    }

    all_docs = []

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
                    doc = partition_doc(scenario, transition_scenes)
                    doc['eval'] = eval_type
                    all_docs.append(doc)
                    print(f"Processed: {filename}")
                except Exception as e:
                    print(f"Error processing {filename}: {str(e)}")
        
    upload_config(all_docs, textbased_mongo_collection)
    print(f"Uploaded {len(all_docs)} scenarios, replacing the existing collection.")

if __name__ == '__main__':
    main()