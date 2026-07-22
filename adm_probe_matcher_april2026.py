from decouple import config
from typing import Any

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

ADM_NAMES_TO_REMOVE = [
    'ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3__b1d8c4e4-7677-4055-8576-6a6c59b11879',
    'ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3__bf666949-e21f-4085-9984-7ba78e19d5b4',
    'ALIGN-ADM-Ph2-ComparativeRegression-Zeroshot-Mistral-7B-Instruct-v0.3__9d46bb74-ddad-4e96-bde2-322d8b5837a0',
    'ALIGN-ADM-Ph2-DirectRegression-Mistral-7B-Instruct-v0.3__88aadd5e-9f2b-4310-801e-3edcff9d39dc',
    'ALIGN-ADM-Ph2-DirectRegression-Mistral-7B-Instruct-v0.3__df910407-c00e-4a41-a957-8f05ed828d47',
    'ALIGN-ADM-Ph2-ComparativeRegression-Mistral-7B-Instruct-v0.3__9c02ace1-58a9-4d6d-9356-25fde54b9648',
    'ALIGN-ADM-Ph2-ComparativeRegression-Mistral-7B-Instruct-v0.3__ab819dc3-ecc3-49c8-867a-2aa9d3e1a37a'
]

EVAL_NUMBERS = [8, 15, 16]

def build_query() -> dict[str, Any]:
    return {
        "evalNumber": {"$in": EVAL_NUMBERS},
        "adm_name": {"$in": ADM_NAMES_TO_REMOVE},
    }

def print_matching_documents(collection: Any, query: dict[str, Any]) -> None:
    projection = {
        "_id": 1,
        "evalNumber": 1,
        "evalName": 1,
        "scenario": 1,
        "adm_name": 1,
        "alignment_target": 1,
        "synthetic": 1,
    }

    docs = list(collection.find(query, projection).sort([("adm_name", 1), ("scenario", 1), ("alignment_target", 1)]))

    print(f"Matched {len(docs)} document(s) for removal.")

    for doc in docs:
        print(
            "  "
            f"_id={doc.get('_id')} | "
            f"evalNumber={doc.get('evalNumber')} | "
            f"scenario={doc.get('scenario')} | "
            f"alignment_target={doc.get('alignment_target')} | "
            f"synthetic={doc.get('synthetic', False)} | "
            f"adm_name={doc.get('adm_name')}"
        )

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


def patient_key(character, field):
    # builds keys for different fields
    return f"{character.replace(' ', '')}_{field}"


def patient_order(actions, patients):
    # 1-based rank of first treat/tag interaction; evac moves don't count
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
    last_category = {}

    for action in actions:
        if action["action_type"] != "TAG_CHARACTER":
            continue
        if action["category"]:
            last_category[action["character"]] = action["category"]

    tags = {}
    for patient in patients:
        category = last_category.get(patient)
        if category is None:
            color = "N/A"
        else:
            # unknown categories fall through as themselves so bad data is visible
            color = TAG_TO_COLOR.get(category.upper(), category)
        tags[patient_key(patient, "tag")] = color

    return tags


def process_adm(adm):
    history = adm.get("history") or []
    actions = patient_actions(history)
    patients = scenario_patients(history)

    action_analysis = {}
    # determine Patient{N}_order
    action_analysis.update(patient_order(actions, patients))
    # Patient{N}_evac
    action_analysis.update(patient_evac(actions, patients))
    # Patient{N}_tag
    action_analysis.update(patient_tag(actions, patients))

    return action_analysis

def delete_adms(collection, write_to_db=True, verbose=True):
    query = build_query()
    matched_count = collection.count_documents(query)

    if verbose:
        print_matching_documents(collection, query)
    else:
        print(f"Matched {matched_count} document(s) for removal.")

    if matched_count == 0:
        print("No matching documents found. Nothing to delete.")
        return

    if not write_to_db:
        print("Dry-run complete. No MongoDB documents were deleted.")
        return

    result = collection.delete_many(query)

    print(f"Deleted {result.deleted_count} document(s) from {collection.name}.")

    if result.deleted_count != matched_count:
        raise RuntimeError(
            f"Delete count mismatch: matched {matched_count}, deleted {result.deleted_count}."
        )

    remaining_count = collection.count_documents(query)

    if remaining_count != 0:
        raise RuntimeError(
            f"Cleanup incomplete: {remaining_count} matching document(s) still remain."
        )

    print("Cleanup complete. No matching unwanted ADM documents remain.")

def main(mongo_db, delete_bad_adms=False):
    collection = mongo_db["admTargetRuns"]
    delete_adms(collection, delete_bad_adms)
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