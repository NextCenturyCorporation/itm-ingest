from decouple import config 
import requests, os, csv, sys
import utils.db_utils as db_utils
from scripts._0_5_3_jan_eval_to_dre_server import main as update_dre_server

ADEPT_DRE_URL = config("ADEPT_DRE_URL")

SCENARIO_MAP = {
    'DryRunEval-MJ2-eval': 'AD1',
    'DryRunEval-MJ4-eval': 'AD2',
    'DryRunEval-MJ5-eval': 'AD3'
}

PH1_TO_DRE_MAP = {
    "phase1-adept-eval-MJ2": "DryRunEval-MJ2-eval",
    "phase1-adept-eval-MJ4": "DryRunEval-MJ4-eval",
    "phase1-adept-eval-MJ5": "DryRunEval-MJ5-eval",
    "phase1-adept-train-MJ1": "DryRunEval.MJ1",
    "phase1-adept-train-IO1": "DryRunEval.IO1"
}

def main(mongo_db):
    '''
    Goes through the adms to combine all multi-kdma results.
    Also calculates the comparison alignment between the human who generated the target 
    and the adm run against that "synthetic" target
    '''
    # run the jan_eval_to_dre_server script to make sure all jan eval text sessions have been sent to the dre server
    update_dre_server(mongo_db)
    # run the dev script to get text. store in list for easy indexing
    os.system('python3 dev_scripts/get_text_kdmas.py')
    f = open('text_kdmas.csv', 'r', encoding='utf-8')
    reader = csv.reader(f)
    header = next(reader)
    text_kdmas = []
    for line in reader:
        if len(line) > 2:  # Skip blank lines
            text_kdmas.append(line)
    # clean up csv file
    f.close()
    os.remove('text_kdmas.csv')


    # create a new DB to store all the data
    multi_kdmas = mongo_db['multiKdmaData']
    multi_kdmas.drop()

    all_adms = mongo_db['admTargetRuns']
    adept_adms = all_adms.find({'evalNumber': 7})

    # an "adm group" consists of 3 adms with the same name and target - one for each ADEPT scenario
    adm_groups = {}
    group_count = 0

    # generate the adm groups, organized by adm_name, then target_id
    for adm in adept_adms:
        history = adm['history']
        adm_name = history[0]['parameters']['adm_name']
        kdmas = history[-1]['response']['kdma_values']
        target_id = history[-1]['parameters']['target_id']
        if adm_name not in adm_groups:
            adm_groups[adm_name] = {}
        if target_id not in adm_groups[adm_name]:
            adm_groups[adm_name][target_id] = []
            group_count += 1
        adm_groups[adm_name][target_id].append(adm)

    completed_groups = 0
    for adm_name in adm_groups:
        for target_id in adm_groups[adm_name]:
            sys.stdout.write(f"\rAnalyzing ADM group {completed_groups+1} of {group_count}")
            target_mj = -1
            target_io = -1
            # get mj/io kdma target values to find matching human(s)
            unique_matching_lines = []
            for entry in adm_groups[adm_name][target_id][0]['history']:
                if entry['command'] == 'Alignment Target':
                    target_mj = entry['response']['kdma_values'][0]['value']
                    target_io = entry['response']['kdma_values'][1]['value']
                    unique_matching_lines = get_humans_with_kdmas(text_kdmas, header, target_mj, target_io, mongo_db)
                    break

            # run the comparison for all unique entries
            for match in unique_matching_lines:
                new_doc = {
                    'admName': adm_name, 
                    'evalNumber': 7,
                    'humanScenario': match['scenario'], 
                    'targetType': match['type'],
                    'mjTarget': float(target_mj), 
                    'ioTarget': float(target_io), 
                    'mjAD1_kdma': -1, 
                    'mjAD2_kdma': -1, 
                    'mjAD3_kdma': -1, 
                    'mjAve_kdma': -1, 
                    'ioAD1_kdma': -1, 
                    'ioAD2_kdma': -1, 
                    'ioAD3_kdma': -1, 
                    'ioAve_kdma': -1, 
                    'AD1_align': -1,
                    'AD2_align': -1,
                    'AD3_align': -1,
                    'ave_align': -1
                }
                mj_kdma_sum = 0
                io_kdma_sum = 0
                mj_kdma_count = 0
                io_kdma_count = 0
                align_sum = 0
                align_count = 0
                for adm in adm_groups[adm_name][target_id]:
                    history = adm['history']
                    
                    # get kdmas and averages for each scenario
                    sys.stdout.flush()
                    sys.stdout.write(f"\rAnalyzing ADM group {completed_groups+1} of {group_count} - get adm kdmas")
                    kdmas = history[-1]['response']['kdma_values']
                    mj_kdma = kdmas[0]['value'] if kdmas[0]['kdma'] == 'Moral judgement' else kdmas[1]['value']
                    io_kdma = kdmas[1]['value'] if kdmas[1]['kdma'] == 'Ingroup Bias' else kdmas[0]['value']
                    scenario = history[-1]['response']['alignment_source'][0]['scenario_id']
                    scenario_id = SCENARIO_MAP[scenario]
                    new_doc[f'mj{scenario_id}_kdma'] = mj_kdma
                    new_doc[f'io{scenario_id}_kdma'] = io_kdma
                    mj_kdma_sum += mj_kdma
                    io_kdma_sum += io_kdma
                    mj_kdma_count += 1
                    io_kdma_count += 1

                    # send ADMs to DRE server
                    sys.stdout.flush()
                    sys.stdout.write(f"\rAnalyzing ADM group {completed_groups+1} of {group_count} - send adms to dre server            ")
                    adm_session_id = create_dre_adm_session(adm, all_adms)
                    # get session id from dre server for text
                    text_session_id = None
                    # if 'overall', use session id from the match 
                    if match['type'] == 'overall':
                        text_session_id = match['dreCombinedSession']
                        if text_session_id is None:
                            print(f'Error getting dre session id for {match["pid"]}')
                    # if 'narr' or 'train', create new session id, send to dre endpoint AND STORE
                    else:
                        sys.stdout.flush()
                        sys.stdout.write(f"\rAnalyzing ADM group {completed_groups+1} of {group_count} - get individual text kdmas        ")
                        text_session_id = get_individual_text_session_id(mongo_db, match['pid'], match['type'])
                        if text_session_id is None:
                            print(f'Error getting individual dre session id for {match["pid"]} ({match["type"]})')
                    # get the comparison between the human and adm
                    sys.stdout.flush()
                    sys.stdout.write(f"\rAnalyzing ADM group {completed_groups+1} of {group_count} - get comparison (text|adm)       ")
                    sys.stdout.flush()
                    res = requests.get(f'{ADEPT_DRE_URL}api/v1/alignment/compare_sessions?session_id_1={text_session_id}&session_id_2={adm_session_id}').json()
                    # store comparison in correct spot using {scenario_id} like lines 104-105
                    if 'score' in res:
                        new_doc[f'{scenario_id}_align'] = res['score']
                        # update average alignment
                        align_sum += res['score']
                        align_count += 1
                    else:
                        print(f'Could not get comparison score for (text session {text_session_id}; adm session {adm_session_id})')
                    

                new_doc['mjAve_kdma'] = mj_kdma_sum / max(1, mj_kdma_count)
                new_doc['ioAve_kdma'] = io_kdma_sum / max(1, io_kdma_count)
                new_doc['ave_align'] = align_sum / max(1, align_count)

                multi_kdmas.insert_one(new_doc)
            completed_groups += 1
            sys.stdout.flush()


    print("Multi-KDMA Data collection has been created and populated.")
        

def get_humans_with_kdmas(text_kdmas, kdma_header, mj, io, mongo_db):
    '''
    Takes in the text_kdmas list along with an mj and io value to find.
    Returns a list of objects containing pids, their scenarios, the session type, 
    and session ids that match.
    There may be more than one matching entry for this kdma set.
    Ignore the ones with the same scenario and type (narr, eval, overall) 
    '''
    text_scenarios = mongo_db['userScenarioResults']
    matches = []
    for line in text_kdmas:
        line_mj = line[kdma_header.index('MJ')]
        line_io = line[kdma_header.index('IO')]
        if mj == line_mj and io == line_io:
            pid = line[kdma_header.index('PID')]
            matching_scenario = text_scenarios.find_one({'participantID': pid,         
                                     '$or': [
                                        {'scenario_id': {'$regex': 'DryRunEval-'}}, 
                                        {'scenario_id': {'$regex': 'adept-eval'}}
            ]})
            kdma_type = line[kdma_header.index('Type')]
            scenario = matching_scenario['scenario_id']
            # make sure only unique matches appear in the output (no two with the same type and same scenario)
            duplicate = False
            for match in matches:
                if match['type'] == kdma_type and match['scenario'] == scenario:
                    duplicate = True
                    break
            if not duplicate:
                # kdmas did not change between ph1 and dre servers, so just stick with dre session ids because that's the comparison endpoint we're using
                matches.append({
                    'pid': pid,
                    'type': kdma_type,
                    'scenario': scenario,
                    'dreCombinedSession': matching_scenario.get('dreSessionId', matching_scenario.get('combinedSessionId'))
                    })
    # this should never happen
    if len(matches) == 0:
        print(f'WARNING: Could not find match for MJ={mj}, IO={io}')

    return matches


def create_dre_adm_session(adm, adm_collection):
    '''
    Takes in an adm and sends the probes to the DRE server, storing the 
    session id back in the database (and returning it)
    '''
    history = adm['history']
    dre_session_id = history[-1]['parameters'].get('dreSessionId')
    if dre_session_id is not None:
        return dre_session_id
    # start new adept session
    adept_sid = requests.post(f'{ADEPT_DRE_URL}api/v1/new_session').text.replace('"', '').strip()
    probe_responses = []
    for x in history:
        if x['command'] == 'Respond to TA1 Probe':
            probe_responses.append(x['parameters'])
    send_probes(probe_responses, adept_sid)
    history[-1]['parameters']['dreSessionId'] = adept_sid
    adm_collection.update_one({'_id': adm['_id']}, {'$set': {'history': history}})
    return adept_sid


def send_probes(probe_responses, adept_sid):
    for x in probe_responses:
        requests.post(f'{ADEPT_DRE_URL}api/v1/response', json={
            "response": {
                "choice": x['choice'],
                "justification": x["justification"],
                "probe_id": x['probe_id'],
                "scenario_id": x['scenario_id'],
            },
            "session_id": adept_sid
        })


def get_individual_text_session_id(mongo_db, pid, type='narr'):
    '''
    Creates a session id either for eval only (narr) or training only (train).
    Sends the probe responses from the human to the adept server.
    Stores the session id in userScenarioResults.
    Returns the session id.
    '''
    type = type.lower()
    if type != 'narr' and type != 'train':
        print(f'Error: type must be "narr" or "train", but instead was {type}')
        return -1
    # find all text scenarios for this participant
    text_scenarios = mongo_db['userScenarioResults']
    entries = text_scenarios.find({'participantID': pid,         
                            '$or': [
                            {'scenario_id': {'$regex': 'DryRunEval'}}, 
                            {'scenario_id': {'$regex': 'adept'}}
                        ]})
    # get only training or eval scenarios based on 'type' parameter
    entries_to_use = []
    for e in entries:
        scenario = e['scenario_id']
        if type == 'train' and ('IO1' in scenario or 'MJ1' in scenario or 'train' in scenario):
            if 'dreTrainId' in e:
                return e['dreTrainId']
            entries_to_use.append(e)
        if type == 'narr' and ('MJ2' in scenario or 'MJ4' in scenario or 'MJ5' in scenario):
            if 'dreNarrId' in e:
                return e['dreNarrId']
            entries_to_use.append(e)


    # send all probes from that scenario to the server
    adept_sid = requests.post(f'{ADEPT_DRE_URL}api/v1/new_session').text.replace('"', '').strip()
    for entry in entries_to_use:
        probes = []
        for k in entry:
            if isinstance(entry[k], dict) and 'questions' in entry[k]:
                for valid_key in [f'probe {k}', f'probe {k}_conditional']:
                    probe_data = entry[k]['questions'].get(valid_key, {})
                    if 'response' in probe_data and 'question_mapping' in probe_data:
                        response = probe_data['response'].replace('.', '')
                        mapping = probe_data['question_mapping']
                        if response in mapping:
                            if isinstance(mapping[response]['choice'], list):
                                for c in mapping[response]['choice']:
                                    probes.append({'probe': {'choice': c, 'probe_id': mapping[response]['probe_id']}})
                            else:
                                probes.append({'probe': {'choice': mapping[response]['choice'], 'probe_id': mapping[response]['probe_id']}})
                        else:
                            print('could not find response in mapping!', response, list(mapping.keys()))
        # send probes to server
        scenario = PH1_TO_DRE_MAP[entry['scenario_id']] if entry['scenario_id'] in PH1_TO_DRE_MAP else entry['scenario_id']
        db_utils.send_probes(f'{ADEPT_DRE_URL}api/v1/response', probes, adept_sid, scenario)
        # store new individual session id (dre) in the database
        if type == 'narr':
            text_scenarios.update_one({'_id': entry['_id']}, {'$set': {'dreNarrId': adept_sid}})
        else:
            text_scenarios.update_one({'_id': entry['_id']}, {'$set': {'dreTrainId': adept_sid}})

    return adept_sid
