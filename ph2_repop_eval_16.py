import requests
from decouple import config
from collections import defaultdict
import utils.db_utils as db_utils

MONGO_URL = config("MONGO_URL")
ADEPT_URL = config("ADEPT_URL")

EVAL_NUMBER = 16
SUBPOP_SCENARIO_ID = "April2026-subpopulation"
RESPONSE_URL = f"{ADEPT_URL}api/v1/response"
# combinedMostLeastAligned[0] = affiliation, [1] = merit
COMBINED_TARGETS = ["affiliation", "merit"]


def new_session():
    return requests.post(f"{ADEPT_URL}api/v1/new_session").text.replace('"', "").strip()


def get_kdmas(session_id, enable_subpop=None):
    params = {"session_id": session_id}
    if enable_subpop:
        params["enable_subpop"] = enable_subpop
    return requests.get(f"{ADEPT_URL}api/v1/computed_kdma_profile", params=params).json()


def most_least_aligned(session_id, targets, enable_subpop=None):
    """One get_ordered_alignment call per target (targets=[None] == skipKdmaFilter).
    Drops synthetic '-group-' rows exactly like the dashboard does."""
    responses = []
    for target in targets:
        params = {"session_id": session_id}
        if target:
            params["kdma_id"] = target
        if enable_subpop:
            params["enable_subpop"] = enable_subpop
        data = requests.get(f"{ADEPT_URL}api/v1/get_ordered_alignment", params=params).json()
        if isinstance(data, list):
            data = [o for o in data if not any("-group-" in str(k).lower() for k in o.keys())]
        responses.append({"target": target, "response": data})
    return responses


def extract_probes(document):
    probes = []
    for key, value in document.items():
        if isinstance(value, dict) and "questions" in value:
            probe = value["questions"].get(f"probe {key}", {})
            response = probe.get("response", "").replace(".", "")
            mapping = probe.get("question_mapping", {})
            if response in mapping:
                probes.append(
                    {
                        "probe": {
                            "choice": mapping[response]["choice"],
                            "probe_id": mapping[response]["probe_id"],
                        }
                    }
                )
    return probes


def process_pair(collection, group_key, docs):
    """AF-PS / MF-PS pair session: submit both docs, score with no kdma filter."""
    pair_sid = new_session()
    for document in docs:
        db_utils.send_probes(RESPONSE_URL, extract_probes(document), pair_sid, document["scenario_id"])

    mla = most_least_aligned(pair_sid, [None])  # skipKdmaFilter
    kdmas = get_kdmas(pair_sid)

    for document in docs:
        collection.update_one(
            {"_id": document["_id"]},
            {
                "$set": {
                    f"{group_key}_sessionId": pair_sid,
                    f"{group_key}_mostLeastAligned": mla,
                    f"{group_key}_kdmas": kdmas,
                }
            },
        )


def process_text_scenarios(mongo_db):
    collection = mongo_db["userScenarioResults"]
    text_scenarios = list(collection.find({"evalNumber": EVAL_NUMBER}))

    # group ALL docs by pid (subpopulation included -- it seeds the combined session)
    participant_groups = defaultdict(list)
    for result in text_scenarios:
        participant_groups[result["participantID"]].append(result)

    for participant_id, all_docs in participant_groups.items():
        subpop_doc = next((d for d in all_docs if d.get("scenario_id") == SUBPOP_SCENARIO_ID), None)
        documents = [d for d in all_docs if d.get("scenario_id") != SUBPOP_SCENARIO_ID]

        if not subpop_doc:
            print(f"Warning: Participant {participant_id} missing subpopulation document; skipping")
            continue
        if len(documents) < 4:
            print(f"Warning: Participant {participant_id} has {len(documents)} documents instead of 4")
            continue

        af_ps_docs = [d for d in documents if any(x in d.get("scenario_id", "") for x in ["AF", "PS"])]
        mf_ps_docs = [d for d in documents if any(x in d.get("scenario_id", "") for x in ["MF", "PS"])]
        if len(af_ps_docs) != 2 or len(mf_ps_docs) != 2:
            print(
                f"Warning: Participant {participant_id} does not have expected AF-PS and MF-PS groupings. "
                f"AF-PS: {len(af_ps_docs)}, MF-PS: {len(mf_ps_docs)}"
            )
            continue

        # --- combined session, seeded by the subpopulation scenario ---
        combined_sid = new_session()

        # subpop responses first, then read the (possibly changed) subpopulation
        db_utils.send_probes(RESPONSE_URL, extract_probes(subpop_doc), combined_sid, subpop_doc["scenario_id"])
        sub_pop_result = requests.get(
            f"{ADEPT_URL}api/v1/subpopulation", params={"session_id": combined_sid}
        ).json()

        # then all four regular scenarios into the same session
        for document in documents:
            db_utils.send_probes(RESPONSE_URL, extract_probes(document), combined_sid, document["scenario_id"])

        combined_mla = most_least_aligned(combined_sid, COMBINED_TARGETS, enable_subpop=sub_pop_result)
        combined_kdmas = get_kdmas(combined_sid, enable_subpop=sub_pop_result)

        # subpopulation doc: session id + (possibly updated) subpop result
        collection.update_one(
            {"_id": subpop_doc["_id"]},
            {"$set": {"combinedSessionId": combined_sid, "subPopResult": sub_pop_result}},
        )
        # regular docs: combined session id + combined alignment + kdmas
        for document in documents:
            collection.update_one(
                {"_id": document["_id"]},
                {
                    "$set": {
                        "combinedSessionId": combined_sid,
                        "combinedMostLeastAligned": combined_mla,
                        "combinedKdmas": combined_kdmas,
                    }
                },
            )

        # --- pair sessions ---
        process_pair(collection, "AF-PS", af_ps_docs)
        process_pair(collection, "MF-PS", mf_ps_docs)

        print(f"Processed text scenarios for participant {participant_id} (subpop={sub_pop_result})")


def run_obs(mongo_db):
    medics = mongo_db["admMedics"]
    adm_runs = list(medics.find({"evalNumber": EVAL_NUMBER}))

    for adm_run in adm_runs:
        elements = adm_run.get("elements") or []
        responses = elements[0].get("rows") if elements else None
        if not responses:
            print(f"Skipping {adm_run.get('name')}: no probe rows")
            continue

        scenario_id = responses[0]["scenario_id"]
        sid = new_session()

        probes = [
            {"probe": {"choice": response["choice_id"], "probe_id": response["probe_id"]}}
            for response in responses
        ]
        db_utils.send_probes(RESPONSE_URL, probes, sid, scenario_id)

        kdmas = get_kdmas(sid)

        # Oracle runs carry a subpop and must score against it; aligned ADMs don't.
        alignment_params = {"session_id": sid, "target_id": adm_run.get("target")}
        if adm_run.get("subpop"):
            alignment_params["enable_subpop"] = adm_run["subpop"]
        alignment_score = requests.get(
            f"{ADEPT_URL}api/v1/alignment/session", params=alignment_params
        ).json()

        medics.update_one(
            {"_id": adm_run["_id"]},
            {
                "$set": {
                    "admSessionId": sid,
                    "kdmas": kdmas,
                    "alignmentScore": alignment_score.get("score"),
                }
            },
        )
        print(f"Processed {adm_run.get('name')} - {scenario_id} -> session {sid}")


def gen_comp(mongo_db):
    text_scenario_collection = mongo_db["userScenarioResults"]
    delegation_collection = mongo_db["surveyResults"]
    comparison_collection = mongo_db["humanToADMComparison"]
    medic_collection = mongo_db["admMedics"]

    comparison_collection.delete_many({"evalNumber": EVAL_NUMBER})

    data_to_use = list(text_scenario_collection.find({"evalNumber": EVAL_NUMBER}))
    total_text_scenarios = len(data_to_use)
    current_text_scenario = 0

    for entry in data_to_use:
        current_text_scenario += 1
        print(f"Currently processing {current_text_scenario} of {total_text_scenarios} total text scenarios Evaluation {EVAL_NUMBER}.")

        scenario_id = entry.get("scenario_id")
        pid = entry.get("participantID")

        survey = list(delegation_collection.find({"results.pid": pid, "results.evalNumber": EVAL_NUMBER}))
        if len(survey) == 0:
            print(f"No survey found for {pid}")
            continue
        survey = survey[-1]

        # PS document has all three session ids I need, so just grab that
        ps2_doc = text_scenario_collection.find_one(
            {"participantID": pid, "evalNumber": EVAL_NUMBER, "scenario_id": {"$regex": "PS"}}
        )
        if not ps2_doc:
            print(f"No PS document found for {pid}")
            continue

        subpop_doc = text_scenario_collection.find_one(
            {"participantID": pid, "evalNumber": EVAL_NUMBER, "scenario_id": {"$regex": "subpopulation"}}
        )
        if not subpop_doc:
            print(f"No subpop document found for {pid}")
            continue

        participant_subpop = subpop_doc.get("subPopResult")

        for page in survey["results"]:
            if "Medic" not in page or " vs " in page:
                continue

            page_data = survey["results"][page]
            page_scenario = page_data.get("scenarioIndex")
            if not page_scenario:
                continue

            # figure out what session id to use
            if "MF-PS" in page_scenario:
                session_id = ps2_doc.get("MF-PS_sessionId")
            elif "AF-PS" in page_scenario:
                session_id = ps2_doc.get("AF-PS_sessionId")
            elif "MF-observe" in page_scenario or "AF-observe" in page_scenario:
                session_id = ps2_doc.get("combinedSessionId")
            else:
                # shouldnt happen
                print(f"Couldnt match page_scenario of {page_scenario}")
                continue

            if not session_id:
                print(f"No session ID found for {pid} page {page} scenario {page_scenario}")
                continue

            # Match text scenario attribute to medic scenario attribute
            scenario_attribute = next((x for x in ["MF", "SS", "PS", "AF"] if x in scenario_id), None)
            if scenario_attribute is None or scenario_attribute not in page_scenario:
                continue

            medic = medic_collection.find_one({"evalNumber": EVAL_NUMBER, "name": page})
            if not medic:
                print(f"No medic found for {page}")
                continue

            adm_session = medic.get("admSessionId")
            if not adm_session:
                print(f"No admSessionId for medic {page}")
                continue

            base_url = f"{ADEPT_URL}api/v1/alignment/compare_sessions"

            query_params = {
                "session_id_1": session_id,
                "session_id_2": adm_session,
            }

            # Only add optional params if they exist
            if medic["admName"] == "Oracle":
                if participant_subpop:
                    query_params["enable_subpop"] = participant_subpop

                query_params["kdma_filter"] = (
                    "affiliation" if "AF" in medic["scenarioIndex"] else "merit"
                )

            response = requests.get(base_url, params=query_params)

            if response.status_code != 200:
                print(f"Request failed: {response.status_code} - {response.text}")
                continue

            try:
                res = response.json()
            except Exception:
                print(f"Invalid JSON response: {response.text}")
                continue

            if res is not None and "score" in res:
                document = {
                    "pid": pid,
                    "score": res["score"],
                    "text_scenario": scenario_id,
                    "text_session_id": session_id.replace('"', "").strip(),
                    "adm_scenario": page_scenario,
                    "adm_session_id": adm_session,
                    "adm_alignment_target": page_data.get("admTarget"),
                    "evalNumber": EVAL_NUMBER,
                }

                if medic["admName"] == "Oracle":
                    document["oracle_subpop"] = page_data.get("subpop")
                    document["participant_subpop"] = participant_subpop

                send_document_to_mongo(comparison_collection, document)
            else:
                print(
                    f"Error getting comparison for {scenario_id} and {page_scenario} "
                    f"with text session {session_id} and adm session {adm_session}",
                    res,
                )

    print("Human to ADM comparison values added to database.")


def send_document_to_mongo(comparison_collection, document):
    # do not send duplicate documents; if one already exists, replace it
    found_docs = comparison_collection.find(
        {
            "pid": document["pid"],
            "text_scenario": document["text_scenario"],
            "adm_scenario": document["adm_scenario"],
            "evalNumber": document["evalNumber"],
            "text_session_id": document["text_session_id"],
            "adm_session_id": document["adm_session_id"],
            "adm_alignment_target": document["adm_alignment_target"],
        }
    )
    doc_found = False
    obj_id = ""
    for doc in found_docs:
        doc_found = True
        obj_id = doc["_id"]
        break
    if doc_found:
        comparison_collection.update_one({"_id": obj_id}, {"$set": document})
    else:
        comparison_collection.insert_one(document)

def opposite_subpop(subpop):
    return "B" if subpop == "A" else "A"


def populate_other_sub_kdma(mongo_db):
    collection = mongo_db["userScenarioResults"]
    text_scenarios = list(collection.find({"evalNumber": EVAL_NUMBER}))

    participant_groups = defaultdict(list)
    for result in text_scenarios:
        participant_groups[result["participantID"]].append(result)

    for participant_id, all_docs in participant_groups.items():
        subpop_doc = next((d for d in all_docs if d.get("scenario_id") == SUBPOP_SCENARIO_ID), None)
        documents = [d for d in all_docs if d.get("scenario_id") != SUBPOP_SCENARIO_ID]

        if not subpop_doc:
            print(f"Warning: Participant {participant_id} missing subpopulation document; skipping")
            continue

        subpop = subpop_doc.get("subPopResult")
        if not subpop:
            print(f"Warning: Participant {participant_id} has no subPopResult; skipping")
            continue
        other = opposite_subpop(subpop)

        combined_sid = subpop_doc.get("combinedSessionId") or next(
            (d.get("combinedSessionId") for d in documents if d.get("combinedSessionId")), None
        )
        if not combined_sid:
            print(f"Warning: Participant {participant_id} has no combinedSessionId; skipping")
            continue

        # KDMA profile from the combined session under the opposite subpopulation
        other_kdmas = get_kdmas(combined_sid, enable_subpop=other)

        for document in documents:
            collection.update_one(
                {"_id": document["_id"]},
                {"$set": {"otherSubKDMA": other_kdmas}},
            )

        print(f"Participant {participant_id}: otherSubKDMA from opposite subpop {other!r} (own {subpop!r})")

def main(mongo_db):
    # re run humans
    process_text_scenarios(mongo_db) 
    # re run observed adms
    run_obs(mongo_db)      
    #redo comparisons          
    gen_comp(mongo_db)
    # populates otherSubKDMA (used on participant-level)
    populate_other_sub_kdma(mongo_db)


if __name__ == "__main__":
    from pymongo import MongoClient

    MONGO_URL = config("MONGO_URL")
    client = MongoClient(MONGO_URL)
    mongoDB = client["dashboard"]
    main(mongoDB)