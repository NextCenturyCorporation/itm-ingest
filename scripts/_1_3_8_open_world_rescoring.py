"""
ITM-1332 / ITM-1337: Rescore Feb2026 Open World desert ADM target runs.

This script recalculates TA1/ADEPT session alignment results for the Feb2026
Open World desert ADM runs Darren identified, then writes the recalculated result
object back to admTargetRuns.results.

Examples:
  python redo.py 138 false true false
      Dry-run, verbose, do not enforce the expected 16+16 document count.

  python redo.py 138 false true true
      Dry-run, verbose, enforce the expected 16 baseline + 16 aligned docs.

  python redo.py 138 true true true
      Write updates, verbose, enforce expected counts.
"""

from typing import Any, Dict, List, Optional, Tuple

import requests
from decouple import config


EVAL_NUMBER = 15
SCENARIO = "Feb2026-OW_desert"
COLLECTION_NAME = "admTargetRuns"
EXPECTED_DOCS_PER_ADM = 16

BASELINE_ADM = (
    "ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3__"
    "9d7c67c1-9c7e-46b1-a8d9-75eceb2428ca"
)
ALIGNED_ADM = (
    "ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-Mistral-7B-Instruct-v0.3__"
    "96699c14-ab0d-4dfc-b915-8ddfb67f198b"
)
TARGET_ADMS = [BASELINE_ADM, ALIGNED_ADM]

REQUEST_TIMEOUT_SECONDS = 60


def _adept_url(path: str) -> str:
    """Build an ADEPT URL that works whether ADEPT_URL has a trailing slash or not."""
    return config("ADEPT_URL").rstrip("/") + "/" + path.lstrip("/")


def _get_alignment_target(adm_run: Dict[str, Any]) -> str:
    """Return the alignment target ID from the known possible document locations."""
    target = adm_run.get("alignment_target")
    if target:
        return target

    evaluation = adm_run.get("evaluation", {})
    target = evaluation.get("alignment_target_id") or evaluation.get("alignment_target")
    if target:
        return target

    raise ValueError(f"ADM run {adm_run.get('_id')} does not have an alignment target field.")


def _extract_probe_responses(adm_run: Dict[str, Any]) -> List[Dict[str, str]]:
    """Extract TA1 probe responses from an admTargetRuns history block."""
    probes: List[Dict[str, str]] = []
    for history_item in adm_run.get("history", []):
        if history_item.get("command") != "Respond to TA1 Probe":
            continue

        parameters = history_item.get("parameters", {})
        probe_id = parameters.get("probe_id")
        choice = parameters.get("choice")

        if probe_id is None or choice is None:
            raise ValueError(
                f"ADM run {adm_run.get('_id')} has a probe response missing probe_id or choice."
            )

        probes.append({"probe_id": probe_id, "choice": choice})

    if not probes:
        raise ValueError(f"ADM run {adm_run.get('_id')} has no TA1 probe responses in history.")

    return probes


def _create_ta1_session(req_session: requests.Session) -> str:
    response = req_session.post(
        _adept_url("api/v1/new_session"),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    session_id = response.text.replace('"', "").strip()
    if not session_id:
        raise RuntimeError("ADEPT returned an empty TA1 session ID.")
    return session_id


def _send_probe_responses(
    req_session: requests.Session,
    session_id: str,
    probes: List[Dict[str, str]],
    scenario_id: str,
) -> None:
    for probe in probes:
        response = req_session.post(
            _adept_url("api/v1/response"),
            json={
                "response": {
                    "probe_id": probe["probe_id"],
                    "choice": probe["choice"],
                    "justification": "justification",
                    "scenario_id": scenario_id,
                },
                "session_id": session_id,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()


def _get_session_alignment(
    req_session: requests.Session,
    session_id: str,
    target_id: str,
) -> Dict[str, Any]:
    response = req_session.get(
        _adept_url("api/v1/alignment/session"),
        params={
            "session_id": session_id,
            "target_id": target_id,
            "population": "false",
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    session_alignment = response.json()

    if "score" not in session_alignment:
        raise RuntimeError(
            f"ADEPT alignment response for session {session_id}, target {target_id} "
            f"did not contain a score: {session_alignment}"
        )

    return session_alignment


def _get_computed_kdma_profile(req_session: requests.Session, session_id: str) -> List[Dict[str, Any]]:
    response = req_session.get(
        _adept_url("api/v1/computed_kdma_profile"),
        params={"session_id": session_id},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    kdmas = response.json()

    if kdmas is None:
        raise RuntimeError(f"ADEPT returned no KDMA profile for session {session_id}.")

    return kdmas


def _extract_alignment_warning(session_alignment: Dict[str, Any]) -> Any:
    """Handle the likely warning key names without dropping TA1 warning info."""
    if "alignment_warning" in session_alignment:
        return session_alignment.get("alignment_warning")
    if "warning" in session_alignment:
        return session_alignment.get("warning")
    if "warnings" in session_alignment:
        return session_alignment.get("warnings")
    return None


def _build_results_object(
    session_id: str,
    session_alignment: Dict[str, Any],
    kdmas: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "ta1_session_id": session_id,
        "alignment_score": session_alignment.get("score"),
        "kdmas": kdmas,
        "alignment_warning": _extract_alignment_warning(session_alignment),
    }


def _old_score(adm_run: Dict[str, Any]) -> Any:
    evaluation_results = adm_run.get("evaluation", {}).get("results", {})
    if isinstance(evaluation_results, dict) and "alignment_score" in evaluation_results:
        return evaluation_results.get("alignment_score")

    top_level_results = adm_run.get("results", {})
    if isinstance(top_level_results, dict):
        return top_level_results.get("alignment_score")

    return None


def _target_sort_key(adm_run: Dict[str, Any]) -> Tuple[str, str]:
    target = _get_alignment_target(adm_run)
    return target, str(adm_run.get("_id"))


def _print_document_summary(docs: List[Dict[str, Any]]) -> None:
    baseline_count = sum(1 for doc in docs if doc.get("adm_name") == BASELINE_ADM)
    aligned_count = sum(1 for doc in docs if doc.get("adm_name") == ALIGNED_ADM)
    targets = sorted({_get_alignment_target(doc) for doc in docs})

    print(f"Matched {len(docs)} {COLLECTION_NAME} documents for rescoring.")
    print(f"  Baseline docs: {baseline_count}")
    print(f"  Aligned docs:  {aligned_count}")
    print("  Targets found:")
    for target in targets:
        print(f"    - {target}")


def _validate_expected_counts(docs: List[Dict[str, Any]]) -> None:
    baseline_count = sum(1 for doc in docs if doc.get("adm_name") == BASELINE_ADM)
    aligned_count = sum(1 for doc in docs if doc.get("adm_name") == ALIGNED_ADM)

    if baseline_count != EXPECTED_DOCS_PER_ADM or aligned_count != EXPECTED_DOCS_PER_ADM:
        raise RuntimeError(
            "Unexpected document count. Expected "
            f"{EXPECTED_DOCS_PER_ADM} baseline and {EXPECTED_DOCS_PER_ADM} aligned documents, "
            f"but found {baseline_count} baseline and {aligned_count} aligned. "
            "Re-run with strict_counts=False only if you intentionally want to process a partial set."
        )


def _calculate_baseline_updates(
    req_session: requests.Session,
    baseline_docs: List[Dict[str, Any]],
    verbose: bool,
) -> List[Tuple[Any, Dict[str, Any]]]:
    """
    Baseline ADMs produce the same probe responses at each target, so use one
    TA1 session/KDMA profile and compare that session against each target.
    """
    if not baseline_docs:
        return []

    first_probes = _extract_probe_responses(baseline_docs[0])

    # Darren said baseline responses should be the same across targets. Verify that before reusing one session.
    for doc in baseline_docs[1:]:
        probes = _extract_probe_responses(doc)
        if probes != first_probes:
            raise RuntimeError(
                "Baseline ADM probe responses were not identical across all targets. "
                "Aborting instead of reusing one baseline TA1 session."
            )

    print("Creating one ADEPT session for baseline ADM and reusing it across baseline targets.")
    baseline_session_id = _create_ta1_session(req_session)
    _send_probe_responses(req_session, baseline_session_id, first_probes, SCENARIO)
    baseline_kdmas = _get_computed_kdma_profile(req_session, baseline_session_id)

    updates: List[Tuple[Any, Dict[str, Any]]] = []
    for doc in baseline_docs:
        target_id = _get_alignment_target(doc)
        session_alignment = _get_session_alignment(req_session, baseline_session_id, target_id)
        new_results = _build_results_object(baseline_session_id, session_alignment, baseline_kdmas)
        updates.append((doc["_id"], new_results))

        if verbose:
            print(
                f"Prepared baseline update for _id={doc['_id']} target={target_id}: "
                f"old_score={_old_score(doc)} new_score={new_results['alignment_score']} "
                f"ta1_session_id={baseline_session_id}"
            )

    return updates


def _calculate_aligned_updates(
    req_session: requests.Session,
    aligned_docs: List[Dict[str, Any]],
    verbose: bool,
) -> List[Tuple[Any, Dict[str, Any]]]:
    """
    Aligned ADMs can produce different probe responses at each target, so each
    target document gets a fresh TA1 session, alignment score, and KDMA profile.
    """
    updates: List[Tuple[Any, Dict[str, Any]]] = []

    for doc in aligned_docs:
        target_id = _get_alignment_target(doc)
        probes = _extract_probe_responses(doc)

        session_id = _create_ta1_session(req_session)
        _send_probe_responses(req_session, session_id, probes, SCENARIO)
        session_alignment = _get_session_alignment(req_session, session_id, target_id)
        kdmas = _get_computed_kdma_profile(req_session, session_id)
        new_results = _build_results_object(session_id, session_alignment, kdmas)
        updates.append((doc["_id"], new_results))

        if verbose:
            print(
                f"Prepared aligned update for _id={doc['_id']} target={target_id}: "
                f"old_score={_old_score(doc)} new_score={new_results['alignment_score']} "
                f"ta1_session_id={session_id}"
            )

    return updates


def _fake_updates_for_testing(docs: List[Dict[str, Any]], verbose: bool) -> List[Tuple[Any, Dict[str, Any]]]:
    """
    Allows redo.py smoke testing without calling ADEPT. Do not write these fake
    values to shared/dev/prod data.
    """
    updates: List[Tuple[Any, Dict[str, Any]]] = []
    for index, doc in enumerate(docs, start=1):
        target_id = _get_alignment_target(doc)
        new_results = {
            "ta1_session_id": f"fake_ta1_session_{index}",
            "alignment_score": 0.0,
            "kdmas": [],
            "alignment_warning": "FAKE RESULTS - hit_ta1_server was False",
        }
        updates.append((doc["_id"], new_results))
        if verbose:
            print(
                f"Prepared FAKE update for _id={doc['_id']} target={target_id}: "
                f"old_score={_old_score(doc)} new_score=0.0"
            )
    return updates


def _write_updates(mongo_db: Any, updates: List[Tuple[Any, Dict[str, Any]]]) -> None:
    collection = mongo_db[COLLECTION_NAME]
    modified_count = 0

    for doc_id, new_results in updates:
        result = collection.update_one(
            {"_id": doc_id},
            {"$set": {"results": new_results}},
        )
        modified_count += result.modified_count

    print(f"Wrote {len(updates)} updates to {COLLECTION_NAME}. Modified {modified_count} documents.")


def main(
    mongo_db: Any,
    write_to_db: bool = True,
    verbose: bool = False,
    strict_counts: bool = True,
    hit_ta1_server: bool = True,
) -> None:
    """
    Recalculate and update Feb2026 Open World desert scoring.

    Args are intentionally simple so redo.py can pass them positionally:
      write_to_db: False = dry-run; True = write results updates.
      verbose: True = print per-document prepared updates.
      strict_counts: True = require 16 baseline and 16 aligned documents.
      hit_ta1_server: False = fake values for smoke testing only.
    """
    collection = mongo_db[COLLECTION_NAME]
    query = {
        "evalNumber": EVAL_NUMBER,
        "scenario": SCENARIO,
        "adm_name": {"$in": TARGET_ADMS},
    }

    print("Starting Feb2026 Open World desert rescoring.")
    print(f"write_to_db={write_to_db}, verbose={verbose}, strict_counts={strict_counts}, hit_ta1_server={hit_ta1_server}")
    print(f"Query: {query}")

    docs = list(collection.find(query))
    if not docs:
        print("No matching documents found. Nothing to rescore.")
        return

    docs = sorted(docs, key=lambda doc: (doc.get("adm_name", ""), _target_sort_key(doc)))
    _print_document_summary(docs)

    if strict_counts:
        _validate_expected_counts(docs)

    baseline_docs = sorted([doc for doc in docs if doc.get("adm_name") == BASELINE_ADM], key=_target_sort_key)
    aligned_docs = sorted([doc for doc in docs if doc.get("adm_name") == ALIGNED_ADM], key=_target_sort_key)

    if not hit_ta1_server:
        if write_to_db:
            raise RuntimeError("Refusing to write fake results because hit_ta1_server=False.")
        updates = _fake_updates_for_testing(docs, verbose)
    else:
        req_session = requests.Session()
        try:
            updates = []
            updates.extend(_calculate_baseline_updates(req_session, baseline_docs, verbose))
            updates.extend(_calculate_aligned_updates(req_session, aligned_docs, verbose))
        finally:
            req_session.close()

    print(f"Prepared {len(updates)} total results update(s).")

    if not write_to_db:
        print("Dry-run complete. No MongoDB documents were updated.")
        return

    _write_updates(mongo_db, updates)
    print("Feb2026 Open World desert rescoring complete.")


if __name__ == "__main__":
    # Optional direct execution support. Normal repo usage should be through
    # deployment_script.py or redo.py.
    import argparse
    from pymongo import MongoClient

    parser = argparse.ArgumentParser(description="Rescore Feb2026 Open World desert ADM target runs.")
    parser.add_argument("--no-write", action="store_true", help="Dry-run; do not write MongoDB updates.")
    parser.add_argument("--verbose", action="store_true", help="Print per-document details.")
    parser.add_argument("--no-strict-counts", action="store_true", help="Do not require 16 baseline and 16 aligned docs.")
    parser.add_argument("--no-ta1", action="store_true", help="Do not call ADEPT; fake dry-run values only.")
    args = parser.parse_args()

    client = MongoClient(config("MONGO_URL"))
    try:
        main(
            client["dashboard"],
            write_to_db=not args.no_write,
            verbose=args.verbose,
            strict_counts=not args.no_strict_counts,
            hit_ta1_server=not args.no_ta1,
        )
    finally:
        client.close()
