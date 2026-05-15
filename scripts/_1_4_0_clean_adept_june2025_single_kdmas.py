from typing import Any, Dict, List, Optional


COLLECTION_NAME = "admTargetRuns"
TARGET_PREFIX = "ADEPT-June2025"
SINGLE_KDMAS = {"affiliation", "merit", "search", "personal_safety"}


def build_query() -> Dict[str, Any]:
    return {
        "evaluation.alignment_target_id": {
            "$regex": "^ADEPT-June2025-(affiliation|merit|search|personal_safety)-",
        },
        "results.kdmas": {"$exists": True},
    }


def expected_kdma_from_target_id(target_id: Any) -> Optional[str]:
    if not isinstance(target_id, str):
        return None

    parts = target_id.split("-")
    if len(parts) < 4:
        return None

    if "-".join(parts[:2]) != TARGET_PREFIX:
        return None

    kdma = parts[2]
    if kdma not in SINGLE_KDMAS:
        return None

    return kdma


def get_kdma_names(kdmas: Any) -> List[Any]:
    if not isinstance(kdmas, list):
        return []
    return [entry.get("kdma") if isinstance(entry, dict) else None for entry in kdmas]


def cleaned_kdmas(kdmas: Any, expected_kdma: str) -> List[Any]:
    if not isinstance(kdmas, list):
        return []
    return [entry for entry in kdmas if isinstance(entry, dict) and entry.get("kdma") == expected_kdma]


def print_cleanup_doc(doc: Dict[str, Any], expected_kdma: str, original_kdmas: List[Any], new_kdmas: List[Any]) -> None:
    evaluation = doc.get("evaluation", {}) or {}

    print(
        "  "
        f"_id={doc.get('_id')} | "
        f"scenario_id={evaluation.get('scenario_id')} | "
        f"alignment_target_id={evaluation.get('alignment_target_id')} | "
        f"expected_kdma={expected_kdma} | "
        f"original_kdmas={original_kdmas} | "
        f"cleaned_kdmas={new_kdmas}"
    )


def main(mongo_db: Any, verbose: bool = True) -> None:
    print("Starting ADEPT June 2025 single-KDMA cleanup.")
    print(f"verbose={verbose}")

    collection = mongo_db[COLLECTION_NAME]
    query = build_query()
    projection = {
        "evaluation.scenario_id": 1,
        "evaluation.alignment_target_id": 1,
        "results.kdmas": 1,
    }

    print(f"Collection: {COLLECTION_NAME}")
    print(f"Query: {query}")

    matched = 0
    skipped_non_single_target = 0
    skipped_bad_kdmas = 0
    cleanup_needed = 0
    modified = 0

    cursor = collection.find(query, projection=projection, batch_size=500)

    for doc in cursor:
        matched += 1

        evaluation = doc.get("evaluation", {}) or {}
        target_id = evaluation.get("alignment_target_id")
        expected_kdma = expected_kdma_from_target_id(target_id)

        if expected_kdma is None:
            skipped_non_single_target += 1
            continue

        original_results_kdmas = doc.get("results", {}).get("kdmas")
        if not isinstance(original_results_kdmas, list):
            skipped_bad_kdmas += 1
            continue

        new_results_kdmas = cleaned_kdmas(original_results_kdmas, expected_kdma)

        if new_results_kdmas == original_results_kdmas:
            continue

        cleanup_needed += 1

        if verbose:
            print_cleanup_doc(
                doc,
                expected_kdma,
                get_kdma_names(original_results_kdmas),
                get_kdma_names(new_results_kdmas),
            )

        result = collection.update_one(
            {"_id": doc["_id"]},
            {"$set": {"results.kdmas": new_results_kdmas}},
        )

        if result.modified_count:
            modified += 1

    print(
        "Summary: "
        f"matched={matched}, "
        f"cleanup_needed={cleanup_needed}, "
        f"modified={modified}, "
        f"skipped_non_single_target={skipped_non_single_target}, "
        f"skipped_bad_kdmas={skipped_bad_kdmas}"
    )

    if modified != cleanup_needed:
        raise RuntimeError(f"Update count mismatch: cleanup_needed={cleanup_needed}, modified={modified}.")
