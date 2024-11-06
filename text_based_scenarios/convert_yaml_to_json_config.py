import yaml
import os
from collections import OrderedDict
from decouple import config 
from pymongo import MongoClient

v_gauze = 'Response 3-B.2-A-gauze-v'
s_gauze = 'Response 3-B.2-B-gauze-s'
special_case_probe = {
    'DryRunEval-MJ2-eval': {
        'Scene 2A': {
            '5 Babson / 0 Alderson': [v_gauze, v_gauze, v_gauze, v_gauze, v_gauze],
            '4 Babson / 1 Alderson': [v_gauze, v_gauze, v_gauze, v_gauze, s_gauze],
            '3 Babson / 2 Alderson': [v_gauze, v_gauze, v_gauze, s_gauze, s_gauze],
            'Do not treat either patient with gauze, look for new patients': 'Response 3-B.2-C'
        }
    }
}

always_visible_characters = {
    'DryRunEval-MJ5-eval': {
        'Scene 3': ['us_soldier'],
        'Probe 8': ['us_soldier'],
        'Probe 9-C.1': ['us_soldier']
    },
    'DryRunEval-MJ4-eval': {
        'Scene 2': ['US soldier']
    },
    'DryRunEval-MJ2-eval': {
        'Scene 3': ['Victim'],
        'Probe 4-B.1': ['Victim'],
        'Probe 4-B.1-B.1': ['Victim']
    }
}

transition_scenes = {
    'DryRunEval-MJ5-eval': ['Scene 2'],
    'DryRunEval-MJ4-eval': ['Transition to Scene 2'],
    'DryRunEval-MJ2-eval': ['Transition to Scene 4']
}

always_visible_edge_case = {
    'DryRunEval-MJ2-eval': ['Scene 4']
}

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
    parts = text.split('<text_scenario_line_break>')
    return parts[1].strip() if len(parts) > 1 else text.strip()

def get_scene_text(scene, is_first_scene, starting_context):
    if is_first_scene:
        return starting_context
    
    if 'probe_config' in scene:
        probe_config = scene['probe_config']
        if isinstance(probe_config, list) and probe_config and 'description' in probe_config[0]:
            return probe_config[0]['description']
    
    return scene.get('state', {}).get('unstructured', '')

def partition_doc(scenario, filename):
    scenario_id = scenario['id']
    scenes = scenario['scenes']
    starting_context = scenario['state']['unstructured']
    starting_mission = scenario['state'].get('mission', {})
    current_supplies = scenario['state']['supplies']
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
        
        action_character_ids = set(action.get('character_id') for action in scene['action_mapping'] if 'character_id' in action)
        
        # Get the list of always visible characters for this scene
        always_visible = always_visible_characters.get(scenario_id, {}).get(scene['id'], [])
        
        visible_characters = set()
        for char in all_characters:
            if not char.get('unseen', False):
                if (char['id'].lower() in {id.lower() for id in action_character_ids} or any(char['id'] == action.get('character_id') for action in scene['action_mapping'])):
                    visible_characters.add(char['id'])
            if char['id'] in always_visible:
                visible_characters.add(char['id'])

        return [char for char in all_characters if char['id'] in visible_characters]

    def create_page(scene, is_first_scene, transition_info=None):
        nonlocal current_supplies

        page = {
            'name': scene['id'],
            'scenario_id': scenario_id,
            'scenario_name': scenario['name'],
            'elements': []
        }

        unstructured = get_scene_text(scene, is_first_scene, starting_context)
        processed_unstructured = process_unstructured_text(unstructured)
        if 'supplies' in scene.get('state', {}):
            current_supplies = scene['state']['supplies']
        
        if transition_info:
            # characters introduced in transition scenes
            if 'characters' in transition_info:
                for char in transition_info['characters']:
                    if char not in all_characters:
                        all_characters.append(char)
                        char['unseen'] = False 

        scene_characters = get_scene_characters(scene)

        # Soartech always wants vitals visible
        if 'soartech' in filename.lower():
            blocked_vitals = [] 
            for char in scene_characters:
                if 'vitals' in char and 'mental_status' in char['vitals']:
                    del char['vitals']['mental_status']
        else:
            blocked_vitals = [
                action['character_id']
                for action in scene['action_mapping']
                if action['action_type'] == 'CHECK_ALL_VITALS'
            ]

            # edge case adept
            if scene.get('vitals_blocked', False):
                blocked_vitals = [char['id'] for char in scene_characters]

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
            'title': " ",
            'type': 'medicalScenario',
            'unstructured': processed_unstructured,
            'supplies': current_supplies,
            'patients': scene_characters,
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

        regular_actions = []
        conditional_actions = []

        for action in scene['action_mapping']:
            if 'action_conditions' in action:
                if action.get('action_condition_semantics') == 'not':
                    regular_actions.append(action)
                else:
                    conditional_actions.append(action)
            else:
                regular_actions.append(action)

        # Create the main question
        choices = []
        question_mapping = {}
        # 'what action do you intend to take' if all actions are intent
        all_intent_actions = all(action.get('intent_action', False) for action in regular_actions)
        for action in regular_actions:
            choices.append({
                "value": action['unstructured'],
                "text": action['unstructured']
            })
            if scenario_id in special_case_probe and scene['id'] in special_case_probe[scenario_id]:
                question_mapping[action['unstructured']] = {
                    "probe_id": action['probe_id'],
                    "choice": special_case_probe[scenario_id][scene['id']][action['unstructured']]
                }
            else:
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
            'title': 'What action do you intend to take?' if all_intent_actions else 'What action do you take?',
            'name': 'probe ' + str(page['name']),
            'probe_id': regular_actions[0]['probe_id'] if regular_actions else '',
            'question_mapping': question_mapping
        }
        page['elements'].append(main_question_element)

        # Create conditional question
        if conditional_actions:
            choices = []
            question_mapping = {}
            for action in conditional_actions:
                visible_if = 'probe_responses' in action['action_conditions']

                if visible_if:
                    dependent_response = action['action_conditions']['probe_responses'][0]
                    matching_action_text = ""
                    for reg_action in regular_actions:
                        if reg_action['choice'] == dependent_response:
                            matching_action_text = reg_action['unstructured']
                            break
                    choices.append({
                        "value": action['unstructured'],
                        "text": action['unstructured'],
                        'visibleIf':  f"({{probe {scene['id']}}} == '{matching_action_text}')"
                    })
                else:
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
                    condition = f"({{probe {scene['id']}}} notempty) and ({{probe {scene['id']}_conditional}} = '{action['unstructured']}')"
                    if next_scene not in scene_conditions:
                        scene_conditions[next_scene] = []
                    scene_conditions[next_scene].append(condition)

            conditional_question_element = {
                'type': 'radiogroup',
                'choices': choices,
                'isRequired': True,
                'title': 'Why did you choose that action?',
                'name': f'probe {scene["id"]}_conditional',
                'probe_id': conditional_actions[0]['probe_id'],
                'question_mapping': question_mapping,
                'visibleIf': f'{{probe {scene["id"]}}} notempty'
            }
            page['elements'].append(conditional_question_element)

        return page

    # Process scenes in order
    transition_info = None
    for scene in scenes:
        is_transition = scenario_id in transition_scenes and scene['id'] in transition_scenes[scenario_id]
        
        if is_transition:
            transition_info = {
                'unstructured': process_unstructured_text(scene['state']['unstructured']),
                'action': scene['action_mapping'][0]['unstructured']
            }
            # event information to transition_info if it exists
            if 'events' in scene['state']:
                transition_info['events'] = scene['state']['events']
            # character information to transition_info
            if 'characters' in scene['state']:
                transition_info['characters'] = scene['state']['characters']
            # skip creating a page for this transition scene
            continue

        is_first_scene = (scene['id'] == scenario.get('first_scene') or (not scenario.get('first_scene') and scene == scenes[0]))
        page = create_page(scene, is_first_scene, transition_info)
        doc['pages'].append(page)
        transition_info = None  # Reset transition_info after use

    # Apply visibility conditions
    for page in doc['pages']:
        if page['name'] in scene_conditions:
            page['visibleIf'] = " or ".join(scene_conditions[page['name']])
            if page['scenario_id'] in always_visible_edge_case and page['name'] in always_visible_edge_case[page['scenario_id']]:
                page['visibleIf'] = None

    doc = add_surveyjs_configs(doc)
    return doc

def upload_config(docs, textbased_mongo_collection):
    if not docs:
        print("No new documents to upload.")
        return
    
    # Check for existing documents and only add new ones
    existing_scenario_ids = set(doc['scenario_id'] for doc in textbased_mongo_collection.find({}, {'scenario_id': 1}))
    
    new_docs = []
    updated_docs = []
    for doc in docs:
        if doc['scenario_id'] in existing_scenario_ids:
            # Update existing document
            textbased_mongo_collection.replace_one(
                {'scenario_id': doc['scenario_id']}, 
                doc
            )
            updated_docs.append(doc['scenario_id'])
        else:
            # Add new document
            new_docs.append(doc)
    
    if new_docs:
        textbased_mongo_collection.insert_many(new_docs)
    
    print(f"Added {len(new_docs)} new scenarios")
    if updated_docs:
        print(f"Updated {len(updated_docs)} existing scenarios: {', '.join(updated_docs)}")

def main():
    client = MongoClient(config('MONGO_URL'))
    db = client.dashboard
    textbased_mongo_collection = db['textBasedConfig']

    current_dir = os.path.dirname(os.path.abspath(__file__))
    mre_folder = os.path.join(current_dir, 'mre-yaml-files')
    dre_folder = os.path.join(current_dir, 'dre-yaml-files')
    phase1_folder = os.path.join(current_dir, 'phase1-yaml-files')

    all_docs = []

    for folder, eval_type in [(mre_folder, 'mre'), (dre_folder, 'dre'), (phase1_folder, 'phase1')]:
        if not os.path.exists(folder):
            print(f"Warning: {folder} does not exist.")
            continue

        for filename in os.listdir(folder):
            if filename.endswith('.yaml'):
                file_path = os.path.join(folder, filename)
                try:
                    with open(file_path, 'r') as file:
                        scenario = yaml.safe_load(file)
                    doc = partition_doc(scenario, filename)
                    doc['eval'] = eval_type
                    all_docs.append(doc)
                    print(f"Processed: {filename}")
                except Exception as e:
                    print(f"Error processing {filename}: {str(e)}")
        
    upload_config(all_docs, textbased_mongo_collection)

if __name__ == '__main__':
    main()