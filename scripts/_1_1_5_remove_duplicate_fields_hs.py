EVALS = [8, 9, 10, 12]
BAD_SUFFIXES = (" Tag_acc", " Tag_expectant")

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
        # Case-sensitive exact suffix match
        if key.endswith(BAD_SUFFIXES):
            unset_fields[f"actionAnalysis.{key}"] = ""

    return unset_fields


def main(mongo_db):
    human_simulator_collection = mongo_db["humanSimulator"]

    # Query only documents:
    # - evalNumber in the target set
    # - actionAnalysis exists and is an object (dict)
    # (We could also prefilter for likely bad keys, but keeping it simple & robust here.)
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

        # No bad fields in this document
        if not unset_fields:
            continue

        result = human_simulator_collection.update_one(
            {"_id": doc["_id"]},
            {"$unset": unset_fields},
        )

        if result.modified_count:
            modified += 1

    print(f"[remove-duplicate-fields] matched={matched}, modified={modified}")