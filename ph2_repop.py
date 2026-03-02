"""
https://nextcentury.atlassian.net/browse/ITM-1085

This script takes all text based scenario results and adm runs of eval number 8 or greater
and repopulates the ADEPT server with the probe responses. This script is to be used if the
ADEPT server is not persisting session ids that are needed to generate comparison scores.
"""

import requests
from decouple import config
from collections import defaultdict
import utils.db_utils as db_utils

MONGO_URL = config("MONGO_URL")
ADEPT_URL = config("ADEPT_URL")


def main(mongo_db):
   text_scenarios = mongo_db["userScenarioResults"].find({"evalNumber": {"$gte": 15}})
   adm_runs = mongo_db["admTargetRuns"].find({"evalNumber": {"$gte": 15}})

   # group text scenarios by pid
   participant_groups = defaultdict(list)
   for result in text_scenarios:
       participant_groups[result["participantID"]].append(result)

   for participant_id, documents in participant_groups.items():
       if len(documents) < 4:
           print(
               f"Warning: Participant {participant_id} has {len(documents)} documents instead of 4"
           )
           continue

       # Separate documents into eval 15 groups: PS+AF share one session, MF+SS share another
       ps_af_docs = [d for d in documents if any(x in d.get("scenario_id", "") for x in ["PS", "AF"])]
       mf_ss_docs = [d for d in documents if any(x in d.get("scenario_id", "") for x in ["MF", "SS"])]
       mf_docs = [d for d in documents if "MF" in d.get("scenario_id", "")]

       if len(ps_af_docs) != 2 or len(mf_ss_docs) != 2:
           print(
               f"Warning: Participant {participant_id} does not have expected PS/AF and MF/SS groupings. "
               f"PS/AF: {len(ps_af_docs)}, MF/SS: {len(mf_ss_docs)}"
           )
           continue

       # --- PS+AF combined session ---
       ps_af_sid = requests.post(f"{ADEPT_URL}api/v1/new_session").text.replace('"', "").strip()
       for document in ps_af_docs:
           old_sid = document.get("combinedSessionId")
           probes = extract_probes(document)
           db_utils.send_probes(
               f"{ADEPT_URL}api/v1/response", probes, ps_af_sid, document["scenario_id"]
           )
           mongo_db["userScenarioResults"].update_one(
               {"_id": document["_id"]}, {"$set": {"combinedSessionId": ps_af_sid}}
           )
           if old_sid:
               mongo_db["humanToADMComparison"].update_many(
                   {"text_session_id": old_sid},
                   {"$set": {"text_session_id": ps_af_sid}}
               )

       # --- MF+SS combined session ---
       mf_ss_sid = requests.post(f"{ADEPT_URL}api/v1/new_session").text.replace('"', "").strip()
       for document in mf_ss_docs:
           old_sid = document.get("combinedSessionId")
           probes = extract_probes(document)
           db_utils.send_probes(
               f"{ADEPT_URL}api/v1/response", probes, mf_ss_sid, document["scenario_id"]
           )
           mongo_db["userScenarioResults"].update_one(
               {"_id": document["_id"]}, {"$set": {"combinedSessionId": mf_ss_sid}}
           )
           if old_sid:
               mongo_db["humanToADMComparison"].update_many(
                   {"text_session_id": old_sid},
                   {"$set": {"text_session_id": mf_ss_sid}}
               )

       # --- MF individual session ---
       for document in mf_docs:
           old_individual_sid = document.get("individualSessionId")
           mf_individual_sid = requests.post(f"{ADEPT_URL}api/v1/new_session").text.replace('"', "").strip()
           probes = extract_probes(document)
           db_utils.send_probes(
               f"{ADEPT_URL}api/v1/response", probes, mf_individual_sid, document["scenario_id"]
           )
           mongo_db["userScenarioResults"].update_one(
               {"_id": document["_id"]}, {"$set": {"individualSessionId": mf_individual_sid}}
           )
           if old_individual_sid:
               mongo_db["humanToADMComparison"].update_many(
                   {"text_session_id": old_individual_sid},
                   {"$set": {"text_session_id": mf_individual_sid}}
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