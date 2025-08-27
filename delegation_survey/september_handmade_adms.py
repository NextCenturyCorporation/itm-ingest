import yaml, json, os, copy
from delegation_survey.phase2_covert_adm_to_del_materials import get_unique_medic_name 
from delegation_survey.phase2_covert_adm_to_del_materials import find_scene_by_probe_id

fake_adm_mappings = {
    'PS': [
         ['Probe 3', 'Probe 8', 'Probe 14'],
         ['Probe 9', 'Probe 22', 'Probe 13'],
         ['Probe 11', 'Probe 23', 'Probe 19']
    ],
    'AF': [
        ['Probe 5', 'Probe 15', 'Probe 101'],
        ['Probe 6', 'Probe 21', 'Probe 106'],
        ['Probe 111', 'Probe 31', 'Probe 107']
    ]
}




def create_adm(target, probe_set, attr, probe_set_index, template, medic_collection):
    doc = copy.deepcopy(template)
    medic_name = get_unique_medic_name(medic_collection)

    scenario = f"Sept2025-{attr}{probe_set_index}-eval"

    doc.update({
        'name': medic_name,
        'title': ' ',
        'target': target,
        'scenarioIndex': scenario,
        'admAuthor': 'kitware',
        'evalNumber': 10,
    })

    doc['elements'][0]['rows'] = []
    doc['elements'][0]['title'] = ' '
    
    doc['elements'][0]['name'] = medic_name

    for i, element in enumerate(doc['elements']):
        if 'name' in element and 'Test medic 1' in element['name']:
            doc['elements'][i]['name'] = element['name'].replace('Test medic 1', medic_name)
        if 'title' in element and 'Test medic 1' in element['title']:
            doc['elements'][i]['title'] = element['title'].replace('Test medic 1', medic_name)

    #load scenario yaml file
    yaml_dir = os.path.join('phase2', 'september2025')
    yaml_data = None
    for filename in os.listdir(yaml_dir):
        if not filename.endswith('.yaml'):
            continue
        yaml_path = os.path.join(yaml_dir, filename)
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if data.get('id') == scenario:
                    yaml_data = data
                    break
        except Exception as e:
                print(f"Error reading {filename}: {e}")
                continue
        
    if not yaml_data:
        print(f"Warning: No YAML file found with name matching scenario: {scenario}")
        return
    
    choices = [action['unstructured'] for action in yaml_data['scenes'][0]['action_mapping']]
    doc['elements'][0]['options'] = choices

    scenario_description = yaml_data['scenes'][0]['state']['threat_state']['unstructured']
    doc['elements'][0]['scenarioDescription'] = scenario_description

    for probe in probe_set:
        scene = find_scene_by_probe_id(yaml_data, probe)

        if not scene:
            print(f"Error: did not find matching probe in yaml file for {probe}")
            continue
        choice = 1 if target == 'high' else 0

        row_data = {
            'choice': scene['action_mapping'][choice]['unstructured'],
            'probe_unstructured': scene['state']['unstructured']
        }

        doc['elements'][0]['rows'].append(row_data)

    print(f"Creating medic document with name: {medic_name}")
    medic_collection.insert_one(doc)

'''
Not for multi-kdma. This is for the 4 targets that are PS and AF singular probes appended.
Uses ADMs that were just crafted

High PS/Low AF
High PS/High AF
Low PS/Low AF
Low PS/Low AF
'''
def ps_and_af(medic_collection):
    for i in range(1, 4):
        af_scenario_id = f'Sept2025-AF{i}-eval'
        ps_scenario_id = f'Sept2025-PS{i}-eval'

        af_high = medic_collection.find_one({'scenarioIndex': af_scenario_id, 'target': 'high'})
        af_low = medic_collection.find_one({'scenarioIndex': af_scenario_id, 'target': 'low'})
        ps_high = medic_collection.find_one({'scenarioIndex': ps_scenario_id, 'target': 'high'})
        ps_low = medic_collection.find_one({'scenarioIndex': ps_scenario_id, 'target': 'low'})

        if not all([af_high, af_low, ps_high, ps_low]):
            print(f"Missing ADM for PS/AF {i}.")
            continue

        combos = [
            ("high", "high", ps_high, af_high),
            ("high", "low", ps_high, af_low),
            ("low", "high", ps_low, af_high),
            ("low", "low", ps_low, af_low),
        ]

        for ps_target, af_target, ps_doc, af_doc in combos:
            # Deep copy from ps_doc as base
            new_doc = copy.deepcopy(ps_doc)

            if '_id' in new_doc:
                del new_doc['_id']

            # Update name and metadata
            new_doc['name'] = get_unique_medic_name(medic_collection)
            new_doc['title'] = ' '
            new_doc['scenarioIndex'] = f"Sept2025-PSAF{i}-combined-eval"
            new_doc['admAuthor'] = 'kitware'
            new_doc['evalNumber'] = 10
            new_doc['target'] = f"PS-{ps_target}_AF-{af_target}"

            ps_rows = ps_doc['elements'][0]['rows'][:3]
            af_rows = af_doc['elements'][0]['rows'][:3]
            new_doc['elements'][0]['rows'] = ps_rows + af_rows

            # Ensure element name/title updated
            medic_name = new_doc['name']
            new_doc['elements'][0]['name'] = medic_name
            new_doc['elements'][0]['title'] = ' '

            print(f"Creating combined PS/AF medic: {new_doc['name']} ({new_doc['scenarioIndex']})")
            medic_collection.insert_one(new_doc)
    

def main(mongo_db):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(script_dir, 'templates', 'phase2_single_medic_template.json')
    f = open(template_path, 'r', encoding='utf-8')
    template = json.load(f)
    medic_collection = mongo_db['admMedics']
    medic_collection.delete_many({'evalNumber': 10})

    for attr, probe_sets in fake_adm_mappings.items():
        for probe_set_index, probe_set in enumerate(probe_sets, start=1):
            create_adm('high', probe_set, attr, probe_set_index, template, medic_collection)
            create_adm('low', probe_set, attr, probe_set_index, template, medic_collection)

    ps_and_af(medic_collection)