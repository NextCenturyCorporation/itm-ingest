def find_matching_probe_percentage(mongoDB):
    text_scenario_collection = mongoDB['userScenarioResults']
    delegation_collection = mongoDB['surveyResults']
    match_collection = mongoDB['admVsTextProbeMatches']
    adm_collection = mongoDB["test"]

    data_to_use = text_scenario_collection.find(
        {"evalNumber": 4}
    )

    for entry in data_to_use:
        scenario_id = entry.get('scenario_id')
        if 'MJ1' in scenario_id or 'IO1' in scenario_id:
            # ignore test scenarios from adept
            continue
        pid = entry.get('participantID')
        for target in entry['mostLeastAligned']:
            attribute = target['target']
            most = target['response'][0]
            least = target['response'][len(target['response'])-1]
            # find the adm at the text-scenario scenario at the aligned or misaligned target
            edited_target = most.get('target', list(most.keys())[0])
            if 'Ingroup' in attribute or 'Moral' in attribute:
                edited_target = edited_target[:-1] + '.' + edited_target[-1]
            
            ### GET TAD ALIGNED AT MOST ALIGNED TARGET
            tad_most_adm = find_adm(adm_collection, scenario_id, edited_target, 'TAD-aligned')
            if tad_most_adm is not None:
                perc = calculate_matches(entry, tad_most_adm)
                document = {
                    'pid': pid,
                    'adm_type': 'most aligned',
                    'score': perc,
                    'text_scenario': scenario_id,
                    'adm_author': 'TAD',
                    'attribute': attribute,
                    'adm_alignment_target': most.get('target', list(most.keys())[0]),
                    'evalNumber': 4
                }
                send_document_to_mongo(match_collection, document)
            
            ### GET KITWARE ALIGNED AT MOST ALIGNED TARGET
            kit_most_adm = find_adm(adm_collection, scenario_id, edited_target, 'ALIGN-ADM-ComparativeRegression-ICL-Template')
            if kit_most_adm is not None:
                perc = calculate_matches(entry, kit_most_adm)
                document = {
                    'pid': pid,
                    'adm_type': 'most aligned',
                    'score': perc,
                    'text_scenario': scenario_id,
                    'adm_author': 'kitware',
                    'attribute': attribute,
                    'adm_alignment_target': most.get('target', list(most.keys())[0]),
                    'evalNumber': 4
                }
                send_document_to_mongo(match_collection, document)

            edited_target = least.get('target', list(least.keys())[0])
            if 'Ingroup' in attribute or 'Moral' in attribute:
                edited_target = edited_target[:-1] + '.' + edited_target[-1]
            ### GET TAD ALIGNED AT LEAST ALIGNED TARGET
            tad_least_adm = find_adm(adm_collection, scenario_id, edited_target, 'TAD-aligned')
            if tad_least_adm is not None:
                perc = calculate_matches(entry, tad_least_adm)
                document = {
                    'pid': pid,
                    'adm_type': 'least aligned',
                    'score': perc,
                    'text_scenario': scenario_id,
                    'adm_author': 'TAD',
                    'attribute': attribute,
                    'adm_alignment_target': least.get('target', list(least.keys())[0]),
                    'evalNumber': 4
                }
                send_document_to_mongo(match_collection, document)
            ### GET TAD ALIGNED AT LEAST ALIGNED TARGET
            kit_least_adm = find_adm(adm_collection, scenario_id, edited_target, 'ALIGN-ADM-ComparativeRegression-ICL-Template')
            if kit_least_adm is not None:
                perc = calculate_matches(entry, kit_least_adm)
                document = {
                    'pid': pid,
                    'adm_type': 'least aligned',
                    'score': perc,
                    'text_scenario': scenario_id,
                    'adm_author': 'kitware',
                    'attribute': attribute,
                    'adm_alignment_target': least.get('target', list(least.keys())[0]),
                    'evalNumber': 4
                }
                send_document_to_mongo(match_collection, document)

    print("Text vs ADM probe match percentage values added to database.")


def calculate_matches(text, adm):
    '''
    Look through probes of text scenario and adm to count how many
    responses match.
    '''
    adm_probes = []
    for x in adm['history']:
        if x['command'] == 'Respond to TA1 Probe':
            adm_probes.append(x['parameters'])
    text_probes = []
    for page in text:
        if type(text[page]) == dict:
            if 'questions' in text[page] and f'probe {page}' in text[page]['questions'] and 'response' in text[page]['questions'][f'probe {page}']:
                resp = text[page]['questions'][f'probe {page}']['response'].replace('.', '')
                if 'question_mapping' in text[page]['questions'][f'probe {page}']:
                    q_map = text[page]['questions'][f'probe {page}']['question_mapping']
                    text_probes.append(q_map[resp])
    matches = 0
    total = 0
    # only count probes that both the participant and adm answered (Jennifer's instruction - remind her!)
    for p1 in text_probes:
        for p2 in adm_probes:
            if p1['probe_id'] == p2['probe_id']:
                total += 1
                if p1['choice'] == p2['choice']:
                    matches += 1

    return matches / max(1, total)
    

def find_adm(adm_collection, scenario, target, adm_name):
    adms = adm_collection.find({'evalNumber': 4,     '$or': [{'history.1.response.id': scenario}, {'history.0.response.id': scenario}], 'history.0.parameters.adm_name': adm_name})
    adm = None
    for x in adms:
        if x['history'][len(x['history'])-1]['parameters']['target_id'] == target:
            adm = x
            break
    if adm is None:
        print(f"No matching adm found for scenario {scenario} with adm {adm_name} at target {target}")
        return None
    return adm


def send_document_to_mongo(match_collection, document):
    # do not send duplicate documents, make sure if one already exists, we just replace it
    found_docs = match_collection.find({'pid': document['pid'], 'adm_type': document['adm_type'], 'text_scenario': document['text_scenario'], 
                                                'adm_author': document['adm_author'], 'adm_alignment_target': document['adm_alignment_target'], 'attribute': document['attribute']})
    doc_found = False
    obj_id = ''
    for doc in found_docs:
        doc_found = True
        obj_id = doc['_id']
        break
    if doc_found:
        match_collection.update_one({'_id': obj_id}, {'$set': document})
    else:
        match_collection.insert_one(document)