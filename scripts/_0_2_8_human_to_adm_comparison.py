import requests

ADEPT_URL = "https://darpaitm.caci.com/adept/"
ST_URL = "https://darpaitm.caci.com/soartech/" 

ST_PROBES = {
    "qol-dre-1-eval": ['4.2', '4.3', '4.6', '4.7', '4.10', 'qol-dre-train2-Probe-11'],
    "qol-dre-2-eval": ['qol-dre-2-eval-Probe-2', 'qol-dre-2-eval-Probe-3', 'qol-dre-2-eval-Probe-6', 'qol-dre-2-eval-Probe-7', 'qol-dre-2-eval-Probe-10', 'qol-dre-2-eval-Probe-11'],
    "qol-dre-3-eval": ['qol-dre-3-eval-Probe-2', 'qol-dre-3-eval-Probe-3', 'qol-dre-3-eval-Probe-6', 'qol-dre-3-eval-Probe-7', 'qol-dre-3-eval-Probe-10', 'qol-dre-3-eval-Probe-11'],
    "vol-dre-1-eval": ['4.2', '4.3', '4.6', '4.7', '4.10', 'vol-dre-train2-Probe-11'],
    "vol-dre-2-eval": ['vol-dre-2-eval-Probe-2', 'vol-dre-2-eval-Probe-3', 'vol-dre-2-eval-Probe-6', 'vol-dre-2-eval-Probe-7', 'vol-dre-2-eval-Probe-10', 'vol-dre-2-eval-Probe-11'],
    "vol-dre-3-eval": ['vol-dre-3-eval-Probe-2', 'vol-dre-3-eval-Probe-3', 'vol-dre-3-eval-Probe-6', 'vol-dre-3-eval-Probe-7', 'vol-dre-3-eval-Probe-10', 'vol-dre-3-eval-Probe-11']
}

AD_PROBES = {
    "DryRunEval-IO2-eval": ['Probe 4', 'Probe 8', 'Probe 9', 'Probe 9-B.1', 'Probe 9-A.1', 'Probe 10'],
    "DryRunEval-MJ2-eval": ['Probe 2B-1', 'Probe 2A-1', 'Response 3-B.2-B-gauze-v', 'Response 3-B.2-B-gauze-s', 'Response 3-B.2-A-gauze-v', 'Response 3-B.2-A-gauze-s', 'Probe 5', 'Probe 5-A.1', 'Probe 5-B.1', 'Probe 6', 'Probe 7'],
    "DryRunEval-IO4-eval": ['Probe 6', 'Probe 7', 'Probe 8', 'Probe 10'],
    "DryRunEval-MJ4-eval": ['Probe 1', 'Probe 2 kicker', 'Probe 2 passerby', 'Probe 2-A.1', 'Probe 2-D.1', 'Probe 2-D.1-B.1', 'Probe 3', 'Probe 3-A.1', 'Probe 3-B.1', 'Probe 9', 'Response 10-B', 'Response 10-C', 'Probe 10-A.1'],
    "DryRunEval-IO5-eval": ['Probe 7', 'Probe 8', 'Probe 8-A.1', 'Probe 8-A.1-A.1', 'Probe 9', 'Probe 9-A.1', 'Probe 9-B.1', 'Probe 9-C.1'],
    "DryRunEval-MJ5-eval": ['Probe 1', 'Probe 1-A.1', 'Probe 1-B.1', 'Probe 2', 'Response 2-A.1-B', 'Response 2-B.1-B', 'Response 2-B.1-B-gauze-u', 'Response 2-A.1-B-gauze-sp', 'Probe 2-A.1-A.1', 'Probe 2-B.1-A.1', 'Probe 2-A.1-B.1-A.1', 'Probe 2-B.1-B.1-A.1', 'Probe 3', 'Probe 4']
}

def compare_probes(mongoDB):
    text_scenario_collection = mongoDB['userScenarioResults']
    delegation_collection = mongoDB['surveyResults']
    comparison_collection = mongoDB['humanToADMComparison']
    medic_collection = mongoDB['admMedics']
    adm_collection = mongoDB["test"]
    del_adm_runs_collection = mongoDB['delegationADMRuns']

    data_to_use = text_scenario_collection.find(
        {"evalNumber": 4}
    )

    for entry in data_to_use:
        scenario_id = entry.get('scenario_id')
        if 'MJ1' in scenario_id or 'IO1' in scenario_id:
            # ignore test scenarios from adept
            continue
        session_id = entry.get('combinedSessionId', entry.get('serverSessionId'))
        pid = entry.get('participantID')
        survey = list(delegation_collection.find({"results.Participant ID Page.questions.Participant ID.response": pid}))
        if len(survey) == 0:
            print(f"No survey found for {pid}")
            continue
        survey = survey[-1] # get last survey entry for this pid
        for page in survey['results']:
            if 'Medic' in page and ' vs ' not in page:
                page_scenario = survey['results'][page]['scenarioIndex']
                # handle ST scenario, only compare QOL vs QOL and VOL vs VOL
                if ('qol' in scenario_id and 'qol' in page_scenario) or ('vol' in scenario_id and 'vol' in page_scenario):
                    # find the adm session id that matches the medic shown in the delegation survey
                    adm = find_adm(medic_collection, adm_collection, page, page_scenario, survey)
                    if adm is None:
                        continue
                    adm_session = adm['history'][len(adm['history'])-1]['parameters']['session_id']
                    # create ST query param
                    query_param = f"session_1={session_id}&session_2={adm_session}"
                    for probe_id in ST_PROBES[scenario_id]:
                        query_param += f"&session1_probes={probe_id}"
                    for probe_id in ST_PROBES[page_scenario]:
                        query_param += f"&session2_probes={probe_id}"
                    # get comparison score
                    res = requests.get(f'{ST_URL}api/v1/alignment/session/subset?{query_param}').json()
                    # send document to mongo
                    if res is not None and 'score' in res:
                        document = {
                            'pid': pid,
                            'adm_type': survey['results'][page]['admAlignment'],
                            'score': res['score'],
                            'text_scenario': scenario_id,
                            'text_session_id': session_id,
                            'adm_scenario': page_scenario,
                            'adm_session_id': adm_session,
                            'adm_author': survey['results'][page]['admAuthor'],
                            'adm_alignment_target': survey['results'][page]['admTarget'],
                            'evalNumber': 4
                        }
                        send_document_to_mongo(comparison_collection, document)
                        
                    else:
                        print('Error:', res)

                elif ('DryRunEval' in scenario_id and 'DryRunEval' in page_scenario):
                    adm = find_adm(medic_collection, adm_collection, page, page_scenario.replace('IO', 'MJ'), survey)
                    if adm is None:
                        continue
                    adm_target = adm['history'][len(adm['history'])-1]['parameters']['target_id']
                    found_mini_adm = del_adm_runs_collection.find_one({'target': adm_target, 'scenario': page_scenario.replace('IO', 'MJ'), 'adm_name': survey['results'][page]['admName']})
                    if found_mini_adm is None:
                        # get new adm session
                        probe_ids = AD_PROBES[page_scenario] # this is where IO/MJ comes into play - choosing the probes
                        probe_responses = []
                        for x in adm['history']:
                            if x['command'] == 'Respond to TA1 Probe':
                                if x['parameters']['choice'] in probe_ids or x['parameters']['probe_id'] in probe_ids:
                                    probe_responses.append(x['parameters'])
                        found_mini_adm = mini_adm_run(del_adm_runs_collection, probe_responses, adm_target, survey['results'][page]['admName'])
                    # get comparison score
                    res = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions?session_id_1={session_id}&session_id_2={found_mini_adm["session_id"]}').json()
                    # send document to mongo
                    if res is not None and 'score' in res:
                        document = {
                            'pid': pid,
                            'adm_type': survey['results'][page]['admAlignment'],
                            'score': res['score'],
                            'text_scenario': scenario_id,
                            'text_session_id': session_id.replace('"', "").strip(),
                            'adm_scenario': page_scenario,
                            'adm_session_id': found_mini_adm["session_id"],
                            'adm_author': survey['results'][page]['admAuthor'],
                            'adm_alignment_target': survey['results'][page]['admTarget'],
                            'evalNumber': 4
                        }
                        send_document_to_mongo(comparison_collection, document)

    print("Human to ADM comparison values added to database.")


def mini_adm_run(collection, probes, target, adm_name):
    adept_sid = requests.post(f'{ADEPT_URL}/api/v1/new_session').text.replace('"', "").strip()
    scenario = None
    for x in probes:
        requests.post(f'{ADEPT_URL}/api/v1/response', json={
            "response": {
                "choice": x['choice'],
                "justification": x["justification"],
                "probe_id": x['probe_id'],
                "scenario_id": x['scenario_id'],
            },
            "session_id": adept_sid
        })
        scenario = x['scenario_id']
    alignment = requests.get(f'{ADEPT_URL}/api/v1/alignment/session?session_id={adept_sid}&target_id={target}&population=false').json()
    doc = {'session_id': adept_sid, 'probes': probes, 'alignment': alignment, 'target': target, 'scenario': scenario, 'adm_name': adm_name, 'evalNumber': 4}
    collection.insert_one(doc)
    return doc


def find_adm(medic_collection, adm_collection, page, page_scenario, survey):
    adm_session = medic_collection.find_one({'evalNumber': 4, 'name': page})['admSession']
    adms = adm_collection.find({'evalNumber': 4, 'history.0.parameters.session_id': adm_session, 'history.0.response.id': page_scenario, 'history.0.parameters.adm_name': survey['results'][page]['admName']})
    adm = None
    for x in adms:
        if x['history'][len(x['history'])-1]['parameters']['target_id'] == survey['results'][page]['admTarget']:
            adm = x
            break
    if adm is None:
        print(f"No matching adm found for scenario {page_scenario} with adm {survey['results'][page]['admName']} (session {adm_session})")
        return None
    return adm


def send_document_to_mongo(comparison_collection, document):
    # do not send duplicate documents, make sure if one already exists, we just replace it
    found_docs = comparison_collection.find({'pid': document['pid'], 'adm_type': document['adm_type'], 'text_scenario': document['text_scenario'], 'adm_scenario': document['adm_scenario'],
                                                'text_session_id': document['text_session_id'], 'adm_session_id': document['adm_session_id'], 'adm_author': document['adm_author'], 'adm_alignment_target': document['adm_alignment_target']})
    doc_found = False
    obj_id = ''
    for doc in found_docs:
        doc_found = True
        obj_id = doc['_id']
        break
    if doc_found:
        comparison_collection.update_one({'_id': obj_id}, {'$set': document})
    else:
        comparison_collection.insert_one(document)