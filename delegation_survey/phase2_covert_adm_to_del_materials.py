import os, json, copy, yaml

# grabs a medic name, makes sure no duplicate in admMedics collection
def get_unique_medic_name(medic_collec):
    names = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 
             'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']
    existing_medics = medic_collec.find(
        {"name": {"$regex": "^Medic-[A-Z]\\d{1,2}$"}}, 
        {"name": 1}
    )
    
    used_names = set()
    for doc in existing_medics:
        name = doc.get('name', '')
        if name.startswith('Medic-'):
            used_names.add(name)
    
    for letter in names:
        for num in range(1, 100):
            candidate_name = f"Medic-{letter}{num}"
            if candidate_name not in used_names:
                return candidate_name
    

def find_scene_by_probe_id(yaml_data, probe_id):
    for scene in yaml_data['scenes']:
        if scene['id'] == probe_id:
            return scene
    return None

def find_action_by_choice(scene, choice_id):
    for action in scene['action_mapping']:
        if action['choice'] == choice_id:
            return action
    return None

def convert_adm(adm, scenario, target, name, template, medic_collec, evalNumber):
    # start building document to be uploaded
    doc = copy.deepcopy(template)
    
    # Get a unique medic name
    medic_name = get_unique_medic_name(medic_collec)
    
    doc.update({
        'name': medic_name,
        # need to include blank title or it will use the name field
        'title': ' ',
        'target': target,
        'admName': name,
        'scenarioIndex': scenario,
        'admSessionId': adm['results']['ta1_session_id'],
        'alignmentScore': adm['results']['alignment_score'],
        'kdmas': adm['results']['kdmas'],
        'admAuthor': 'kitware',
        'evalNumber': evalNumber,
    })

    # wipe out template default from rows
    doc['elements'][0]['rows'] = []
    doc['elements'][0]['title'] = ' '
    
    doc['elements'][0]['name'] = medic_name
    
    # Update all the question titles and names that reference placeholder
    for i, element in enumerate(doc['elements']):
        if 'name' in element and 'Test medic 1' in element['name']:
            doc['elements'][i]['name'] = element['name'].replace('Test medic 1', medic_name)
        if 'title' in element and 'Test medic 1' in element['title']:
            doc['elements'][i]['title'] = element['title'].replace('Test medic 1', medic_name)

    for el in adm['history']:
        # grab scenario name
        if el['command'] == 'Start Scenario':
            scenario_name = el['response']['name']
            doc['scenarioName'] = scenario_name
            break
    
    # Load the corresponding YAML file
    if scenario_name:
        extension = 'june2025' if evalNumber == 8 else 'july2025'
        yaml_dir = os.path.join('phase2', extension)
        yaml_data = None
        
        for filename in os.listdir(yaml_dir):
            if filename.endswith('.yaml'):
                yaml_path = os.path.join(yaml_dir, filename)
                try:
                    with open(yaml_path, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                        if data.get('name') == scenario_name:
                            yaml_data = data
                            break
                except Exception as e:
                    print(f"Error reading {filename}: {e}")
                    continue
        
        if not yaml_data:
            print(f"Warning: No YAML file found with name matching scenario: {scenario_name}")
            return
        
        # grab the two choices for the probes in the scenario
        choices = [action['unstructured'] for action in yaml_data['scenes'][0]['action_mapping']]
        doc['elements'][0]['options'] = choices
        
        # grabs the repeated text
        scenario_description = yaml_data['scenes'][0]['state']['threat_state']['unstructured']
        doc['elements'][0]['scenarioDescription'] = scenario_description
        
        for el in adm['history']:
            # every probe response 
            if el['command'] == 'Respond to TA1 Probe':
                probe_id = el['parameters']['probe_id']
                choice_id = el['parameters']['choice']

                matching_scene = find_scene_by_probe_id(yaml_data, probe_id)
                # should never happen
                if not matching_scene:
                    print(f"Error: did not find matching probe in yaml file for {probe_id}")
                    continue
                
                matching_action = find_action_by_choice(matching_scene, choice_id)
                # should also never happen
                if not matching_action:
                    print(f"Error: did not find matching action for choice {choice_id} in probe {probe_id}")
                    continue

                row_data = {
                    'choice': matching_action['unstructured'],
                    'probe_unstructured': matching_scene['state']['unstructured']
                }

                doc['elements'][0]['rows'].append(row_data)
    
    print(f"Creating medic document with name: {medic_name}")
    medic_collec.insert_one(doc)

def main(mongo_db, evalNumber):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(script_dir, 'templates', 'phase2_single_medic_template.json')
    f = open(template_path, 'r', encoding='utf-8')
    template = json.load(f)
    adm_runs = mongo_db['admTargetRuns'].find({"evalNumber": evalNumber})
    medic_collec = mongo_db['admMedics']

    for adm in adm_runs:
        scenario = adm['scenario']
        target = adm['alignment_target']
        name = adm['adm_name']
        
        # don't process tests and failed runs
        if 'test' not in name and 'Random' not in name and '6d0829ad-4e3c-4a03-8f3d-472cc549888f' not in name:
            convert_adm(adm, scenario, target, name, template, medic_collec, evalNumber)
