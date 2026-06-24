"""
June 2026 text scenario ADEPT repopulation script.

Purpose
-------
Replays June 2026 text scenario probe responses from Mongo userScenarioResults
into the ADEPT server, then writes the new ADEPT session ids back to Mongo.

This is useful when Mongo has text scenario documents, but the current ADEPT
server was rebuilt or does not have those sessions in memory/storage anymore.
The June 2026 open-world probe matcher uses userScenarioResults.combinedSessionId
from the MF and AF text documents when calling /api/v1/alignment/compare_sessions.

Expected June 2026 document shape
---------------------------------
For each participant there are normally 6 userScenarioResults documents:
- June2026-SS-assess
- June2026-MF-assess
- June2026-AF-assess
- June2026-PS-assess
- June2026-AF-assess-trinary
- June2026-PS-assess-trinary

This script creates or reuses:
- One binomial combinedSessionId for SS + MF + AF + PS
- One trinary combinedSessionId for AF-trinary + PS-trinary
- One AF-SS_sessionId for SS + AF, because June docs already contain that field
- One individualSessionId for MF, matching the older repop script behavior

By default, existing session ids are validated against ADEPT and reused when
they still exist. Use --recreate-sessions to intentionally create fresh ADEPT
sessions and overwrite the Mongo session id fields.

Only the binomial combinedSessionId is required by the current June open-world
probe matcher for MF/AF alignment, but the other sessions are useful for keeping
June text scenario documents consistent with the existing schema.
"""

import argparse
import copy
import os
import re
import sys
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

try:
    from decouple import config
except ImportError:
    def config(key: str, default: Optional[str] = None, **kwargs: Any) -> Optional[str]:
        return os.environ.get(key, default)

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None


DEFAULT_EVAL_NUMBER = 17
DEFAULT_DB_NAME = "dashboard"
SCRIPT_VERSION = "2026-06-24-dry-run-validates-existing-sessions"

BINOMIAL_SCENARIOS = {
    "June2026-SS-assess",
    "June2026-MF-assess",
    "June2026-AF-assess",
    "June2026-PS-assess",
}

TRINARY_SCENARIOS = {
    "June2026-AF-assess-trinary",
    "June2026-PS-assess-trinary",
}

AF_SS_SCENARIOS = {
    "June2026-SS-assess",
    "June2026-AF-assess",
}

MF_SCENARIOS = {
    "June2026-MF-assess",
}


def normalize_adept_url(url: Optional[str]) -> str:
    """Return ADEPT_URL with one trailing slash."""
    if not url:
        return ""
    return url.rstrip("/") + "/"


def log(message: str) -> None:
    print(message, flush=True)


def create_new_session(adept_url: str, timeout: int) -> str:
    """Create and return a fresh ADEPT session id."""
    response = requests.post(f"{adept_url}api/v1/new_session", timeout=timeout)
    response.raise_for_status()
    session_id = response.text.replace('"', "").strip()
    if not session_id:
        raise RuntimeError("ADEPT returned an empty session id")
    return session_id


def send_probe_response(
    adept_url: str,
    session_id: str,
    scenario_id: str,
    probe_id: str,
    choice: str,
    timeout: int,
) -> None:
    """Send a single text probe response to ADEPT."""
    payload = {
        "response": {
            "probe_id": probe_id,
            "choice": choice,
            "justification": "repopulated from userScenarioResults",
            "scenario_id": scenario_id,
        },
        "session_id": session_id,
    }
    response = requests.post(f"{adept_url}api/v1/response", json=payload, timeout=timeout)
    response.raise_for_status()


def get_computed_kdmas(adept_url: str, session_id: str, timeout: int) -> Optional[List[Dict[str, Any]]]:
    """Return computed KDMAs for a populated ADEPT session, if available."""
    response = requests.get(
        f"{adept_url}api/v1/computed_kdma_profile",
        params={"session_id": session_id},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else None


def validate_existing_session(
    label: str,
    adept_url: str,
    session_id: Optional[str],
    timeout: int,
    verbose: bool,
) -> Tuple[bool, Optional[List[Dict[str, Any]]]]:
    """Return whether an existing ADEPT session id is still valid."""
    if not session_id:
        log(f"  No existing {label} session id found in Mongo.")
        return False, None

    try:
        kdmas = get_computed_kdmas(adept_url, session_id, timeout)
    except Exception as exc:
        log(f"  Existing {label} session {session_id} is not valid in ADEPT: {exc}")
        return False, None

    if kdmas is None:
        log(f"  Existing {label} session {session_id} did not return a KDMA profile; will recreate if allowed.")
        return False, None

    log(f"  Existing {label} session {session_id} is valid in ADEPT; reusing it.")
    return True, kdmas


def first_common_session_id(documents: Sequence[Dict[str, Any]], field_name: str) -> Optional[str]:
    """Return the first existing session id from a group of documents."""
    for document in documents:
        value = document.get(field_name)
        if value:
            return str(value)
    return None


def unique_session_ids(documents: Sequence[Dict[str, Any]], field_name: str) -> List[str]:
    """Return sorted unique non-empty session ids from a group of documents."""
    return sorted({str(doc.get(field_name)) for doc in documents if doc.get(field_name)})


def scene_sort_key(key: str) -> Tuple[int, str]:
    """Sort Scene 1, Scene 2, ... numerically."""
    match = re.search(r"scene\s+(\d+)", str(key), re.IGNORECASE)
    if match:
        return int(match.group(1)), str(key)
    return 10_000, str(key)


def get_probe_from_scene(document: Dict[str, Any], scene_key: str) -> Optional[Dict[str, str]]:
    """Extract a single probe response from one Scene block."""
    scene = document.get(scene_key)
    if not isinstance(scene, dict):
        return None

    questions = scene.get("questions")
    if not isinstance(questions, dict):
        return None

    # Current documents use "probe Scene N", but this is intentionally flexible.
    probe = questions.get(f"probe {scene_key}")
    if not isinstance(probe, dict):
        for key, value in questions.items():
            if str(key).lower().startswith("probe ") and isinstance(value, dict):
                probe = value
                break

    if not isinstance(probe, dict):
        return None

    response_value = probe.get("response")
    mapping = probe.get("question_mapping", {})
    if not response_value or not isinstance(mapping, dict):
        return None

    response_candidates = [
        str(response_value),
        str(response_value).replace(".", ""),
        str(response_value).strip(),
        str(response_value).strip().replace(".", ""),
    ]

    mapped = None
    for candidate in response_candidates:
        mapped = mapping.get(candidate)
        if mapped:
            break

    # Last-resort fuzzy match used only for harmless punctuation differences.
    if mapped is None:
        normalized_response = re.sub(r"[^a-z0-9]+", "", str(response_value).lower())
        for mapping_key, mapping_value in mapping.items():
            normalized_key = re.sub(r"[^a-z0-9]+", "", str(mapping_key).lower())
            if normalized_key == normalized_response:
                mapped = mapping_value
                break

    if not isinstance(mapped, dict):
        return None

    probe_id = mapped.get("probe_id")
    choice = mapped.get("choice")
    if not probe_id or not choice:
        return None

    return {
        "probe_id": str(probe_id),
        "choice": str(choice),
        "response": str(response_value),
        "scene": scene_key,
    }


def extract_probes(document: Dict[str, Any]) -> List[Dict[str, str]]:
    """Extract all selected text probe responses from a userScenarioResults document."""
    scene_keys = [
        key for key, value in document.items()
        if isinstance(value, dict) and re.match(r"^Scene\s+\d+$", str(key), re.IGNORECASE)
    ]

    probes = []
    for scene_key in sorted(scene_keys, key=scene_sort_key):
        probe = get_probe_from_scene(document, scene_key)
        if probe:
            probes.append(probe)

    return probes


def send_document_probes(
    adept_url: str,
    session_id: str,
    document: Dict[str, Any],
    timeout: int,
    dry_run: bool,
    verbose: bool,
) -> int:
    """Send every extracted probe from one document to an existing ADEPT session."""
    scenario_id = str(document.get("scenario_id", ""))
    probes = extract_probes(document)

    if verbose:
        log(f"    {scenario_id}: extracted {len(probes)} probes")

    if dry_run:
        return len(probes)

    for probe in probes:
        send_probe_response(
            adept_url=adept_url,
            session_id=session_id,
            scenario_id=scenario_id,
            probe_id=probe["probe_id"],
            choice=probe["choice"],
            timeout=timeout,
        )

    return len(probes)


def scenario_id(document: Dict[str, Any]) -> str:
    return str(document.get("scenario_id", ""))


def find_docs(documents: Sequence[Dict[str, Any]], wanted: Iterable[str]) -> List[Dict[str, Any]]:
    wanted_set = set(wanted)
    return [doc for doc in documents if scenario_id(doc) in wanted_set]


def update_session_references(
    mongo_db: Any,
    old_session_id: Optional[str],
    new_session_id: str,
    dry_run: bool,
) -> None:
    """Update existing comparison references from old text session id to new one."""
    if not old_session_id or old_session_id == new_session_id:
        return

    if dry_run:
        return

    mongo_db["humanToADMComparison"].update_many(
        {"text_session_id": old_session_id},
        {"$set": {"text_session_id": new_session_id}},
    )


def update_documents(
    collection: Any,
    documents: Sequence[Dict[str, Any]],
    set_values: Dict[str, Any],
    dry_run: bool,
) -> None:
    """Apply a $set update to each supplied userScenarioResults document."""
    if dry_run:
        return

    for document in documents:
        collection.update_one(
            {"_id": document["_id"]},
            {"$set": copy.deepcopy(set_values)},
        )


def populate_session_for_docs(
    label: str,
    adept_url: str,
    documents: Sequence[Dict[str, Any]],
    timeout: int,
    dry_run: bool,
    verbose: bool,
) -> Tuple[Optional[str], int, Optional[List[Dict[str, Any]]]]:
    """Create one ADEPT session and send all selected document probes into it."""
    if not documents:
        return None, 0, None

    scenario_list = ", ".join(scenario_id(doc) for doc in documents)

    if dry_run:
        session_id = f"DRY_RUN_{label}"
        log(f"  [dry-run] Would create {label} session for: {scenario_list}")
    else:
        session_id = create_new_session(adept_url, timeout)
        log(f"  Created {label} session {session_id} for: {scenario_list}")

    total_probes = 0
    for document in documents:
        total_probes += send_document_probes(
            adept_url=adept_url,
            session_id=session_id,
            document=document,
            timeout=timeout,
            dry_run=dry_run,
            verbose=verbose,
        )

    kdmas = None
    if not dry_run:
        try:
            kdmas = get_computed_kdmas(adept_url, session_id, timeout)
        except Exception as exc:
            log(f"  Warning: could not fetch computed KDMAs for {label} session {session_id}: {exc}")

    if dry_run:
        log(f"  {label}: would send {total_probes} probes")
    else:
        log(f"  {label}: sent {total_probes} probes")
    return session_id, total_probes, kdmas


def ensure_session_for_docs(
    label: str,
    adept_url: str,
    documents: Sequence[Dict[str, Any]],
    session_field: str,
    timeout: int,
    dry_run: bool,
    verbose: bool,
    recreate_sessions: bool,
) -> Tuple[Optional[str], int, Optional[List[Dict[str, Any]]], bool]:
    """Reuse a valid existing session, or create one when needed.

    Returns (session_id, probe_count, kdmas, created_new_session).
    In dry-run mode this still validates existing sessions against ADEPT, but it
    never creates a new session or sends probe responses.
    """
    if not documents:
        return None, 0, None, False

    existing_ids = unique_session_ids(documents, session_field)
    if len(existing_ids) > 1:
        log(
            f"  Warning: found multiple existing {label} session ids in Mongo: "
            f"{', '.join(existing_ids)}. The first valid one will be reused unless --recreate-sessions is set."
        )

    if recreate_sessions:
        if existing_ids:
            log(f"  --recreate-sessions set; ignoring existing {label} session id(s): {', '.join(existing_ids)}")
        else:
            log(f"  --recreate-sessions set; no existing {label} session id was found.")
    else:
        if not existing_ids:
            log(f"  No existing {label} session id found in Mongo.")
        for existing_id in existing_ids:
            is_valid, kdmas = validate_existing_session(
                label=label,
                adept_url=adept_url,
                session_id=existing_id,
                timeout=timeout,
                verbose=verbose,
            )
            if is_valid:
                return existing_id, 0, kdmas, False

    return (*populate_session_for_docs(
        label=label,
        adept_url=adept_url,
        documents=documents,
        timeout=timeout,
        dry_run=dry_run,
        verbose=verbose,
    ), True)


def process_participant(
    mongo_db: Any,
    participant_id: Any,
    documents: Sequence[Dict[str, Any]],
    adept_url: str,
    timeout: int,
    dry_run: bool,
    verbose: bool,
    update_af_ss: bool,
    update_trinary: bool,
    update_mf_individual: bool,
    recreate_sessions: bool,
) -> None:
    """Repopulate all text ADEPT sessions for one participant."""
    collection = mongo_db["userScenarioResults"]

    documents = sorted(documents, key=lambda doc: scenario_id(doc))
    present = {scenario_id(doc) for doc in documents}

    log(f"\nParticipant {participant_id}: {len(documents)} text documents")
    if verbose:
        log(f"  Scenarios: {', '.join(sorted(present))}")

    missing_binomial = BINOMIAL_SCENARIOS - present
    if missing_binomial:
        log(f"  Warning: missing binomial scenarios: {', '.join(sorted(missing_binomial))}")

    # Required by the current June open-world probe matcher: MF and AF docs need
    # a combinedSessionId that exists in the current ADEPT server.
    binomial_docs = find_docs(documents, BINOMIAL_SCENARIOS)
    if binomial_docs:
        old_combined_ids = unique_session_ids(binomial_docs, "combinedSessionId")

        combined_sid, _, combined_kdmas, created = ensure_session_for_docs(
            label="combined binomial",
            adept_url=adept_url,
            documents=binomial_docs,
            session_field="combinedSessionId",
            timeout=timeout,
            dry_run=dry_run,
            verbose=verbose,
            recreate_sessions=recreate_sessions,
        )

        if combined_sid and created:
            set_values = {"combinedSessionId": combined_sid}
            if combined_kdmas is not None:
                set_values["combinedKdmas"] = combined_kdmas
            update_documents(collection, binomial_docs, set_values, dry_run)
            for old_sid in old_combined_ids:
                update_session_references(mongo_db, old_sid, combined_sid, dry_run)

    if update_af_ss:
        af_ss_docs = find_docs(documents, AF_SS_SCENARIOS)
        if af_ss_docs:
            old_af_ss_ids = unique_session_ids(af_ss_docs, "AF-SS_sessionId")

            af_ss_sid, _, af_ss_kdmas, created = ensure_session_for_docs(
                label="AF-SS",
                adept_url=adept_url,
                documents=af_ss_docs,
                session_field="AF-SS_sessionId",
                timeout=timeout,
                dry_run=dry_run,
                verbose=verbose,
                recreate_sessions=recreate_sessions,
            )

            if af_ss_sid and created:
                set_values = {"AF-SS_sessionId": af_ss_sid}
                if af_ss_kdmas is not None:
                    set_values["AF-SS_kdmas"] = af_ss_kdmas
                update_documents(collection, af_ss_docs, set_values, dry_run)
                for old_sid in old_af_ss_ids:
                    update_session_references(mongo_db, old_sid, af_ss_sid, dry_run)

    if update_trinary:
        trinary_docs = find_docs(documents, TRINARY_SCENARIOS)
        if trinary_docs:
            old_trinary_ids = unique_session_ids(trinary_docs, "combinedSessionId")

            trinary_sid, _, trinary_kdmas, created = ensure_session_for_docs(
                label="combined trinary",
                adept_url=adept_url,
                documents=trinary_docs,
                session_field="combinedSessionId",
                timeout=timeout,
                dry_run=dry_run,
                verbose=verbose,
                recreate_sessions=recreate_sessions,
            )

            if trinary_sid and created:
                set_values = {"combinedSessionId": trinary_sid}
                if trinary_kdmas is not None:
                    set_values["combinedKdmas"] = trinary_kdmas
                update_documents(collection, trinary_docs, set_values, dry_run)
                for old_sid in old_trinary_ids:
                    update_session_references(mongo_db, old_sid, trinary_sid, dry_run)

    if update_mf_individual:
        mf_docs = find_docs(documents, MF_SCENARIOS)
        for mf_doc in mf_docs:
            old_individual_sid = mf_doc.get("individualSessionId")
            mf_sid, _, mf_kdmas, created = ensure_session_for_docs(
                label="MF individual",
                adept_url=adept_url,
                documents=[mf_doc],
                session_field="individualSessionId",
                timeout=timeout,
                dry_run=dry_run,
                verbose=verbose,
                recreate_sessions=recreate_sessions,
            )

            if mf_sid and created:
                set_values = {"individualSessionId": mf_sid}
                if mf_kdmas is not None:
                    set_values["individualKdmas"] = mf_kdmas
                update_documents(collection, [mf_doc], set_values, dry_run)
                update_session_references(mongo_db, old_individual_sid, mf_sid, dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Repopulate ADEPT sessions for June 2026 text scenario results."
    )
    parser.add_argument("--eval-number", type=int, default=DEFAULT_EVAL_NUMBER)
    parser.add_argument("--mongo-url", default=config("MONGO_URL", default=""))
    parser.add_argument("--adept-url", default=config("ADEPT_URL", default=""))
    parser.add_argument("--db-name", default=DEFAULT_DB_NAME)
    parser.add_argument("--pid", help="Optional participantID to process for a test run")
    parser.add_argument("--dry-run", action="store_true", help="Validate existing ADEPT sessions and print what would be done without creating sessions or updating Mongo")
    parser.add_argument("--recreate-sessions", action="store_true", help="Ignore valid existing session IDs and create fresh ADEPT sessions")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--skip-af-ss", action="store_true", help="Do not create/update AF-SS_sessionId")
    parser.add_argument("--skip-trinary", action="store_true", help="Do not create/update trinary combinedSessionId")
    parser.add_argument("--skip-mf-individual", action="store_true", help="Do not create/update MF individualSessionId")
    args = parser.parse_args()

    if MongoClient is None:
        log("Error: pymongo is not installed.")
        return 1

    mongo_url = args.mongo_url
    adept_url = normalize_adept_url(args.adept_url)

    if not mongo_url:
        log("Error: MONGO_URL is not set. Set it in .env or pass --mongo-url.")
        return 1

    if not adept_url:
        log("Error: ADEPT_URL is not set. Set it in .env or pass --adept-url.")
        return 1

    query: Dict[str, Any] = {"evalNumber": args.eval_number}
    if args.pid:
        # participantID may be stored as string or int depending on ingest.
        pid_candidates: List[Any] = [args.pid]
        if str(args.pid).isdigit():
            pid_candidates.append(int(args.pid))
        query["participantID"] = {"$in": pid_candidates}

    log(f"Running {os.path.basename(__file__)} version {SCRIPT_VERSION}")
    log(f"Script path: {os.path.abspath(__file__)}")
    log(f"Connecting to Mongo database '{args.db_name}'")
    client = MongoClient(mongo_url)
    mongo_db = client[args.db_name]

    documents = list(mongo_db["userScenarioResults"].find(query))
    if not documents:
        log(f"No userScenarioResults found for query: {query}")
        return 0

    participant_groups: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for document in documents:
        participant_groups[document.get("participantID")].append(document)

    log(f"Found {len(documents)} text documents for {len(participant_groups)} participant(s).")
    if args.dry_run:
        log("Dry run enabled: existing ADEPT sessions will be validated, but no sessions will be created and Mongo will not be updated.")

    for participant_id, participant_docs in sorted(participant_groups.items(), key=lambda item: str(item[0])):
        try:
            process_participant(
                mongo_db=mongo_db,
                participant_id=participant_id,
                documents=participant_docs,
                adept_url=adept_url,
                timeout=args.timeout,
                dry_run=args.dry_run,
                verbose=args.verbose,
                update_af_ss=not args.skip_af_ss,
                update_trinary=not args.skip_trinary,
                update_mf_individual=not args.skip_mf_individual,
                recreate_sessions=args.recreate_sessions,
            )
        except Exception as exc:
            log(f"Error processing participant {participant_id}: {exc}")

    log("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
