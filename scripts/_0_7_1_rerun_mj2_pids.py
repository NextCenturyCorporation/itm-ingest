'''
https://nextcentury.atlassian.net/jira/software/projects/ITM/boards/116?assignee=60ba425da547eb00686ee0ce&selectedIssue=ITM-964

This script corrects an issue that existed with the kdma scoring for participants who saw the MJ2 text scenario.
The MJ2 scenario will be run again individually to recalculate Narrative kdma scores and replace with the ta1 session id
for comparison in other scripts. The two training scenarios will then be run along with the MJ2 scenario to recalculate
the participant's combined kdma scores, alignment, and session id. 

The DRE results (that included MJ2) are run through both the DRE server and the PH1 server. The scores nested inside of their
survey results are then adjusted to reflect the new values (these are pulled for the rq134 table). The comparison scores for DRE are also
then recalculated. 
'''


from scripts._0_5_7_add_Narr_nonNarr_kdmas import submit_responses
from scripts._0_5_7_add_Narr_nonNarr_kdmas import get_kdma_value
from scripts._0_6_8_adept_p1e_old_endpoints import main as rerun0_6_8
import requests
from decouple import config

adept_scenario_map = {
    "phase1-adept-eval-MJ2": "DryRunEval-MJ2-eval",
    "phase1-adept-eval-MJ4": "DryRunEval-MJ4-eval",
    "phase1-adept-eval-MJ5": "DryRunEval-MJ5-eval",
    "phase1-adept-train-MJ1": "DryRunEval.MJ1",
    "phase1-adept-train-IO1": "DryRunEval.IO1",
}

ADEPT_URL = config("ADEPT_URL")
ADEPT_DRE_URL = config("ADEPT_DRE_URL")


def main(mongo_db):
    text_collec = mongo_db["userScenarioResults"]
    comparison_collec = mongo_db["humanToADMComparison"]

    query = {"evalNumber": {"$gte": 4}, "scenario_id": {"$regex": "DryRun|adept"}}

    adept_res = text_collec.find(query)

    participant_ids = set()
    for result in adept_res:
        pid = result["participantID"]
        participant_ids.add(pid)

    participant_documents = {}

    for pid in participant_ids:
        participant_docs = text_collec.find({"participantID": pid})
        filtered_docs = []
        for doc in participant_docs:
            scenario_id = doc.get("scenario_id", "").lower()
            if "qol" not in scenario_id and "vol" not in scenario_id:
                filtered_docs.append(doc)
        participant_documents[pid] = filtered_docs

    group = 0
    for pid, documents in participant_documents.items():
        group += 1
        print(f"processing group {group}/{len(participant_documents)}")
        has_mj2 = any("MJ2" in doc.get("scenario_id", "") for doc in documents)
        if not has_mj2:
            print("skipping group because no MJ2 document")
            # skip if no mj2
            continue
        
        session = requests.post(f"{ADEPT_URL}/api/v1/new_session")
        combined_sess = session.text.replace('"', "").strip()

        dre_combined_sess = None
        if documents[0]["evalNumber"] == 4:
            dre_sess = requests.post(f"{ADEPT_DRE_URL}/api/v1/new_session")
            dre_combined_sess = dre_sess.text.replace('"', "").strip()

        for doc in documents:
            scenario_id = doc.get("scenario_id", "N/A")
            scenario_id = adept_scenario_map.get(scenario_id, scenario_id)

            submit_responses(doc, scenario_id, combined_sess, ADEPT_URL)

            if dre_combined_sess != None:
                submit_responses(doc, scenario_id, dre_combined_sess, ADEPT_DRE_URL)

            if "MJ2" in scenario_id:
                # mj2 needs narr scores and session replaced as well
                narr_sess = requests.post(f"{ADEPT_URL}/api/v1/new_session")
                narr_sess_id = narr_sess.text.replace('"', "").strip()
                submit_responses(doc, scenario_id, narr_sess_id, ADEPT_URL)
                kdmas = get_kdma_value(narr_sess_id, ADEPT_URL)

                text_collec.update_one(
                    {"_id": doc["_id"]},
                    {
                        "$set": {"ph1NarrId": narr_sess_id, "individual_kdma": kdmas},
                        "$unset": {"dreNarrId": ""},
                    },
                )

                if doc.get("evalNumber") == 4:
                    dre_narr_sess = requests.post(f"{ADEPT_DRE_URL}/api/v1/new_session")
                    dre_narr_sess_id = dre_narr_sess.text.replace('"', "").strip()
                    submit_responses(doc, scenario_id, dre_narr_sess_id, ADEPT_DRE_URL)
                    kdmas = get_kdma_value(dre_narr_sess_id, ADEPT_DRE_URL)
                    text_collec.update_one(
                    {"_id": doc["_id"]},
                    {
                        "$set": {"dreNarrId": dre_narr_sess_id, "individual_kdma": kdmas},
                    },
                )

        combined_kdmas = get_kdma_value(combined_sess, ADEPT_URL)
        most_least_aligned = most_least(combined_sess, ADEPT_URL)

        dre_combined_kdmas = None
        dre_most_least_aligned = None
        if documents[0]["evalNumber"] == 4:
            dre_combined_kdmas = get_kdma_value(dre_combined_sess, ADEPT_DRE_URL)
            dre_most_least_aligned = most_least(dre_combined_sess, ADEPT_DRE_URL)
        
        for doc in documents:
            if doc.get("evalNumber") == 4:
                text_collec.update_one(
                    {"_id": doc["_id"]},
                    {
                        "$set": {
                            "ph1SessionId": combined_sess,
                            "combinedSessionId": dre_combined_sess,
                            "mostLeastAligned": dre_most_least_aligned,
                            "ph1MostLeastAligned": most_least_aligned,
                            "kdmas": dre_combined_kdmas
                        },
                        "$unset": {
                            "distance_based_most_least_aligned": ""
                        },
                    },
                )
            else:
                text_collec.update_one(
                    {"_id": doc["_id"]},
                    {
                        "$set": {
                            "kdmas": combined_kdmas,
                            "combinedSessionId": combined_sess,
                            "mostLeastAligned": most_least_aligned,
                        },
                        "$unset": {
                            "distance_based_most_least_aligned": "",
                            "dreSessionId": "",
                        },
                    },
                )

        # replace comparison scores
        comparison_docs = comparison_collec.find({"pid": pid, "text_scenario": {"$regex": "MJ2"}, "dre_server": {"$exists": False}}) if documents[0]['evalNumber'] > 4 else comparison_collec.find({"pid": pid, "text_scenario": {"$regex": "MJ2"}, "ph1_server": True})
        for doc in comparison_docs:
            if "Moral" in doc["adm_alignment_target"]:
                res_new = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions_population?session_id_1_or_target_id={combined_sess}&session_id_2_or_target_id={doc["adm_session_id"]}&target_pop_id=ADEPT-DryRun-Moral%20judgement-Population-All').json()
            else:
                res_new = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions_population?session_id_1_or_target_id={combined_sess}&session_id_2_or_target_id={doc["adm_session_id"]}&target_pop_id=ADEPT-DryRun-Ingroup%20Bias-Population-All').json()
            comparison_collec.update_one({"_id": doc['_id']}, {"$set": {"text_session_id": combined_sess, "score": res_new["score"]}})
        if documents[0]["evalNumber"] == 4:
            # update text session id for updated dre comparisons
            comparison_collec.update_many({"pid": pid, "text_scenario": {"$regex": "MJ2"}, "ph1_server": {"$exists": False}}, {"$set": {"text_session_id": dre_combined_sess}})
            fix_dre_survey_results(pid, mongo_db, most_least_aligned)
    
    rerun0_6_8(mongo_db)
    # update all dre comparison docs with kdma_filter endpoint
    comparison_docs = comparison_collec.find({"evalNumber": 4, "ph1_server": {"$exists": False}})
    for doc in comparison_docs:
        if "DryRun" in doc['text_scenario'] or "adept" in doc['text_scenario']:
            if "Moral" in doc["adm_alignment_target"]:
                res_new = requests.get(f'{ADEPT_DRE_URL}api/v1/alignment/compare_sessions?session_id_1={doc["text_session_id"]}&session_id_2={doc["adm_session_id"]}&kdma_filter=Moral%20judgement').json()
            else:
                res_new = requests.get(f'{ADEPT_DRE_URL}api/v1/alignment/compare_sessions?session_id_1={doc["text_session_id"]}&session_id_2={doc["adm_session_id"]}&kdma_filter=Ingroup%20Bias').json()
            comparison_collec.update_one({"_id": doc['_id']}, {"$set": {"score": res_new["score"]}})


def most_least(session_id, url):
    targets = ["Moral judgement", "Ingroup Bias"]
    responses = []
    for target in targets:
        endpoint = "/api/v1/get_ordered_alignment"
        response = requests.get(
            f"{url}{endpoint}",
            params={"session_id": session_id, "kdma_id": target},
        )

        responses.append({"target": target, "response": response.json()})
    return responses

def fix_dre_survey_results(pid, mongo_db, ph1_most_least_aligned):
    survey_collection = mongo_db['surveyResults']
    survey = list(survey_collection.find({"results.Participant ID Page.questions.Participant ID.response": pid}))
    
    if len(survey) == 0:
        print(f"No survey found for {pid}")
        return
    
    survey = survey[-1] # get last survey entry for this pid
    updated = False
    
    for page_key, page_value in survey['results'].items():
        if isinstance(page_value, dict) and 'Medic' in page_key and ' vs ' not in page_key:
            if 'scenarioIndex' not in page_value or 'qol' in page_value["scenarioIndex"] or 'vol' in page_value["scenarioIndex"]:
                continue
                
            if 'admTarget' not in page_value:
                continue
            
            target = page_value['admTarget']
            kdma_type = "Moral judgement" if "Moral judgement" in target else "Ingroup Bias"
            target_list = next((entry for entry in ph1_most_least_aligned if entry.get('target') == kdma_type), None)
            
            if not target_list:
                print(f"No target list found for {kdma_type}")
                continue
                
            target_list = target_list["response"]
            
            new_score = None
            for entry in target_list:
                for key in entry:
                    if target in key:
                        new_score = entry[key]
                        break
                if new_score is not None:
                    break
            
            if new_score is None:
                print(f"Didn't find new score for {target}")
                continue
            
            page_value["ph1TxtAlignment"] = new_score
            updated = True
            print(f"Updated ph1TxtAlignment for pid: {pid}, {page_key} with target {target} to {new_score}")
    
    if updated:
        result = survey_collection.update_one({'_id': survey['_id']}, {'$set': {'results': survey['results']}})
        if result.matched_count > 0:
            print(f"Successfully updated survey document for {pid}")
        else:
            print(f"Failed to update survey document for {pid}")