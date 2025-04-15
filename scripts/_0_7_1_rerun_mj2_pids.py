'''
https://nextcentury.atlassian.net/jira/software/projects/ITM/boards/116?assignee=60ba425da547eb00686ee0ce&selectedIssue=ITM-964

This script corrects an issue that existed with the kdma scoring for participants who saw the MJ2 text scenario.
The MJ2 scenario will be run again individually to recalculate Narrative kdma scores and replace with the ta1 session id
for comparison in other scripts. The two training scenarios will then be run along with the MJ2 scenario to recalculate
the participant's combined kdma scores, alignment, and session id. 
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
        for doc in documents:
            scenario_id = doc.get("scenario_id", "N/A")
            scenario_id = adept_scenario_map.get(scenario_id, scenario_id)

            submit_responses(doc, scenario_id, combined_sess, ADEPT_URL)

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

        combined_kdmas = get_kdma_value(combined_sess, ADEPT_URL)
        most_least_aligned = most_least(combined_sess)
        # replace combined kdmas of IO and Mj2 docs
        for doc in documents:
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
        if documents[0]["evalNumber"] > 4:
            comparison_docs = comparison_collec.find({"pid": pid, "text_scenario": {"$regex": "MJ2"}, "dre_server": {"$exists": False}})
            for doc in comparison_docs:
                if "Moral" in doc["adm_alignment_target"]:
                    res_new = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions_population?session_id_1_or_target_id={combined_sess}&session_id_2_or_target_id={doc["adm_session_id"]}&target_pop_id=ADEPT-DryRun-Moral%20judgement-Population-All').json()
                else:
                    res_new = requests.get(f'{ADEPT_URL}api/v1/alignment/compare_sessions_population?session_id_1_or_target_id={combined_sess}&session_id_2_or_target_id={doc["adm_session_id"]}&target_pop_id=ADEPT-DryRun-Ingroup%20Bias-Population-All').json()
                comparison_collec.update_one({"_id": doc['_id']}, {"$set": {"text_session_id": combined_sess, "score": res_new["score"]}})
                

    rerun0_6_8(mongo_db)


def most_least(session_id):
    targets = ["Moral judgement", "Ingroup Bias"]
    responses = []
    for target in targets:
        endpoint = "/api/v1/get_ordered_alignment"
        response = requests.get(
            f"{ADEPT_URL}{endpoint}",
            params={"session_id": session_id, "kdma_id": target},
        )

        responses.append({"target": target, "response": response.json()})
    return responses
