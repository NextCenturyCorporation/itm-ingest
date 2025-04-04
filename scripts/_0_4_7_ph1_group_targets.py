import requests
from decouple import config 

ADEPT_URL = config("ADEPT_URL")
ST_URL = config("ST_URL")

GROUP_TARGETS ={
    "202411541": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low",
        "qol-group-target-2-final-eval"
    ],
    "202411310": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low",
        "ADEPT-Phase1Eval-Moral judgement-Group-Low",
        "qol-group-target-2-final-eval"
    ],
    "202411311": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low"
    ],
    "202411536": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low",
        "ADEPT-Phase1Eval-Moral judgement-Group-Low"
    ],
    "202411315": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low",
        "ADEPT-Phase1Eval-Moral judgement-Group-Low"
    ],
    "202411559": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low",
        "vol-group-target-2-final-eval"
    ],
    "202411547": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low",
        "ADEPT-Phase1Eval-Moral judgement-Group-High",
        "vol-group-target-2-final-eval"
    ],
    "202411577": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low",
        "ADEPT-Phase1Eval-Moral judgement-Group-High"
    ],
    "202411350": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low",
        "ADEPT-Phase1Eval-Moral judgement-Group-Low",
        "qol-group-target-2-final-eval"
    ],
    "202411555": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low",
        "ADEPT-Phase1Eval-Moral judgement-Group-High",
        "vol-group-target-2-final-eval"
    ],
    "202411302": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low",
        "ADEPT-Phase1Eval-Moral judgement-Group-High",
        "qol-group-target-1-final-eval"
    ],
    "202411567": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low",
        "ADEPT-Phase1Eval-Moral judgement-Group-Low",
        "qol-group-target-2-final-eval",
        "vol-group-target-2-final-eval"
    ],
    "202411312": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low"
    ],
    "202411557": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low",
        "qol-group-target-2-final-eval"
    ],
    "202411560": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low",
        "ADEPT-Phase1Eval-Moral judgement-Group-Low"
    ],
    "202411369": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low"
    ],
    "202411338": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low",
        "ADEPT-Phase1Eval-Moral judgement-Group-High",
        "qol-group-target-2-final-eval"
    ],
    "202411314": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low",
        "ADEPT-Phase1Eval-Moral judgement-Group-Low",
        "vol-group-target-2-final-eval"
    ],
    "202411340": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low",
        "qol-group-target-1-final-eval"
    ],
    "202411514": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low",
        "ADEPT-Phase1Eval-Moral judgement-Group-Low"
    ],
    "202411544": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low",
        "qol-group-target-2-final-eval",
        "vol-group-target-1-final-eval"
    ],
    "202411561": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-Low",
        "ADEPT-Phase1Eval-Moral judgement-Group-Low"
    ],
    "202411545": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "qol-group-target-2-final-eval",
        "vol-group-target-1-final-eval"
    ],
    "202411334": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "ADEPT-Phase1Eval-Moral judgement-Group-Low",
        "qol-group-target-2-final-eval"
    ],
    "202411367": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "ADEPT-Phase1Eval-Moral judgement-Group-High",
        "qol-group-target-2-final-eval",
        "vol-group-target-1-final-eval"
    ],
    "202411351": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "ADEPT-Phase1Eval-Moral judgement-Group-Low",
        "qol-group-target-2-final-eval",
        "vol-group-target-2-final-eval"
    ],
    "202411353": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "ADEPT-Phase1Eval-Moral judgement-Group-Low",
        "vol-group-target-1-final-eval"
    ],
    "202411327": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "ADEPT-Phase1Eval-Moral judgement-Group-High",
        "qol-group-target-1-final-eval"
    ],
    "202411563": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "vol-group-target-1-final-eval"
    ],
    "202411358": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "ADEPT-Phase1Eval-Moral judgement-Group-Low",
        "qol-group-target-2-final-eval"
    ],
    "202411569": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "ADEPT-Phase1Eval-Moral judgement-Group-High"
    ],
    "202411570": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High"
    ],
    "202411554": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "ADEPT-Phase1Eval-Moral judgement-Group-High",
        "vol-group-target-1-final-eval"
    ],
    "202411572": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "ADEPT-Phase1Eval-Moral judgement-Group-High",
        "qol-group-target-1-final-eval"
    ],
    "202411333": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "ADEPT-Phase1Eval-Moral judgement-Group-Low"
    ],
    "202411579": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "ADEPT-Phase1Eval-Moral judgement-Group-High"
    ],
    "202411539": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "ADEPT-Phase1Eval-Moral judgement-Group-High"
    ],
    "202411363": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "vol-group-target-1-final-eval"
    ],
    "202411553": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "ADEPT-Phase1Eval-Moral judgement-Group-Low"
    ],
    "202411565": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "ADEPT-Phase1Eval-Moral judgement-Group-High"
    ],
    "202411581": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "ADEPT-Phase1Eval-Moral judgement-Group-High",
        "qol-group-target-2-final-eval",
        "vol-group-target-1-final-eval"
    ],
    "202411359": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "ADEPT-Phase1Eval-Moral judgement-Group-High"
    ],
    "202411580": [
        "ADEPT-Phase1Eval-Ingroup Bias-Group-High",
        "ADEPT-Phase1Eval-Moral judgement-Group-High",
        "vol-group-target-2-final-eval"
    ],
    "202411316": [
        "ADEPT-Phase1Eval-Moral judgement-Group-Low",
        "qol-group-target-2-final-eval"
    ],
    "202411346": [
        "ADEPT-Phase1Eval-Moral judgement-Group-Low",
        "qol-group-target-2-final-eval"
    ],
    "202411313": [
        "ADEPT-Phase1Eval-Moral judgement-Group-Low",
        "qol-group-target-1-final-eval",
        "vol-group-target-1-final-eval"
    ],
    "202411357": [
        "ADEPT-Phase1Eval-Moral judgement-Group-Low",
        "vol-group-target-2-final-eval"
    ],
    "202411543": [
        "ADEPT-Phase1Eval-Moral judgement-Group-Low",
        "qol-group-target-2-final-eval"
    ],
    "202411370": [
        "ADEPT-Phase1Eval-Moral judgement-Group-Low",
        "qol-group-target-2-final-eval"
    ],
    "202411578": [
        "ADEPT-Phase1Eval-Moral judgement-Group-High"
    ],
    "202411537": [
        "ADEPT-Phase1Eval-Moral judgement-Group-High",
        "qol-group-target-2-final-eval"
    ],
    "202411534": [
        "ADEPT-Phase1Eval-Moral judgement-Group-High",
        "qol-group-target-2-final-eval",
        "vol-group-target-1-final-eval"
    ],
    "202411550": [
        "ADEPT-Phase1Eval-Moral judgement-Group-High"
    ],
    "202411548": [
        "ADEPT-Phase1Eval-Moral judgement-Group-High"
    ],
    "202411546": [
        "qol-group-target-1-final-eval"
    ],
    "202411355": [
        "qol-group-target-2-final-eval",
        "vol-group-target-1-final-eval"
    ],
    "202411558": [
        "qol-group-target-2-final-eval"
    ],
    "202411562": [
        "vol-group-target-2-final-eval"
    ]
}

def main(mongoDB):
    text_scenario_collection = mongoDB['userScenarioResults']

    data_to_update = text_scenario_collection.find(
        {"evalNumber": 5}
    )
    for entry in data_to_update:
        scenario_id = entry.get('scenario_id')
        session_id = entry.get('combinedSessionId', entry.get('serverSessionId'))
        data_id = entry.get('_id')
        pid = entry.get('participantID')
        group_targets = {}
        if 'qol' in scenario_id or 'vol' in scenario_id:
            for x in GROUP_TARGETS.get(pid, []):
                if ('qol' in x and 'qol' in scenario_id) or ('vol' in x and 'vol' in scenario_id):
                    alignment = requests.get(f'{ST_URL}api/v1/alignment/session?session_id={session_id}&target_id={x}').json()
                    group_targets[x] = alignment.get('score')
        else:   
            mj_targets = requests.get(f'{ADEPT_URL}api/v1/get_ordered_alignment?session_id={session_id}&population=false&kdma_id=Moral%20judgement').json()
            io_targets = requests.get(f'{ADEPT_URL}api/v1/get_ordered_alignment?session_id={session_id}&population=false&kdma_id=Ingroup%20Bias').json()
            all_targets = mj_targets + io_targets
            for x in GROUP_TARGETS.get(pid, []):
                if 'ADEPT' in x:   
                    found = False
                    for obj in all_targets:
                        if x in obj:
                            group_targets[x] = obj[x]  
                            found = True
                            break
                    if not found:
                        print(f'Could not find target {x} for {pid}.')

        # create object to add/update in database
        if (len(list(group_targets.keys())) > 0):
            updates = {'group_targets': group_targets}
            text_scenario_collection.update_one({'_id': data_id}, {'$set': updates})

    print("All Phase 1 Group Target Alignments added to text scenario database.")

if __name__ == "__main__":
    from pymongo import MongoClient
    MONGO_URL = config('MONGO_URL')
    client = MongoClient(MONGO_URL)
    mongoDB = client['dashboard']
    main(mongoDB)