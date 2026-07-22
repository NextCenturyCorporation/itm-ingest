from decouple import config

PATIENT_COUNT = 12

def patient_actions(history, scene_id=None, action_types=None, exclude_types=None):
    # parses history to extract all actions involving patient, will be used for multiple fields
    actions = []

    for entry in history or []:
        if entry.get("command") != "Take Action":
            continue

        params = entry.get("parameters") or {}
        character = params.get("character")
        if not character:
            continue

        action_type = params.get("action_type")
        if action_types is not None and action_type not in action_types:
            continue
        if exclude_types is not None and action_type in exclude_types:
            continue

        if scene_id is not None:
            meta = (entry.get("response") or {}).get("meta_info") or {}
            if meta.get("scene_id") != scene_id:
                continue

        actions.append({
            "character": character,
            "action_type": action_type,
            "category": params.get("category"),
            "justification": params.get("justification"),
        })

    return actions

def patient_order(actions):
    #returns updates 'Patient{n}_order for all patients
    first_seen = {}

    for action in actions:
        if action["action_type"] == "MOVE_TO_EVAC":
            continue

        character = action["character"]
        if character not in first_seen:
            first_seen[character] = len(first_seen) + 1

    return {
        f"Patient{n}_order": first_seen.get(f"Patient {n}")
        for n in range(1, PATIENT_COUNT + 1)
    }

def patient_evac(actions):
    # goes through actions list and returns 1 for a patient if they were evacd
    evacuated = {
        action["character"]
        for action in actions
        if action["action_type"] == "MOVE_TO_EVAC"
    }

    return {
        f"Patient{n}_evac": 1 if f"Patient {n}" in evacuated else 0
        for n in range(1, PATIENT_COUNT + 1)
    }

def process_adm(adm):
    history = adm.get("history") or []
    actions = patient_actions(history)

    action_analysis = {}
    # determine Patient{N}_order
    action_analysis.update(patient_order(actions))
    # Patient{N}_evac
    action_analysis.update(patient_evac(actions))

    return action_analysis


SCENARIO_IDS = [
    "June2025-OW_desert2",
    "June2025-OW_urban2",
    "April2026-OW_desert2",
    "April2026-OW_urban2",
    "Feb2026-OW_desert2",
    "Feb2026-OW_urban2",
]


def main(mongo_db):
    collection = mongo_db["admTargetRuns"]
    open_world_adms = list(
        collection.find({"scenario": {"$in": SCENARIO_IDS}})
    )

    updated = 0
    for adm in open_world_adms:
        action_analysis = process_adm(adm)
        result = collection.update_one(
            {"_id": adm["_id"]},
            {"$set": {"actionAnalysis": action_analysis}},
        )
        updated += result.modified_count
    
    print(f"Updated actionAnalysis on {updated} of {len(open_world_adms)} documents")


if __name__ == "__main__":
    from pymongo import MongoClient

    MONGO_URL = config("MONGO_URL")
    client = MongoClient(MONGO_URL)
    mongoDB = client["dashboard"]
    main(mongoDB)