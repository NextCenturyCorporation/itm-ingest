from decouple import config 
import requests, sys


SERVER_URL = config("ADEPT_URL")

def main(mongo_db):
    '''
    Updates the database to include data from the P1E server using the old endpoints
    '''
    #### add delegator|target alignment values using P1E server, old endpoint ####
    text_collection = mongo_db['userScenarioResults']
    # we only want p1e and jan ADEPT eval (not training) scenarios
    p1e_text = text_collection.find({
        'evalNumber': {'$in': [5, 6]}, 
        'scenario_id': {'$regex': 'adept-eval'}
    }) 
    targets = ['ADEPT-DryRun-Moral judgement-0.2', 'ADEPT-DryRun-Ingroup Bias-0.2', 'ADEPT-DryRun-Moral judgement-0.3', 'ADEPT-DryRun-Ingroup Bias-0.3', 'ADEPT-DryRun-Moral judgement-0.4', 
               'ADEPT-DryRun-Ingroup Bias-0.4', 'ADEPT-DryRun-Moral judgement-0.5', 'ADEPT-DryRun-Ingroup Bias-0.5', 'ADEPT-DryRun-Moral judgement-0.6', 'ADEPT-DryRun-Ingroup Bias-0.6', 
               'ADEPT-DryRun-Moral judgement-0.7', 'ADEPT-DryRun-Ingroup Bias-0.7', 'ADEPT-DryRun-Moral judgement-0.8', 'ADEPT-DryRun-Ingroup Bias-0.8']
    text_count = text_collection.count_documents({
        'evalNumber': {'$in': [5, 6]}, 
        'scenario_id': {'$regex': 'adept-eval'}
    })
    completed = 0
    for entry in p1e_text:
        sys.stdout.write(f"\rRunning alignment on text scenario {completed+1} of {text_count}")
        completed += 1
        sys.stdout.flush()
        if 'distance_based_most_least_aligned' in entry:
            continue
        sid = entry['combinedSessionId']
        # we need to build up the mostLeastAligned for the old endpoints
        mla = [{'target': 'Moral judgement', 'response': []}, {'target': 'Ingroup Bias', 'response': []}]
        for target in targets:
            alignment = requests.get(f'{SERVER_URL}api/v1/alignment/session?session_id={sid}&target_id={target}&population=false').json()
            align_obj = {}
            # take out '.' to match the other mostLeastAligned
            align_obj[target.replace('.', '')] = float(alignment['score'])
            if 'Moral' in target:
                mla[0]['response'].append(align_obj)
            else:
                mla[1]['response'].append(align_obj)
        # sort mla from most to least aligned, as the name suggests
        mla[0]['response'] = sorted(mla[0]['response'], key=lambda x: list(x.values())[0], reverse=True)
        mla[1]['response'] = sorted(mla[1]['response'], key=lambda x: list(x.values())[0], reverse=True)
        # update the database with this data
        entry['distance_based_most_least_aligned'] = mla
        text_collection.update_one({'_id': entry['_id']}, {'$set': entry})
        
    print('\n')

    #### add delegator|adm comparison alignment values using P1E server, old endpoint ####
    comparison_collection = mongo_db['humanToADMComparison']
    p1e_comparisons = comparison_collection.find({
        'evalNumber': {'$in': [5, 6]}, 
        'text_scenario': {'$regex': 'adept-eval'},
        'dre_server': {'$exists': False}
    })
    comparison_count = comparison_collection.count_documents({
        'evalNumber': {'$in': [5, 6]}, 
        'text_scenario': {'$regex': 'adept-eval'},
        'dre_server': {'$exists': False}
    })
    completed = 0
    for comparison in p1e_comparisons:
        sys.stdout.write(f"\rRunning alignment comparison on text/adm combo {completed+1} of {comparison_count}")
        completed += 1
        sys.stdout.flush()
        # if 'distance_based_score' in comparison:
        #     continue
        if 'Moral' in comparison['adm_alignment_target']:
            alignment = requests.get(f'{SERVER_URL}api/v1/alignment/compare_sessions?session_id_1={comparison["text_session_id"]}&session_id_2={comparison["adm_session_id"]}&kdma_filter=Moral%20judgement').json()
        else:
            alignment = requests.get(f'{SERVER_URL}api/v1/alignment/compare_sessions?session_id_1={comparison["text_session_id"]}&session_id_2={comparison["adm_session_id"]}&kdma_filter=Ingroup%20Bias').json()
        comparison['distance_based_score'] = alignment['score']
        comparison_collection.update_one({'_id': comparison['_id']}, {'$set': comparison})

    print('\n')

    #### add adm alignment values using P1E server, old endpoint ####
    adm_collection = mongo_db['admTargetRuns']
    p1e_adms = adm_collection.find({
        'evalNumber': 5, 
        'scenario': {'$regex': 'DryRunEval'}
    })
    adm_count = adm_collection.count_documents({
        'evalNumber': 5, 
        'scenario': {'$regex': 'DryRunEval'}
    })
    completed = 0
    for adm in p1e_adms:
        sys.stdout.write(f"\rRunning alignment on adm {completed+1} of {adm_count}")
        completed += 1
        sys.stdout.flush()
        if 'distance_based_score' in adm['history'][-1]['response']:
            continue
        alignment = requests.get(f"{SERVER_URL}api/v1/alignment/session?session_id={adm['history'][-1]['parameters']['session_id']}&target_id={adm['alignment_target']}&population=false").json()
        adm['history'][-1]['response']['distance_based_score'] = alignment['score']
        adm_collection.update_one({'_id': adm['_id']}, {'$set': adm})
    
    print('\nFinished adding distance-based scores to the database')