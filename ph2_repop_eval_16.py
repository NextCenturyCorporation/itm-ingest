import requests
from decouple import config
from collections import defaultdict
import utils.db_utils as db_utils

MONGO_URL = config("MONGO_URL")
ADEPT_URL = config("ADEPT_URL")

SUBPOP_SCENARIO_ID = "April2026-subpopulation"


def main(mongo_db):
    text_scenarios = mongo_db["userScenarioResults"].find({"evalNumber": 16})
    adm_runs = mongo_db["admTargetRuns"].find({"evalNumber": 16})

    # group text scenarios by pid (ignoring subpopulation documents entirely)
    participant_groups = defaultdict(list)
    for result in text_scenarios:
        if result.get("scenario_id") == SUBPOP_SCENARIO_ID:
            continue
        participant_groups[result["participantID"]].append(result)

    for participant_id, documents in participant_groups.items():
        if len(documents) < 4:
            print(
                f"Warning: Participant {participant_id} has {len(documents)} documents instead of 4"
            )
            continue

        af_ps_docs = [d for d in documents if any(x in d.get("scenario_id", "") for x in ["AF", "PS"])]
        mf_ps_docs = [d for d in documents if any(x in d.get("scenario_id", "") for x in ["MF", "PS"])]

        if len(af_ps_docs) != 2 or len(mf_ps_docs) != 2:
            print(
                f"Warning: Participant {participant_id} does not have expected AF-PS and MF-PS groupings. "
                f"AF-PS: {len(af_ps_docs)}, MF-PS: {len(mf_ps_docs)}"
            )
            continue

        combined_sid = requests.post(f"{ADEPT_URL}api/v1/new_session").text.replace('"', "").strip()
        for document in documents:
            old_sid = document.get("combinedSessionId")
            probes = extract_probes(document)
            db_utils.send_probes(
                f"{ADEPT_URL}api/v1/response", probes, combined_sid, document["scenario_id"]
            )
            mongo_db["userScenarioResults"].update_one(
                {"_id": document["_id"]}, {"$set": {"combinedSessionId": combined_sid}}
            )
            if old_sid:
                mongo_db["humanToADMComparison"].update_many(
                    {"text_session_id": old_sid},
                    {"$set": {"text_session_id": combined_sid}}
                )

        # --- AF-PS pair session ---
        af_ps_sid = requests.post(f"{ADEPT_URL}api/v1/new_session").text.replace('"', "").strip()
        for document in af_ps_docs:
            old_sid = document.get("AF-PS_sessionId")
            probes = extract_probes(document)
            db_utils.send_probes(
                f"{ADEPT_URL}api/v1/response", probes, af_ps_sid, document["scenario_id"]
            )
            mongo_db["userScenarioResults"].update_one(
                {"_id": document["_id"]}, {"$set": {"AF-PS_sessionId": af_ps_sid}}
            )
            if old_sid:
                mongo_db["humanToADMComparison"].update_many(
                    {"text_session_id": old_sid},
                    {"$set": {"text_session_id": af_ps_sid}}
                )

        # --- MF-PS pair session ---
        mf_ps_sid = requests.post(f"{ADEPT_URL}api/v1/new_session").text.replace('"', "").strip()
        for document in mf_ps_docs:
            old_sid = document.get("MF-PS_sessionId")
            probes = extract_probes(document)
            db_utils.send_probes(
                f"{ADEPT_URL}api/v1/response", probes, mf_ps_sid, document["scenario_id"]
            )
            mongo_db["userScenarioResults"].update_one(
                {"_id": document["_id"]}, {"$set": {"MF-PS_sessionId": mf_ps_sid}}
            )
            if old_sid:
                mongo_db["humanToADMComparison"].update_many(
                    {"text_session_id": old_sid},
                    {"$set": {"text_session_id": mf_ps_sid}}
                )

    for adm_run in adm_runs:
        # skip over the synthetic runs
        if 'history' not in adm_run:
            continue

        # delegation adm runs
        if 'observe' not in adm_run.get("scenario", "").lower():
            continue

        old_session_id = adm_run.get("results", {}).get("ta1_session_id", "")

        sid = requests.post(f"{ADEPT_URL}api/v1/new_session").text.replace('"', "").strip()

        # probably not needed but better to update the admMedics collection as well
        corresponding_medic = mongo_db["admMedics"].find_one(
            {"admSessionId": old_session_id}
        )

        probes = []
        for entry in adm_run["history"]:
            if entry["command"] == "Respond to TA1 Probe":
                probe = entry["parameters"]
                probes.append(
                    {
                        "probe": {
                            "choice": probe["choice"],
                            "probe_id": probe["probe_id"],
                        }
                    }
                )

        db_utils.send_probes(
            f"{ADEPT_URL}api/v1/response", probes, sid, adm_run.get("scenario", "")
        )

        if corresponding_medic:
            mongo_db["admMedics"].update_one(
                {"_id": corresponding_medic["_id"]}, {"$set": {"admSessionId": sid}}
            )

        # updates every reference to the old session id in the adm run document
        mongo_db["admTargetRuns"].update_one(
            {"_id": adm_run["_id"]},
            {
                "$set": {
                    "results.ta1_session_id": sid,
                    "history.$[sessionId].response": sid,
                    "history.$[probeAlign].parameters.session_id": sid,
                    "history.$[sessionAlign].parameters.session_id": sid,
                }
            },
            array_filters=[
                {"sessionId.command": "TA1 Session ID"},
                {"probeAlign.command": "TA1 Probe Response Alignment"},
                {"sessionAlign.command": "TA1 Session Alignment"},
            ],
        )

        if old_session_id:
            mongo_db["humanToADMComparison"].update_many(
                {"adm_session_id": old_session_id},
                {"$set": {"adm_session_id": sid}}
            )


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


if __name__ == "__main__":
    from pymongo import MongoClient

    MONGO_URL = config("MONGO_URL")
    client = MongoClient(MONGO_URL)
    mongoDB = client["dashboard"]
    main(mongoDB)