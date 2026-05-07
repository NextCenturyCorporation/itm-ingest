"""
ITM-1338 / Open World ADM cleanup

Removes two unwanted Feb2026 ADM runs from admTargetRuns.

redo.py examples:
    python redo.py 139 false true
    python redo.py 139 true true

Arguments when using redo.py:
    write_to_db: bool = True
    verbose: bool = True
"""

from typing import Any


EVAL_NUMBER = 15
COLLECTION_NAME = "admTargetRuns"

ADM_NAMES_TO_REMOVE = [
    "ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3__720f9b47-fbf3-48ee-82f9-8fcfe7f54266",
    "ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-Mistral-7B-Instruct-v0.3__6fcf0cf5-9923-43ce-8b56-fa08021409ed",
]


def build_query() -> dict[str, Any]:
    return {
        "evalNumber": EVAL_NUMBER,
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


def main(mongo_db: Any, write_to_db: bool = True, verbose: bool = True) -> None:
    print("Starting unwanted Feb2026 ADM run cleanup.")
    print(f"write_to_db={write_to_db}, verbose={verbose}")

    collection = mongo_db[COLLECTION_NAME]
    query = build_query()

    print(f"Collection: {COLLECTION_NAME}")
    print(f"Query: {query}")

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

    print(f"Deleted {result.deleted_count} document(s) from {COLLECTION_NAME}.")

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
