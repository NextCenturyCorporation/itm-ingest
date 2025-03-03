import pandas as pd
import os
from pathlib import Path
import re
import requests
from decouple import config 

ADEPT_DRE_URL = config("ADEPT_DRE_URL")
ADEPT_P1_URL = config("ADEPT_URL")

PROBLEM_CODES = ['MJ5P3-Gauze', 'IO5P8', 'IO5P8-A', 'IO4P7', 'MJ4P2', 'MJ4P2-A']
CODE_TO_PROBE_ID = {
    'MJ5P3-Gauze': 'Probe 3',
    'IO5P8': 'Probe 8',
    'IO5P8-A': 'Probe 8-A.1',
    'IO4P7': 'Probe 7',
    'MJ4P2': ['Probe 2 kicker', 'Probe 2 passerby'],
    'MJ4P2-A': 'Probe 2-A.1'
}

AD_PROBES = {
    "DryRunEval-IO2-eval": ['Probe 4', 'Probe 8', 'Probe 9', 'Probe 9-B.1', 'Probe 9-A.1', 'Probe 10'],
    "DryRunEval-MJ2-eval": ['Probe 2B-1', 'Probe 2A-1', 'Response 3-B.2-B-gauze-v', 'Response 3-B.2-B-gauze-s', 'Response 3-B.2-A-gauze-v', 'Response 3-B.2-A-gauze-s', 'Probe 5', 'Probe 5-A.1', 'Probe 5-B.1', 'Probe 6', 'Probe 7'],
    "DryRunEval-IO4-eval": ['Probe 6', 'Probe 7', 'Probe 8', 'Probe 10'],
    "DryRunEval-MJ4-eval": ['Probe 1', 'Probe 2 kicker', 'Probe 2 passerby', 'Probe 2-A.1', 'Probe 2-D.1', 'Probe 2-D.1-B.1', 'Probe 3', 'Probe 3-A.1', 'Probe 3-B.1', 'Probe 9', 'Response 10-B', 'Response 10-C', 'Probe 10-A.1'],
    "DryRunEval-IO5-eval": ['Probe 7', 'Probe 8', 'Probe 8-A.1', 'Probe 8-A.1-A.1', 'Probe 9', 'Probe 9-A.1', 'Probe 9-B.1', 'Probe 9-C.1'],
    "DryRunEval-MJ5-eval": ['Probe 1', 'Probe 1-A.1', 'Probe 1-B.1', 'Probe 2', 'Response 2-A.1-B', 'Response 2-B.1-B', 'Response 2-B.1-B-gauze-u', 'Response 2-A.1-B-gauze-sp', 'Probe 2-A.1-A.1', 'Probe 2-B.1-A.1', 'Probe 2-A.1-B.1-A.1', 'Probe 2-B.1-B.1-A.1', 'Probe 3', 'Probe 4']
}

#regex stuff to handle sometimes 0.7 vs 07 in the targets in mongo collections
def normalize_target(target):
    if re.search(r'-\d{2}$', target):
        return re.sub(r'-(\d)(\d)$', r'-\1.\2', target)
    elif re.search(r'-\d\.\d$', target):
        return re.sub(r'-(\d)\.(\d)$', r'-\1\2', target)
    return target

def mini_adm_run_fixed(mongo_db, pid, scenario, adm_name, target, problem_probes, original_doc):
    adm_collection = mongo_db["test"]
    
    api_url = ADEPT_DRE_URL if original_doc.get('dre_server', False) else ADEPT_P1_URL

    original_target = target
    alt_target = normalize_target(target)
    
    test_scenario = scenario if 'IO' not in scenario else scenario.replace('IO', 'MJ')
    
    query = {
        'evalNumber': 5,
        'scenario': test_scenario,
        'alignment_target': {'$in': [original_target, alt_target]}
    }
    
    matching_adms = list(adm_collection.find(query))
    
    if not matching_adms:
        print(f"    No matching ADM found for PID {pid}, scenario: {test_scenario}, targets: [{original_target}, {alt_target}]")
        return None
    
    adm = matching_adms[0]
    
    # probe ids to incldue
    valid_probe_ids = []
    for scenario_key in AD_PROBES:
        if scenario_key in scenario:
            valid_probe_ids = AD_PROBES[scenario_key]
            break
    
    
    probe_responses = []
    skipped_probes = []
    filtered_probes = []
    
    for x in adm['history']:
        if x['command'] == 'Respond to TA1 Probe':
            probe_id = x['parameters']['probe_id']
            choice = x['parameters']['choice']
            
            is_valid_probe = False
            if probe_id in valid_probe_ids or choice in valid_probe_ids:
                is_valid_probe = True
            
            if not is_valid_probe:
                filtered_probes.append(f"{probe_id} (choice: {choice})")
                continue
                
            # skip if problem probe
            should_skip = False
            for problem_probe in problem_probes:
                if isinstance(problem_probe, list):
                    if probe_id in problem_probe or choice in problem_probe:
                        should_skip = True
                        skipped_probes.append(f"{probe_id} (choice: {choice})")
                        break
                else:
                    if probe_id == problem_probe or choice == problem_probe:
                        should_skip = True
                        skipped_probes.append(f"{probe_id} (choice: {choice})")
                        break
            
            if not should_skip:
                probe_responses.append(x['parameters'])

    print("      Probelm Probes Skipped:")
    for i, probe in enumerate(skipped_probes):
        print(f"      {i+1}. {probe}")

   
    adept_sid = requests.post(f'{api_url}api/v1/new_session').text.replace('"', "").strip()
    print(f"    Created new ADM session: {adept_sid}")
    
    # send proebs
    for i, x in enumerate(probe_responses):
        print(f"      Sending probe {i+1}/{len(probe_responses)}: {x['probe_id']} (choice: {x['choice']})")
        response = requests.post(f'{api_url}api/v1/response', json={
            "response": {
                "choice": x['choice'],
                "justification": x.get("justification", "justification"),
                "probe_id": x['probe_id'],
                "scenario_id": x['scenario_id'],
            },
            "session_id": adept_sid
        })
    
    # depends on dre or not scoring for comparison endpoint
    is_dre = original_doc.get('dre_server', False)        
    if is_dre:
        res = requests.get(f'{api_url}api/v1/alignment/compare_sessions?session_id_1={original_doc["text_session_id"]}&session_id_2={adept_sid}')
    else:
        target_pop_id = ""
        
        if 'Moral' in target:
            target_pop_id = "ADEPT-DryRun-Moral%20judgement-Population-All"
        else:
            target_pop_id = "ADEPT-DryRun-Ingroup%20Bias-Population-All"
            
        res = requests.get(f'{api_url}api/v1/alignment/compare_sessions_population?session_id_1_or_target_id={original_doc["text_session_id"]}&session_id_2_or_target_id={adept_sid}&target_pop_id={target_pop_id}')
        
    res_json = res.json()
    
    if res_json is not None and 'score' in res_json:
        updated_doc = original_doc.copy()
        updated_doc['score'] = res_json['score']
        updated_doc['truncation_error'] = True
        updated_doc['adm_session_id'] = adept_sid

        return updated_doc
    else:
        print(f"    Error getting comparison score")
        if res_json:
            print(f"    Response: {res_json}")
        return None

def main(mongo_db):
    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    root_dir = script_dir.parent
    excel_path = os.path.join(root_dir, 'jan_errors.xlsx')
    
    df = pd.read_excel(excel_path)
    
    comparisons = mongo_db['humanToADMComparison']
    
    adm_groups = [
        {
            'scenario': 'Set1 Scenario',
            'name': 'Set1, adm 1_name',
            'target': 'Set1, adm 1_target',
            'problems': 'Set1, adm 1 problems'
        },
        {
            'scenario': 'Set1 Scenario',
            'name': 'Set1, adm 2_name',
            'target': 'Set1, adm 2_target',
            'problems': 'Set1, adm 2 problems'
        },
        {
            'scenario': 'Set1 Scenario',
            'name': 'Set1, adm 3_name',
            'target': 'Set1, adm 3_target',
            'problems': 'Set1, adm 3 problems'
        },
        {
            'scenario': 'Set 2 Scenario',
            'name': 'Set 2, adm 1_name',
            'target': 'Set 2, adm 1_target',
            'problems': 'Set 2, adm 1 problems'
        },
        {
            'scenario': 'Set 2 Scenario',
            'name': 'Set 2, adm 2_name',
            'target': 'Set 2, adm 2_target',
            'problems': 'Set 2, adm 2 problems'
        },
        {
            'scenario': 'Set 2 Scenario',
            'name': 'Set 2, adm 3_name',
            'target': 'Set 2, adm 3_target',
            'problems': 'Set 2, adm 3 problems'
        }
    ]
    
    processed_pids = 0
    total_problem_adms = 0
    updated_documents = 0
    
    scenario_mapping = {
        'MJ2': 'DryRunEval-MJ2-eval',
        'MJ4': 'DryRunEval-MJ4-eval',
        'MJ5': 'DryRunEval-MJ5-eval',
        'IO2': 'DryRunEval-IO2-eval',
        'IO4': 'DryRunEval-IO4-eval',
        'IO5': 'DryRunEval-IO5-eval'
    }
    
    score_changes = []
    
    for _, row in df.iterrows():
        pid = str(row['PID']) 
        pid_has_problems = False
        
        for i, adm in enumerate(adm_groups):
            scenario_type = row.get(adm['scenario'], '')
            adm_name = row.get(adm['name'], '')
            adm_target = row.get(adm['target'], '')
            problem_text = row.get(adm['problems'], '')
            
            if pd.isna(adm_name) or pd.isna(adm_target) or pd.isna(scenario_type):
                continue
                
            found_problem_codes = []
            
            if isinstance(problem_text, str) and problem_text.strip():
                potential_codes = [code.strip() for code in problem_text.split(',')]
                
                for code in potential_codes:
                    if code in PROBLEM_CODES:
                        found_problem_codes.append(code)
            
            if found_problem_codes:
                if not pid_has_problems:
                    print(f"\nProcessing PID: {pid}")
                    pid_has_problems = True
                
                total_problem_adms += 1

                adm_author = "TAD" if "tad" in adm_name.lower() else "kitware"
    
                print(f"  Set {1 if i < 3 else 2}, ADM {(i % 3) + 1}:")
                print(f"    Scenario: {scenario_type}")
                print(f"    Name: {adm_name}")
                print(f"    Target: {adm_target}")
                print(f"    ADM Author: {adm_author}")
                print(f"    Matched Codes: {', '.join(found_problem_codes)}")
                
                adm_scenario = None
                for key, value in scenario_mapping.items():
                    if key in scenario_type:
                        adm_scenario = value
                        break

                
                target_query = adm_target
                
                base_query = {
                    "pid": pid,
                    "adm_alignment_target": target_query,
                    "adm_author": adm_author,
                    "evalNumber": 6,
                    "adm_scenario": adm_scenario
                }
                
                dre_query = base_query.copy()
                dre_query["dre_server"] = True
                dre_matching_docs = list(comparisons.find(dre_query))
                
                non_dre_query = base_query.copy()
                non_dre_query["$or"] = [{"dre_server": {"$exists": False}}, {"dre_server": False}]
                non_dre_matching_docs = list(comparisons.find(non_dre_query))
                
                # if no matches try the other target (0.8 vs 08)
                if not dre_matching_docs and not non_dre_matching_docs:
                    alt_target = normalize_target(target_query)
                    
                    dre_query["adm_alignment_target"] = alt_target
                    non_dre_query["adm_alignment_target"] = alt_target
                    
                    dre_matching_docs = list(comparisons.find(dre_query))
                    non_dre_matching_docs = list(comparisons.find(non_dre_query))
                
                all_matching_docs = dre_matching_docs + non_dre_matching_docs
                
                if all_matching_docs:
                    for doc in all_matching_docs:
                        doc_id = doc.get('_id')
                        doc_scenario = doc.get('adm_scenario', 'N/A')
                        current_score = doc.get('score', 'N/A')
                        is_dre = doc.get('dre_server', False)
                        print(f"      - Doc ID: {doc_id}")
                        print(f"        adm_scenario: {doc_scenario}")
                        print(f"        current score: {current_score}")
                        print(f"        dre_server: {is_dre}")
                        
   
                        problem_probe_ids = []
                        for code in found_problem_codes:
                            if code in CODE_TO_PROBE_ID:
                                if isinstance(CODE_TO_PROBE_ID[code], list):
                                    problem_probe_ids.extend(CODE_TO_PROBE_ID[code])
                                else:
                                    problem_probe_ids.append(CODE_TO_PROBE_ID[code])
                        
                        # exclude problem probes
                        print(f"      - Rerunning mini ADM without probes: {problem_probe_ids}")
                        updated_doc = mini_adm_run_fixed(
                            mongo_db, 
                            pid, 
                            doc_scenario if isinstance(doc_scenario, str) else adm_scenario, 
                            adm_name, 
                            doc.get('adm_alignment_target', target_query), 
                            problem_probe_ids, 
                            doc
                        )
                        
                        if updated_doc:
                            comparisons.update_one(
                                {"_id": doc_id}, 
                                {"$set": updated_doc}
                            )
                            
                            # track score changes
                            old_score = float(doc.get('score', 0))
                            new_score = float(updated_doc['score'])
                            score_change = new_score - old_score
                            score_changes.append({
                                'pid': pid,
                                'scenario': doc_scenario,
                                'old_score': old_score,
                                'new_score': new_score,
                                'change': score_change,
                                'percent_change': (score_change / old_score) * 100 if old_score != 0 else 0,
                                'is_dre': is_dre
                            })
                            
                            print(f"      - Updated document with new score: {new_score}, old score: {old_score}")
                            updated_documents += 1
                else:
                    print(f"    No matching documents found in MongoDB for this ADM")
        
        if pid_has_problems:
            processed_pids += 1
    
    if score_changes:
        avg_change = sum(item['change'] for item in score_changes) / len(score_changes)
        
        print(f"  Average score change: {avg_change:.4f}")
        
        dre_changes = [item for item in score_changes if item['is_dre']]
        non_dre_changes = [item for item in score_changes if not item['is_dre']]
        
        if dre_changes:
            avg_dre_change = sum(item['change'] for item in dre_changes) / len(dre_changes)
            print(f"  DRE server documents updated: {len(dre_changes)}, Average change: {avg_dre_change:.4f}")
        
        if non_dre_changes:
            avg_non_dre_change = sum(item['change'] for item in non_dre_changes) / len(non_dre_changes)
            print(f"  Non-DRE server documents updated: {len(non_dre_changes)}, Average change: {avg_non_dre_change:.4f}")
            
    print(f"  - Found {processed_pids} participants with problem ADMs")
    print(f"  - Identified {total_problem_adms} ADMs with relevant problem codes")
    print(f"  - Updated {updated_documents} MongoDB documents")