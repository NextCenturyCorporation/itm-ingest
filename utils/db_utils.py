import requests
from decouple import config 


def mini_adm_run(evalNumber, collection, probes, target, adm_name):
    ADEPT_URL = config("ADEPT_DRE_URL") if evalNumber == 4 else config('ADEPT_URL')
    adept_sid = requests.post(f'{ADEPT_URL}api/v1/new_session').text.replace('"', "").strip()
    scenario = None
    for x in probes:
        requests.post(f'{ADEPT_URL}api/v1/response', json={
            "response": {
                "choice": x['choice'],
                "justification": x["justification"],
                "probe_id": x['probe_id'],
                "scenario_id": x['scenario_id'],
            },
            "session_id": adept_sid
        })
        scenario = x['scenario_id']
    if evalNumber == 4:
        alignment = requests.get(f'{ADEPT_URL}api/v1/alignment/session?session_id={adept_sid}&target_id={target}&population=false').json()
    else:
        if 'Moral' in target:
            targets = requests.get(f'{ADEPT_URL}api/v1/get_ordered_alignment?session_id={adept_sid}&population=false&kdma_id=Moral%20judgement').json()
        else:
            targets = requests.get(f'{ADEPT_URL}api/v1/get_ordered_alignment?session_id={adept_sid}&population=false&kdma_id=Ingroup%20Bias').json()
        score = 0
        for t in targets:
            if list(t.keys())[0] == target:
                score = t[list(t.keys())[0]]
                break
        alignment = {'alignment_source': {'score': score}}
    doc = {'session_id': adept_sid, 'probes': probes, 'alignment': alignment, 'target': target, 'scenario': scenario, 'adm_name': adm_name, 'evalNumber': evalNumber}
    collection.insert_one(doc)
    return doc


def find_adm_from_medic(eval_number, medic_collection, adm_collection, page, page_scenario, survey):
    adm_session = medic_collection.find_one({'evalNumber': eval_number, 'name': page})['admSession']
    adms = adm_collection.find({'evalNumber': eval_number, 'history.0.parameters.session_id': adm_session, 'history.0.response.id': page_scenario, 'history.0.parameters.adm_name': survey['results'][page]['admName']})
    adm = None
    for x in adms:
        if x['history'][len(x['history'])-1]['parameters']['target_id'] == survey['results'][page]['admTarget']:
            adm = x
            break
    if adm is None:
        print(f"No matching adm found for scenario {page_scenario} with adm {survey['results'][page]['admName']} (session {adm_session})")
        return None
    return adm


def find_most_least_adm(eval_number, adm_collection, scenario, target, adm_name):
    adms = adm_collection.find({'evalNumber': eval_number,     '$or': [{'history.1.response.id': scenario}, {'history.0.response.id': scenario}], 'history.0.parameters.adm_name': adm_name})
    adm = None
    for x in adms:
        if x['history'][len(x['history'])-1]['parameters']['target_id'] == target:
            adm = x
            break
    if adm is None:
        print(f"No matching adm found for scenario {scenario} with adm {adm_name} at target {target}")
        return None
    return adm