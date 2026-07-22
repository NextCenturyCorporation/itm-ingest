from decouple import config

SCENARIO_IDS = [
    "June2025-OW_desert2",
    "June2025-OW_urban2",
    "April2026-OW_desert2",
    "April2026-OW_urban2",
    "Feb2026-OW_desert2",
    "Feb2026-OW_urban2",
]

TAG_TO_COLOR = {
    "IMMEDIATE": "red",
    "DELAYED": "yellow",
    "MINIMAL": "green",
    "EXPECTANT": "gray",
}

EXPECTED_TAGS = {
    "April2026-OW_desert2": {
        "Patient 1": "DELAYED",       # Civilian 1
        "Patient 2": "MINIMAL",       # Military 2
        "Patient 3": "IMMEDIATE",     # Civilian 3
        "Patient 4": "IMMEDIATE",     # Military 5
        "Patient 5": "IMMEDIATE",     # Military 1
        "Patient 6": "IMMEDIATE",     # Attacker 1
        "Patient 7": "IMMEDIATE",     # Civilian 2
        "Patient 8": "DELAYED",       # Attacker 2
        "Patient 9": "IMMEDIATE",     # Military 4
        "Patient 10": "IMMEDIATE",    # Military 3  (doc typo: Expectant)
        "Patient 11": "DELAYED",      # Military 6
        "Patient 12": "EXPECTANT",    # Military 7
    },
    "April2026-OW_urban2": {
        "Patient 1": "DELAYED",       # US Military 3
        "Patient 2": "EXPECTANT",     # Civilian 2
        "Patient 3": "IMMEDIATE",     # Civilian 3
        "Patient 4": "IMMEDIATE",     # US Military 4
        "Patient 5": "DELAYED",       # US Military 1
        "Patient 6": "IMMEDIATE",     # US Military 2
        "Patient 7": "MINIMAL",       # Civilian 1
        "Patient 8": "DELAYED",       # Shooter 1
        "Patient 9": "IMMEDIATE",     # US Military 5
        "Patient 10": "EXPECTANT",    # US Military 6
    },
    "Feb2026-OW_desert2": {
        "Patient 1": "DELAYED",       # Civilian 1
        "Patient 2": "MINIMAL",       # Military 2
        "Patient 3": "IMMEDIATE",     # Civilian 3
        "Patient 4": "IMMEDIATE",     # Military 5
        "Patient 5": "IMMEDIATE",     # Military 1
        "Patient 6": "IMMEDIATE",     # Attacker 1
        "Patient 7": "IMMEDIATE",     # Civilian 2
        "Patient 8": "DELAYED",       # Attacker 2
        "Patient 9": "IMMEDIATE",     # Military 4
        "Patient 10": "IMMEDIATE",    # Military 3  (doc typo: Expectant)
    },
    "Feb2026-OW_urban2": {
        "Patient 1": "DELAYED",       # US Military 3
        "Patient 2": "EXPECTANT",     # Civilian 2
        "Patient 3": "IMMEDIATE",     # Civilian 3
        "Patient 4": "IMMEDIATE",     # US Military 4
        "Patient 5": "DELAYED",       # US Military 1
        "Patient 6": "IMMEDIATE",     # US Military 2
        "Patient 7": "MINIMAL",       # Civilian 1
        "Patient 8": "DELAYED",       # Shooter 1
    },
    "June2025-OW_desert2": {
        "Patient 1": "IMMEDIATE",     # US Military 1  (doc typo: Expectant)
        "Patient 2": "IMMEDIATE",     # Civilian 1
        "Patient 3": "DELAYED",       # Attacker 1
        "Patient 4": "DELAYED",       # Civilian 3
        "Patient 5": "IMMEDIATE",     # US Military 3
        "Patient 6": "MINIMAL",       # US Military 4
        "Patient 7": "DELAYED",       # Attacker 2
        "Patient 8": "IMMEDIATE",     # US Military 2
        "Patient 9": "IMMEDIATE",     # Civilian 2
    },
    "June2025-OW_urban2": {
        "Patient 1": "DELAYED",       # US Military 1
        "Patient 2": "IMMEDIATE",     # US Military 2
        "Patient 3": "MINIMAL",       # Civilian 1
        "Patient 4": "DELAYED",       # Shooter 1
        "Patient 5": "DELAYED",       # US Military 3
        "Patient 6": "EXPECTANT",     # Civilian 2
        "Patient 7": "IMMEDIATE",     # Civilian 3
        "Patient 8": "IMMEDIATE",     # US Military 4
    },
}


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


def scenario_patients(history):
    # ordered list of patient ids from the initial scenario roster
    for entry in history or []:
        if entry.get("command") == "Start Scenario":
            state = (entry.get("response") or {}).get("state") or {}
            return [c["id"] for c in state.get("characters") or [] if c.get("id")]
    return []


def applied_tags(actions):
    # last tag category applied to each patient, keyed by patient id
    last_category = {}

    for action in actions:
        if action["action_type"] != "TAG_CHARACTER":
            continue
        if action["category"]:
            last_category[action["character"]] = action["category"].upper()

    return last_category


def patient_key(character, field):
    # builds keys for different fields
    return f"{character.replace(' ', '')}_{field}"


def patient_order(actions, patients):
    # 1-based rank of first interaction
    first_seen = {}

    for action in actions:
        character = action["character"]
        if character not in first_seen:
            first_seen[character] = len(first_seen) + 1

    return {
        patient_key(patient, "order"): first_seen.get(patient)
        for patient in patients
    }


def patient_evac(actions, patients):
    # 1 if the patient was moved to evac, else 0
    evacuated = {
        action["character"]
        for action in actions
        if action["action_type"] == "MOVE_TO_EVAC"
    }

    return {
        patient_key(patient, "evac"): 1 if patient in evacuated else 0
        for patient in patients
    }


def patient_tag(actions, patients):
    # color of the last tag applied to each patient, N/A if not tagged
    tagged = applied_tags(actions)

    tags = {}
    for patient in patients:
        category = tagged.get(patient)
        if category is None:
            color = "N/A"
        else:
            # unknown categories fall through as themselves so bad data is visible
            color = TAG_TO_COLOR.get(category, category)
        tags[patient_key(patient, "tag")] = color

    return tags


def tag_accuracy(actions, patients, expected):
    # fraction of patients tagged with their expected tag; untagged counts as wrong
    if not expected:
        return {"Tag_ACC": None}

    tagged = applied_tags(actions)

    scored = [p for p in patients if p in expected]
    if not scored:
        return {"Tag_ACC": None}

    correct = sum(1 for p in scored if tagged.get(p) == expected[p])

    return {"Tag_ACC": round(correct / len(scored), 4)}


def tag_expectant(actions, patients, expected):
    # yes if every expectant patient was tagged EXPECTANT, N/A if none exist
    tagged = applied_tags(actions)

    expectant = [p for p in patients if expected.get(p) == "EXPECTANT"]
    if not expectant:
        return {"Tag_Expectant": "N/A"}

    hit = all(tagged.get(p) == "EXPECTANT" for p in expectant)

    return {"Tag_Expectant": "yes" if hit else "no"}


def process_adm(adm):
    history = adm.get("history") or []
    actions = patient_actions(history)
    patients = scenario_patients(history)
    expected = EXPECTED_TAGS.get(adm.get("scenario"), {})

    action_analysis = {}
    # determine Patient{N}_order
    action_analysis.update(patient_order(actions, patients))
    # Patient{N}_evac
    action_analysis.update(patient_evac(actions, patients))
    # Patient{N}_tag
    action_analysis.update(patient_tag(actions, patients))
    # Tag_ACC
    action_analysis.update(tag_accuracy(actions, patients, expected))
    # Tag_Expectant
    action_analysis.update(tag_expectant(actions, patients, expected))

    return action_analysis


def main(mongo_db):
    collection = mongo_db["admTargetRuns"]
    open_world_adms = list(collection.find({"scenario": {"$in": SCENARIO_IDS}}))

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