"""
The September 2025 Collaboration (Idaho) used hand made 'ADM' runs for the delegation survey
This script will take those fake ADMs and run them through the ADEPT server so we can use them for scoring
"""

import requests
from delegation_survey.september_handmade_adms import main as add_probe_ids
import utils.db_utils as db_utils
from decouple import config

ADEPT_URL = config("ADEPT_URL")


def main(mongo_db):
    # will edit the admMedics collection for eval 10
    # so that we have the corresponding probe ids for each choice
    add_probe_ids(mongo_db)

    medics = mongo_db["admMedics"]
    sept_medics = medics.find({"evalNumber": 10})

    for medic in sept_medics:
        if "combined" in medic["scenarioIndex"]:
            # we can't score these ones yet
            continue
        sid = (
            requests.post(f"{ADEPT_URL}api/v1/new_session")
            .text.replace('"', "")
            .strip()
        )
        scenario = medic["scenarioIndex"]
        responses = medic["elements"][0]["rows"]
        probes = []
        for response in responses:
            probes.append(
                {
                    "probe": {
                        "choice": response["choice_id"],
                        "probe_id": response["probe_id"],
                    }
                }
            )
        db_utils.send_probes(f"{ADEPT_URL}api/v1/response", probes, sid, scenario)
        kdmas = requests.get(
            f"{ADEPT_URL}api/v1/computed_kdma_profile?session_id={sid}"
        ).json()
        medics.update_one(
            {"_id": medic["_id"]},
            {
                "$set": {
                    "kdmas": kdmas,
                    "admSessionId": sid,
                }
            },
        )
