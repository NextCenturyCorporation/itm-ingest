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
   text_scenarios = mongo_db["userScenarioResults"].find({"evalNumber": {"$gte": 8}})
   comparison_collec = mongo_db["humanToADMComparison"].find({"evalNumber": {"$gte": 8}})
   adm_runs = mongo_db["admTargetRuns"].find({"evalNumber": {"$gte": 8}})

   # group text scenarios by pid
   participant_groups = defaultdict(list)
   for result in text_scenarios:
       participant_groups[result["participantID"]].append(result)

   for participant_id, documents in participant_groups.items():
       if len(documents) != 4:
           print(
               f"Warning: Participant {participant_id} has {len(documents)} documents instead of 4"
           )
           continue

       # creates new session id and responds to all probes using it
       sid = requests.post(f"{ADEPT_URL}api/v1/new_session").text.replace('"', "").strip()
       for idx, document in enumerate(documents, 1):
           old_sid = document.get("combinedSessionId")
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
           
           db_utils.send_probes(
               f"{ADEPT_URL}api/v1/response", probes, sid, document["scenario_id"]
           )
           
           # update the session id on the text based documents
           mongo_db["userScenarioResults"].update_one(
               {"_id": document["_id"]}, {"$set": {"combinedSessionId": sid}}
           )

           if old_sid:
               # update the text session id in humanToADMComparison
               mongo_db["humanToADMComparison"].update_many(
                    {"text_session_id": old_sid},
                    {"$set": {"text_session_id": sid}}
                )

   for adm_run in adm_runs:
        # skip over the synthetic runs
        if 'history' not in adm_run:
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


if __name__ == "__main__":
   from pymongo import MongoClient

   MONGO_URL = config("MONGO_URL")
   client = MongoClient(MONGO_URL)
   mongoDB = client["dashboard"]
   main(mongoDB)