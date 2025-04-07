from decouple import config 
import requests, os, csv, sys
from scripts._0_6_5_setup_p2e1 import main as rerun_aligned
from scripts._0_6_7_cleanup_adm_results import main as update_adm_names

ADEPT_URL = config("ADEPT_URL")

BASELINE_NAME = "ALIGN-ADM-OutlinesBaseline-ADEPT"

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
    # ensure all new baseline adms are updated properly
    update_adm_names(mongo_db)
    # rerun the aligned kitware experiment with the ph1 server, distance-based endpoints
    rerun_aligned(mongo_db)
   
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


    # reset baselines in kdma database (avoid duplicates)
    multi_kdmas = mongo_db['multiKdmaData']
    multi_kdmas.delete_many({"admName": BASELINE_NAME})

    # get the first of each mj2, mj4, and mj5 baseline adm run - all others should be duplicates
    all_adms = mongo_db['admTargetRuns']
    scenarios = ["DryRunEval-MJ2-eval", "DryRunEval-MJ4-eval", "DryRunEval-MJ5-eval"]
    session_map = {"AD1": None, "AD2": None, "AD3": None}
    kdmas = {"mjAD1": -1, "mjAD2": -1, "mjAD3": -1, "ioAD1": -1, "ioAD2": -1, "ioAD3": -1}
    kdma_count = 0
    mj_sum = 0
    io_sum = 0
    for x in scenarios:
        scenario_id = "AD1" if '2' in x else "AD2" if '4' in x else "AD3"
        baseline = all_adms.find_one({'evalNumber': 7, "adm_name": BASELINE_NAME, "scenario": x})
        session_id = baseline['history'][-1]['parameters']['session_id'] if baseline else None
        session_map[scenario_id] = session_id
        adm_kdmas = baseline['history'][-1]['response']['kdma_values'] if baseline else None
        if adm_kdmas is not None:
            mj_kdma = adm_kdmas[0]['value'] if adm_kdmas[0]['kdma'] == 'Moral judgement' else adm_kdmas[1]['value']
            io_kdma = adm_kdmas[1]['value'] if adm_kdmas[1]['kdma'] == 'Ingroup Bias' else adm_kdmas[0]['value']
            kdmas["mj" + scenario_id] = mj_kdma
            kdmas["io" + scenario_id] = io_kdma
            mj_sum += mj_kdma
            io_sum += io_kdma
            kdma_count += 1

    # go through every human target to fill multi kdma db with baselines
    completed = 0
    for line in text_kdmas:
        sys.stdout.write(f"\rAnalyzing line {completed+1} of {len(text_kdmas)}")
        sys.stdout.flush()
        pid = line[header.index('PID')]
        human_data = get_human_data(pid, mongo_db)
        human_type = line[header.index('Type')]
        new_doc = {
            'admName': BASELINE_NAME, 
            'evalNumber': 7,
            'pid': pid,
            'humanScenario': human_data['scenario'], 
            'targetType': human_type,
            'mjTarget': float(line[header.index('MJ')]), 
            'ioTarget': float(line[header.index('IO')]), 
            'mjAD1_kdma': kdmas["mjAD1"], 
            'mjAD2_kdma': kdmas["mjAD2"], 
            'mjAD3_kdma': kdmas["mjAD3"], 
            'mjAve_kdma': mj_sum / max(1, kdma_count), 
            'ioAD1_kdma': kdmas["ioAD1"], 
            'ioAD2_kdma': kdmas["ioAD2"], 
            'ioAD3_kdma': kdmas["ioAD3"], 
            'ioAve_kdma': io_sum / max(1, kdma_count), 
            'AD1_align': -1,
            'AD2_align': -1,
            'AD3_align': -1,
            'ave_align': -1
        }
        text_session_id = human_data['overall']
        if human_type == 'narr':
            text_session_id = human_data['narr']
        elif human_type == 'train':
            text_session_id = human_data['train']
        align_count = 0
        align_sum = 0
        for scenario_id in session_map:
            if session_map[scenario_id] is None:
                continue
            res = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions?session_id_1={text_session_id}&session_id_2={session_map[scenario_id]}').json()
            # store comparison in correct spot using {scenario_id} like lines 104-105
            if 'score' in res:
                new_doc[f'{scenario_id}_align'] = res['score']
                align_sum += res['score']
                align_count += 1
            else:
                print(f"Error getting comparison score for {text_session_id} and {session_map[scenario_id]} (pid = {pid}, type = {human_type}) - {res}")
        
        new_doc["ave_align"] = align_sum / max(1, align_count)
        multi_kdmas.insert_one(new_doc)
        completed += 1

    print("\nMulti-KDMA Data collection has been updated with baselines.")


def get_human_data(pid, mongo_db):
    '''
    Takes in the pid to find.
    Returns the name of the scenario the human completed along with their
    3 relevant session ids (overall, train, and narr from ph1 server)
    '''
    text_scenarios = mongo_db['userScenarioResults']
    matching_scenarios = text_scenarios.find({'participantID': pid,         
                                '$or': [
                                {'scenario_id': {'$regex': 'DryRunEval'}}, 
                                {'scenario_id': {'$regex': 'adept'}}
    ]})
    scenario = None
    overall = None
    train = None
    narr = None
    for match in matching_scenarios:
        scenario = match['scenario_id'] if 'Eval-' in match['scenario_id'] or 'adept-eval' in match['scenario_id'] else scenario
        if overall is None:
            overall = match.get('ph1SessionId', match.get('combinedSessionId'))
        if train is None:
            train = match.get('ph1TrainId', None)
        if narr is None:
            narr = match.get('ph1NarrId', None)

    # we expect all to exist because it should have been run in 065
    return {'scenario': scenario, 
            'overall': overall,
            'train': train, 
            'narr': narr}
