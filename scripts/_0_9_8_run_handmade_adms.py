"""
The September 2025 Collaboration (Idaho) used hand made 'ADM' runs for the delegation survey
This script will take those fake ADMs and run them through the ADEPT server so we can use them for scoring
"""

import requests
from delegation_survey.september_handmade_adms import main as add_probe_ids
import utils.db_utils as db_utils
from decouple import config
from collections import defaultdict
ADEPT_URL = config("ADEPT_URL")

def main(mongo_db):
    # will edit the admMedics collection for eval 10
    # so that we have the corresponding probe ids for each choice
    add_probe_ids(mongo_db)

    medics = mongo_db["admMedics"]
    sept_medics = medics.find({"evalNumber": 10})

    for medic in sept_medics:
        responses = medic["elements"][0]["rows"]
        
        responses_by_scenario = defaultdict(list)
        for response in responses:
            responses_by_scenario[response["scenario_id"]].append(response)
        
        sessions_data = []
        for scenario_id, scenario_responses in responses_by_scenario.items():
            sid = (
                requests.post(f"{ADEPT_URL}api/v1/new_session")
                .text.replace('"', "")
                .strip()
            )
            

            probes = [
                {
                    "probe": {
                        "choice": response["choice_id"],
                        "probe_id": response["probe_id"],
                    }
                }
                for response in scenario_responses
            ]
            
            db_utils.send_probes(f"{ADEPT_URL}api/v1/response", probes, sid, scenario_id)
            
   
            kdmas = requests.get(
                f"{ADEPT_URL}api/v1/computed_kdma_profile?session_id={sid}"
            ).json()
            
            sessions_data.append({
                "scenario_id": scenario_id,
                "session_id": sid,
                "kdmas": kdmas
            })
        

        if len(sessions_data) == 1:
            medics.update_one(
                {"_id": medic["_id"]},
                {
                    "$set": {
                        "kdmas": sessions_data[0]["kdmas"],
                        "admSessionId": sessions_data[0]["session_id"],
                    }
                }
            )
        else:
            # combined runs
            medics.update_one(
                {"_id": medic["_id"]},
                {
                    "$set": {
                        "admSessionIdsByScenario": {s["scenario_id"]: s["session_id"] for s in sessions_data},
                        "kdmasByScenario": {s["scenario_id"]: s["kdmas"] for s in sessions_data}
                    }
                }
            )