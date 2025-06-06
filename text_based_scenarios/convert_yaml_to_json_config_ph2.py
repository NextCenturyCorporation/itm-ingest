import os, yaml

def add_surveyjs_configs(doc):
    doc['showQuestionNumbers'] = False
    doc['showPrevButton'] = False
    doc['title'] = doc['scenario_id']
    doc['logoPosition'] = 'right'
    doc['completedHtml'] = '<h3>Thank you for completing the scenario</h3>'
    doc['widthMode'] = 'responsive'
    doc['showProgressBar'] = 'top'
    return doc

def create_page(scene, doc):
    page = {
        'name': scene['id'],
        'title': '',
        'scenario_id': doc['scenario_id'],
        'scenario_name': doc['name'],
        'elements': []
    }

    common_unstructured = scene['state']['threat_state']['unstructured']
    probe_unstructured = scene['state']['unstructured']

    template_element = {
        'name': 'template ' + str(page['name']),
        'title': ' ',
        'type': 'phase2Text' ,
        'common_unstructured': common_unstructured,
        'probe_unstructured': probe_unstructured
    } 

    page['elements'].append(template_element)

    actions = []

    for action in scene['action_mapping']:
        actions.append(action)

    question_mapping = {}
    choices = []

    for action in actions:
        choices.append({
            "value": action['unstructured'],
            "text": action['unstructured']
        })
        question_mapping[action['unstructured']] = {
            "probe_id": action['probe_id'],
            "choice": action['choice']
        }

    question_element = {
        'type': 'radiogroup',
        'choices': choices,
        'isRequired': True,
        'title': 'What action do you take?',
        'name': 'probe ' + str(page['name']),
        'probe_id': actions[0]['probe_id'],
        'question_mapping': question_mapping
    }

    page['elements'].append(question_element)

    return page

def process_scenario(scenario):
    doc = {
        'scenario_id': scenario['id'], 
        'eval': 'Phase 2 June 2025 Collaboration',
        'name': scenario['name'],
        'pages': []
        }
    doc = add_surveyjs_configs(doc)

    for scene in scenario['scenes']:
        # this will need to be replaced with if scene[id] in list of selected probes (i dont have yet)
        if scene['id']:
            new_page = create_page(scene, doc)
            doc['pages'].append(new_page)
    return doc

def upload_configs(docs, collection):
    if not docs:
        print("No documents to upload")
        return
    
    uploaded_count = 0
    replaced_count = 0
    
    for doc in docs:
        scenario_id = doc['scenario_id']
        
        # Replace document with matching scenario_id, or insert if it doesn't exist
        result = collection.replace_one(
            {'scenario_id': scenario_id}, 
            doc, 
            upsert=True
        )
        
        if result.upserted_id:
            print(f"Uploaded new scenario: {scenario_id}")
            uploaded_count += 1
        elif result.modified_count > 0:
            print(f"Replaced existing scenario: {scenario_id}")
            replaced_count += 1
        else:
            print(f"No changes made to scenario: {scenario_id}")
    
    print(f"\nSummary: {uploaded_count} new uploads, {replaced_count} replacements")


def main(mongo_db):
    text_configs = mongo_db['textBasedConfig']
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    phase2_folder = os.path.join(current_dir, 'phase2-yaml-files')

    all_docs = []

    for filename in os.listdir(phase2_folder):
        file_path = os.path.join(phase2_folder, filename)

        try:
            with open(file_path, 'r') as file:
                scenario = yaml.safe_load(file)
            doc = process_scenario(scenario)
            all_docs.append(doc)
        except Exception as e:
            print(f"Error processing {filename}: {str(e)}")

    upload_configs(all_docs, text_configs)