import utils.db_utils as db_utils

def main(mongoDB, EVAL_NUMBER=4):
    text_scenario_collection = mongoDB['userScenarioResults']
    match_collection = mongoDB['admVsTextProbeMatches']
    adm_collection = mongoDB["test"]

    data_to_use = text_scenario_collection.find(
        {"evalNumber": EVAL_NUMBER}
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
            tad_most_adm = db_utils.find_most_least_adm(EVAL_NUMBER, adm_collection, scenario_id, edited_target, 'TAD-aligned')
            if tad_most_adm is not None:
                perc = calculate_matches(entry, tad_most_adm, attribute)
                document = {
                    'pid': pid,
                    'adm_type': 'most aligned',
                    'score': perc,
                    'text_scenario': scenario_id,
                    'adm_author': 'TAD',
                    'attribute': attribute,
                    'adm_alignment_target': most.get('target', list(most.keys())[0]),
                    'evalNumber': EVAL_NUMBER
                }
                db_utils.send_match_document_to_mongo(match_collection, document)
            
            ### GET KITWARE ALIGNED AT MOST ALIGNED TARGET
            kit_most_adm = db_utils.find_most_least_adm(EVAL_NUMBER, adm_collection, scenario_id, edited_target, 'ALIGN-ADM-ComparativeRegression-ICL-Template')
            if kit_most_adm is not None:
                perc = calculate_matches(entry, kit_most_adm, attribute)
                document = {
                    'pid': pid,
                    'adm_type': 'most aligned',
                    'score': perc,
                    'text_scenario': scenario_id,
                    'adm_author': 'kitware',
                    'attribute': attribute,
                    'adm_alignment_target': most.get('target', list(most.keys())[0]),
                    'evalNumber': EVAL_NUMBER
                }
                db_utils.send_match_document_to_mongo(match_collection, document)

            edited_target = least.get('target', list(least.keys())[0])
            if 'Ingroup' in attribute or 'Moral' in attribute:
                edited_target = edited_target[:-1] + '.' + edited_target[-1]
            
            ### GET TAD ALIGNED AT LEAST ALIGNED TARGET
            tad_least_adm = db_utils.find_most_least_adm(EVAL_NUMBER, adm_collection, scenario_id, edited_target, 'TAD-aligned')
            if tad_least_adm is not None:
                perc = calculate_matches(entry, tad_least_adm, attribute)
                document = {
                    'pid': pid,
                    'adm_type': 'least aligned',
                    'score': perc,
                    'text_scenario': scenario_id,
                    'adm_author': 'TAD',
                    'attribute': attribute,
                    'adm_alignment_target': least.get('target', list(least.keys())[0]),
                    'evalNumber': EVAL_NUMBER
                }
                db_utils.send_match_document_to_mongo(match_collection, document)
            
            ### GET TAD ALIGNED AT LEAST ALIGNED TARGET
            kit_least_adm = db_utils.find_most_least_adm(EVAL_NUMBER, adm_collection, scenario_id, edited_target, 'ALIGN-ADM-ComparativeRegression-ICL-Template')
            if kit_least_adm is not None:
                perc = calculate_matches(entry, kit_least_adm, attribute)
                document = {
                    'pid': pid,
                    'adm_type': 'least aligned',
                    'score': perc,
                    'text_scenario': scenario_id,
                    'adm_author': 'kitware',
                    'attribute': attribute,
                    'adm_alignment_target': least.get('target', list(least.keys())[0]),
                    'evalNumber': EVAL_NUMBER
                }
                db_utils.send_match_document_to_mongo(match_collection, document)


        for target in entry.get('group_targets', []):
            attribute = 'QualityOfLife' if 'qol' in target else 'PerceivedQuantityOfLivesSaved' if 'vol' in target else 'Ingroup Bias' if 'Ingroup' in target else 'Moral judgement'
            tad_aligned = db_utils.find_most_least_adm(EVAL_NUMBER, adm_collection, scenario_id, target, 'TAD-aligned')
            if tad_aligned is not None:
                perc = calculate_matches(entry, tad_aligned, attribute)
                document = {
                    'pid': pid,
                    'adm_type': 'group target',
                    'score': perc,
                    'text_scenario': scenario_id,
                    'adm_author': 'TAD',
                    'attribute': attribute,
                    'adm_alignment_target': target,
                    'evalNumber': EVAL_NUMBER
                }
                db_utils.send_match_document_to_mongo(match_collection, document)

            kit_aligned = db_utils.find_most_least_adm(EVAL_NUMBER, adm_collection, scenario_id, target, 'ALIGN-ADM-ComparativeRegression-ICL-Template')
            if kit_aligned is not None:
                perc = calculate_matches(entry, kit_aligned, attribute)
                document = {
                    'pid': pid,
                    'adm_type': 'group target',
                    'score': perc,
                    'text_scenario': scenario_id,
                    'adm_author': 'kitware',
                    'attribute': attribute,
                    'adm_alignment_target': target,
                    'evalNumber': EVAL_NUMBER
                }
                db_utils.send_match_document_to_mongo(match_collection, document)

    print("Text vs ADM probe match percentage values added to database.")


def calculate_matches(text, adm, attribute):
    '''
    Look through probes of text scenario and adm to count how many
    responses match.
    '''
    MJ_PROBES = {
        "MJ2": ["Probe 2", "Probe 2A-1", "Probe 2B-1", "Probe 3-B.2", "Probe 5", "Probe 5-A.1", "Probe 5-B.1", "Probe 6", "Probe 7"],
        "MJ4": ["Probe 1", "Probe 2 kicker", "Probe 2 passerby", "Probe 2-A.1", "Probe 2-D.1", "Probe 2-D.1-B.1", "Probe 3", "Probe 3-A.1", "Probe 3-B.1", "Response 7-B", "Response 7-C", "Response 8-B", "Response 8-C", "Probe 9", "Response 10-B", "Response 10-C", "Probe 10-A.1", "Probe 10-A.1-B.1", "Probe 10-B.1", "Probe 10-C.1"],
        "MJ5": ["Probe 1", "Probe 1-A.1", "Probe 1-B.1", "Probe 2", "Probe 2-A.1-A.1", "Probe 2-A.1-B.1-A.1", "Probe 2-B.1-A.1", "Probe 2-B.1-B.1-A.1", "Probe 4", "Probe 8-A.1"]
    }
    IO_PROBES = {
        "MJ2": ["Probe 4", "Probe 4-B.1", "Probe 4-B.1-B.1", "Probe 8", "Probe 9", "Probe 9-A.1", "Probe 10", "Probe 9-B.1"],
        "MJ4": ["Probe 6", "Probe 7", "Probe 8", "Probe 10"],
        "MJ5": ["Probe 7", "Probe 8", "Probe 8-A.1", "Probe 8-A.1-A.1", "Probe 9", "Probe 9-A.1", "Probe 9-B.1", "Probe 9-C.1"]
    }
    scenario_id = text.get('scenario_id')
    ALLOWED_PROBES = MJ_PROBES if attribute == 'Moral judgement' else IO_PROBES if attribute == 'Ingroup Bias' else None
    if ALLOWED_PROBES is not None:
        ALLOWED_PROBES = ALLOWED_PROBES['MJ2' if 'MJ2' in scenario_id else 'MJ4' if 'MJ4' in scenario_id else 'MJ5']
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
                if ALLOWED_PROBES is None or (p1['probe_id'] in ALLOWED_PROBES or (p1['choice'] in ALLOWED_PROBES and p2['choice'] in ALLOWED_PROBES)):
                    total += 1
                    if p1['choice'] == p2['choice']:
                        matches += 1

    return matches / max(1, total)
    