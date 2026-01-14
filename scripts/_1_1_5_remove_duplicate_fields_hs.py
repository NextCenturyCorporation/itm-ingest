EVALS = [8, 9, 10, 12]
BAD_SUFFIXES = (" Tag_acc", " Tag_expectant")

# Value to replace empty tag fields
TAG_SUFFIX = "_tag"
OLD_TAG_VALUE = "N/A"
NEW_TAG_VALUE = "None"

def _build_unset_for_bad_actionanalysis_fields(action_analysis):
    """
    Given an actionAnalysis dict, return an $unset dict that removes:
      actionAnalysis.<anything ending in ' Tag_acc'>
      actionAnalysis.<anything ending in ' Tag_expectant'>
    This is case-sensitive by nature of Python string matching.
    """
    unset_fields = {}

    if not isinstance(action_analysis, dict):
        return unset_fields

    for key in action_analysis.keys():
        if key.endswith(BAD_SUFFIXES):
            unset_fields[f"actionAnalysis.{key}"] = ""

    return unset_fields


def _build_set_for_na_tags(action_analysis):
    """
    Replace actionAnalysis.<..._tag> values of "N/A" with "None" (string).
    """
    set_fields = {}

    if not isinstance(action_analysis, dict):
        return set_fields

    for key, value in action_analysis.items():
        # Only touch the tag fields
        if key.endswith(TAG_SUFFIX) and value == OLD_TAG_VALUE:
            set_fields[f"actionAnalysis.{key}"] = NEW_TAG_VALUE

    return set_fields


def main(mongo_db):
    human_simulator_collection = mongo_db["humanSimulator"]

    query = {
        "evalNumber": {"$in": EVALS},
        "actionAnalysis": {"$type": "object"},
    }

    projection = {"actionAnalysis": 1}

    matched = 0
    modified = 0

    cursor = human_simulator_collection.find(query, projection=projection, batch_size=500)

    for doc in cursor:
        matched += 1

        action_analysis = doc.get("actionAnalysis", {})

        unset_fields = _build_unset_for_bad_actionanalysis_fields(action_analysis)
        set_fields = _build_set_for_na_tags(action_analysis)

        # Nothing to do
        if not unset_fields and not set_fields:
            continue

        update_doc = {}
        if unset_fields:
            update_doc["$unset"] = unset_fields
        if set_fields:
            update_doc["$set"] = set_fields

        result = human_simulator_collection.update_one(
            {"_id": doc["_id"]},
            update_doc,
        )

        if result.modified_count:
            modified += 1

    print(f"[remove-duplicate-fields-and-fix-tags] matched={matched}, modified={modified}")
