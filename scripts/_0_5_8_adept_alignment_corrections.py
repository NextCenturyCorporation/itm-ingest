import requests, sys, copy
import utils.db_utils as db_utils
from decouple import config 

AD_PROBES = {
    "DryRunEval-IO2-eval": ['Probe 8', 'Probe 9', 'Probe 9-B.1', 'Probe 9-A.1', 'Probe 10'], # Probe 4 removed from list for recalculation
    "DryRunEval-MJ2-eval": ['Probe 2B-1', 'Probe 2A-1', 'Response 3-B.2-B-gauze-v', 'Response 3-B.2-B-gauze-s', 'Response 3-B.2-A-gauze-v', 'Response 3-B.2-A-gauze-s', 'Probe 5', 'Probe 5-A.1', 'Probe 5-B.1', 'Probe 6', 'Probe 7'],
    "DryRunEval-IO4-eval": ['Probe 6', 'Probe 7', 'Probe 8', 'Probe 10'],
    "DryRunEval-MJ4-eval": ['Probe 1', 'Probe 2 kicker', 'Probe 2 passerby', 'Probe 2-A.1', 'Probe 2-D.1', 'Probe 2-D.1-B.1', 'Probe 3', 'Probe 3-A.1', 'Probe 3-B.1', 'Probe 9', 'Response 10-B', 'Response 10-C', 'Probe 10-A.1'],
    "DryRunEval-IO5-eval": ['Probe 7', 'Probe 8', 'Probe 9', 'Probe 9-A.1', 'Probe 9-B.1', 'Probe 9-C.1'], # Probe 8-A.1 and 8-A.1-A.1 removed from list for recalculation
    "DryRunEval-MJ5-eval": ['Probe 1', 'Probe 1-A.1', 'Probe 1-B.1', 'Probe 2', 'Response 2-A.1-B', 'Response 2-B.1-B', 'Response 2-B.1-B-gauze-u', 'Response 2-A.1-B-gauze-sp', 'Probe 2-A.1-A.1', 'Probe 2-B.1-A.1', 'Probe 2-A.1-B.1-A.1', 'Probe 2-B.1-B.1-A.1', 'Probe 3', 'Probe 4']
}

def main(mongoDB):
    # ph1 server
    correct_alignments(mongoDB, 4, False)
    correct_alignments(mongoDB, 5, False)
    correct_alignments(mongoDB, 6, False)
    # dre server
    correct_alignments(mongoDB, 4, True)
    correct_alignments(mongoDB, 5, True)
    correct_alignments(mongoDB, 6, True)

def correct_alignments(mongoDB, EVAL_NUMBER=4, DRE_SERVER=True):
    print(f'\n\033[36mStarting ADEPT recalculation for eval {EVAL_NUMBER} using the {"DRE" if DRE_SERVER else "PH1"} server\033[0m', flush=True)
    if not DRE_SERVER:
        ADEPT_URL = config('ADEPT_URL')
    else:
        ADEPT_URL = config("ADEPT_DRE_URL")

    text_scenario_collection = mongoDB['userScenarioResults']
    delegation_collection = mongoDB['surveyResults']
    medic_collection = mongoDB['admMedics']
    adm_collection = mongoDB["admTargetRuns"]
    del_adm_runs_collection = mongoDB['delegationADMRuns']
    comparisons = mongoDB['humanToADMComparison']

    data_to_use = text_scenario_collection.find(
        {"evalNumber": EVAL_NUMBER}
    )

    data_count = text_scenario_collection.count_documents(
        {"evalNumber": EVAL_NUMBER}
    )

    for idx, entry in enumerate(data_to_use):
        scenario_id = entry.get('scenario_id')
        if 'MJ1' in scenario_id or 'IO1' in scenario_id:
            # ignore test scenarios from adept
            continue

        # get the correct session id based on the server
        session_id = entry.get('combinedSessionId', entry.get('serverSessionId'))
        if (EVAL_NUMBER == 5 or EVAL_NUMBER == 6) and DRE_SERVER:
            session_id = entry.get('dreSessionId')
        if EVAL_NUMBER == 4 and not DRE_SERVER:
            session_id = entry.get('ph1SessionId')

        pid = entry.get('participantID')
        
        # only get completed surveys!
        survey = list(delegation_collection.find({"results.Participant ID Page.questions.Participant ID.response": pid, "results.Post-Scenario Measures": {'$exists': True}}))
        if len(survey) == 0:
            continue
        
        survey = survey[-1] # get last survey entry for this pid

        # get human to adm comparisons from delegation survey adms
        for page in survey['results']:
            if 'Medic' in page and ' vs ' not in page:
                page_scenario = survey['results'][page]['scenarioIndex']
                
                # ignore ST
                if (('qol' in scenario_id and 'qol' in page_scenario) or ('vol' in scenario_id and 'vol' in page_scenario)):
                    continue

                elif (('DryRunEval' in scenario_id or 'adept' in scenario_id) and ('DryRunEval' in page_scenario or 'adept' in page_scenario)):
                    sys.stdout.write(f"\rComputing comparison on {scenario_id} for {pid} (entry {idx} out of {data_count})              ")
                    sys.stdout.flush()
                    # adept requested changes to IO2, MJ5, and IO5 (details here: https://nextcentury.atlassian.net/browse/ITM-873)
                    if 'IO2' not in page_scenario and 'IO5' not in page_scenario and 'MJ5' not in page_scenario:
                        continue

                    # get the adm that was used in the delegation survey
                    adm = db_utils.find_adm_from_medic(EVAL_NUMBER if EVAL_NUMBER != 6 else 5, medic_collection, adm_collection, page, page_scenario.replace('IO', 'MJ'), survey)
                    if adm is None:
                        continue
                    adm_target = adm['history'][len(adm['history'])-1]['parameters']['target_id']

                    # NEW DATA (get mini adm with updated probes)
                    run_dre_through_ph1 = (not DRE_SERVER) and EVAL_NUMBER == 4
                    run_ph1_through_dre = DRE_SERVER and (EVAL_NUMBER == 5 or EVAL_NUMBER == 6)
                    adm_to_find = {'target': adm_target, 'scenario': page_scenario.replace('IO', 'MJ'), 'adm_name': survey['results'][page]['admName'], 
                                    'evalNumber': EVAL_NUMBER, 'recalculation': True}
                    if run_dre_through_ph1:
                        adm_to_find['dre_ph1_run'] = True
                    else:
                        adm_to_find['dre_ph1_run'] = {"$exists": False}
                    if run_ph1_through_dre and EVAL_NUMBER == 5:
                        adm_to_find['ph1_in_dre_server_run'] = True
                    else:
                        adm_to_find['ph1_in_dre_server_run'] = {"$exists": False}
                    if run_ph1_through_dre and EVAL_NUMBER == 6:
                        adm_to_find['jan_in_dre_server_run'] = True
                    else:
                        adm_to_find['jan_in_dre_server_run'] = {"$exists": False}
                    # do not duplicate entry in database
                    found_mini_adm_new = del_adm_runs_collection.find_one(adm_to_find)
                    if found_mini_adm_new is None:
                        probe_ids = copy.deepcopy(AD_PROBES[page_scenario])
                        probe_responses = []
                        io2_probe4_response = None
                        io5_probe8_response = None
                        probe_scenario_id = None
                        for x in adm['history']:
                            if x['command'] == 'Respond to TA1 Probe':
                                probe_id = x['parameters']['probe_id']
                                choice_id = x['parameters']['choice']
                                probe_scenario_id = x['parameters']['scenario_id']
                                
                                # if probe 4 or 4-b.1 was 'A', make that an 'A' for 4-b.1-b.1 instead (IO2 only!)
                                if 'IO2' in page_scenario and ((probe_id == 'Probe 4' and choice_id == 'Response 4-A') \
                                or (probe_id == 'Probe 4-B.1' and choice_id == 'Response 4-B.1-A')):
                                    io2_probe4_response = x['parameters']
                                    io2_probe4_response['probe_id'] = 'Probe 4-B.1-B.1'
                                    io2_probe4_response['choice'] = 'Response 4-B.1-B.1-A'
                                
                                # if probe 4-b.1-b.1 is reached (in which case the above if statement will never be hit), use the response
                                if 'IO2' in page_scenario and probe_id == 'Probe 4-B.1-B.1':
                                    io2_probe4_response = x['parameters']

                                # if probe 8-a.1 was 'b', make that a 'b' for 8-a.1-a.1 instead
                                if 'IO5' in page_scenario and probe_id == 'Probe 8-A.1' and choice_id == 'Response 8-A.1-B':
                                    io5_probe8_response = x['parameters']
                                    io5_probe8_response['probe_id'] = 'Probe 8-A.1-A.1'
                                    io5_probe8_response['choice'] = 'Response 8-A.1-A.1-B'

                                # add the rest of the delegation probes as expected
                                if choice_id in probe_ids or probe_id in probe_ids:
                                    probe_responses.append(x['parameters'])
                        # add adjusted io2 probes
                        if 'IO2' in page_scenario:
                            # for IO2, Probe 4 and 4-B1 get choice B
                            probe_responses.insert(0, {'probe_id': 'Probe 4', 'choice': 'Response 4-B', 'justification': 'recalculation - forced probe', 'scenario_id': probe_scenario_id})
                            probe_responses.insert(1, {'probe_id': 'Probe 4-B.1', 'choice': 'Response 4-B.1-B', 'justification': 'recalculation - forced probe', 'scenario_id': probe_scenario_id})
                            # Probe 4-B.1-B.1 gets A if Probe 4 or 4-B.1 were A, otherwise it gets its normal answer
                            probe_responses.insert(2, io2_probe4_response)
                        # add adjusted io5 probes
                        if 'IO5' in page_scenario and io5_probe8_response is not None:
                            # Add Probe 8-A.1-A.1 back in, using B if 8-A.1 was B (and therefore A1A1 was never hit)
                            probe_responses.insert(2, io5_probe8_response)
                        # add adjusted mj5 probes 
                        if 'MJ5' in page_scenario:
                            good_probes = ['Probe 2-A.1-A.1', 'Probe 2-B.1-A.1', 'Probe 2-A.1-B.1-A.1', 'Probe 2-B.1-B.1-A.1']
                            scoreless_springer_responses = ['Response 2-A.1-B', 'Response 2-A.1-B-gauze-sp']
                            scoreless_upton_responses = ['Response 2-B.1-B', 'Response 2-B.1-B-gauze-u']
                            found_probe = False
                            response_to_use = None
                            for probe in probe_responses:
                                # check if any of the scored first-treatment probes were hit
                                if probe['probe_id'] in good_probes:
                                    found_probe = True
                                    break
                                # if none of the scored first-treatment probes were hit, we need to know who was treated first
                                # to fake-enter a scored probe
                                if probe['choice'] in scoreless_upton_responses + scoreless_springer_responses:
                                    response_to_use = 'upton' if probe['choice'] in scoreless_upton_responses else 'springer'
                            # create a new probe with a score based on the unscored probes if none with scores exist
                            if not found_probe:
                                probe_to_add = {'probe_id': 'Probe 2-A.1-A.1', 'choice': ('Response 2-A.1-A.1-A' if response_to_use == 'springer' else 'Response 2-A.1-A.1-B'), 
                                                'justification': 'recalculation - forced probe', 'scenario_id': probe_scenario_id}
                                probe_responses.insert(4, probe_to_add)

                        # get the mini adm data (session id and score is what we'll use from it)
                        found_mini_adm_new = db_utils.mini_adm_run(EVAL_NUMBER, del_adm_runs_collection, probe_responses, adm_target, survey['results'][page]['admName'], run_dre_through_ph1, run_ph1_through_dre, True)

                    # get new comparison score
                    res_new = None
                    if DRE_SERVER:
                        res_new = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions?session_id_1={session_id}&session_id_2={found_mini_adm_new["session_id"]}').json()
                    else:
                        if 'Moral' in adm_target:
                            res_new = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions_population?session_id_1_or_target_id={session_id}&session_id_2_or_target_id={found_mini_adm_new["session_id"]}&target_pop_id=ADEPT-DryRun-Moral%20judgement-Population-All').json()
                        else:
                            res_new = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions_population?session_id_1_or_target_id={session_id}&session_id_2_or_target_id={found_mini_adm_new["session_id"]}&target_pop_id=ADEPT-DryRun-Ingroup%20Bias-Population-All').json()
                    if res_new is not None and 'score' in res_new:
                        # all scores found, write the new data to the database
                        score = res_new['score']
                        doc_to_find = {'pid': pid, 'evalNumber': EVAL_NUMBER, 'adm_alignment_target': adm_target, 'text_session_id': session_id, 'text_scenario': scenario_id, 
                                       'adm_scenario': page_scenario, 'adm_type': survey['results'][page]['admAlignment'], 'adm_author': survey['results'][page]['admAuthor'],
                                       'probe_subset': {'$exists': False}}
                        if run_ph1_through_dre:
                            doc_to_find['dre_server'] = True
                        if run_dre_through_ph1:
                            doc_to_find['ph1_server'] = True
                        found_doc = comparisons.find_one(doc_to_find)
                        counted_docs = comparisons.count_documents(doc_to_find)
                        if counted_docs > 1:
                            print('Found multiple documents to update:', doc_to_find)
                        if found_doc:
                            comparisons.update_one({'_id': found_doc['_id']}, {'$set': {'score': score, 'adm_session_id': found_mini_adm_new['session_id']}})
                        else:
                            print('Could not find document to update:', doc_to_find)
                    else:
                        print(f'\nError getting comparison for scenarios {scenario_id} and {page_scenario} with text session {session_id} and adm session {found_mini_adm_new["session_id"]}', res_new)
    
    print(f'\n\033[36mCompleted ADEPT recalculation for eval {EVAL_NUMBER} using the {"DRE" if DRE_SERVER else "PH1"} server\033[0m', flush=True)

