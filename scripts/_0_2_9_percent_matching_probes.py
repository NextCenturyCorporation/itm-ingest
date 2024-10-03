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
        survey = list(delegation_collection.find({"results.Participant ID Page.questions.Participant ID.response": pid}))
        if len(survey) == 0:
            print(f"No survey found for {pid}")
            continue
        survey = survey[-1] # get last survey entry for this pid
        for page in survey['results']:
            if 'Medic' in page and ' vs ' not in page:
                page_scenario = survey['results'][page]['scenarioIndex']
                alignment = survey['results'][page]['admAlignment']
                # we only want most and least aligned targets
                if alignment not in ['aligned', 'misaligned']:
                    continue
                # only match like sceenarios to find the high/low target
                if ('qol' in scenario_id and 'qol' in page_scenario) or ('vol' in scenario_id and 'vol' in page_scenario) or ('DryRunEval' in scenario_id and 'DryRunEval' in page_scenario):
                    # find the adm at the text-scenario scenario at the aligned or misaligned target
                    adm = find_adm(adm_collection, page, scenario_id.replace('IO', 'MJ'), survey)
                    if adm is None:
                        continue
                    adm_target = adm['history'][len(adm['history'])-1]['parameters']['target_id']
                    perc = calculate_matches(entry, adm)
                    document = {
                        'pid': pid,
                        'adm_type': survey['results'][page]['admAlignment'],
                        'score': perc,
                        'text_scenario': scenario_id,
                        'adm_author': survey['results'][page]['admAuthor'],
                        'adm_alignment_target': adm_target,
                        'adm_alignment': alignment,
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
    

def find_adm(adm_collection, page, scenario, survey):
    adms = adm_collection.find({'evalNumber': 4, 'history.0.response.id': scenario, 'history.0.parameters.adm_name': survey['results'][page]['admName']})
    adm = None
    for x in adms:
        if x['history'][len(x['history'])-1]['parameters']['target_id'] == survey['results'][page]['admTarget']:
            adm = x
            break
    if adm is None:
        print(f"No matching adm found for scenario {scenario} with adm {survey['results'][page]['admName']} at target {survey['results'][page]['admTarget']}")
        return None
    return adm


def send_document_to_mongo(match_collection, document):
    # do not send duplicate documents, make sure if one already exists, we just replace it
    found_docs = match_collection.find({'pid': document['pid'], 'adm_type': document['adm_type'], 'text_scenario': document['text_scenario'], 
                                                'adm_author': document['adm_author'], 'adm_alignment_target': document['adm_alignment_target'], 'adm_alignment': document['adm_alignment']})
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