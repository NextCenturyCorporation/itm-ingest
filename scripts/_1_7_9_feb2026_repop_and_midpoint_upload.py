"""Repopulate February 2026 ADEPT sessions and upload eval 15 midpoints.

Run with ``python redo.py 179`` or preview with ``python redo.py 179 true``.
Only the combined Text and Open World sessions used for midpoint scoring
are repaired. February's PS/AF and MF/SS text session groups are preserved.
Available midpoint results are saved; missing source data or undefined ADEPT
midpoints are reported without failing the migration.
"""

import os
from pathlib import Path
import subprocess
import sys

from decouple import config

import oct2026_probe_matcher as matcher


EVAL_NUMBER = 15


def _midpoint_updates(existing, values):
    if not any(values.values()):
        return {}
    if existing is None:
        return {"midpoint_values": values}
    if not isinstance(existing, dict):
        raise ValueError("Existing midpoint_values must be an object or null.")
    updates = {}
    for modality, measurements in values.items():
        if not measurements:
            continue
        previous = existing.get(modality)
        if previous is None:
            updates[f"midpoint_values.{modality}"] = measurements
            continue
        if not isinstance(previous, dict):
            raise ValueError(f"Existing midpoint_values.{modality} must be an object or null.")
        for kdma, measurement in measurements.items():
            if previous.get(kdma) != measurement:
                updates[f"midpoint_values.{modality}.{kdma}"] = measurement
    return updates


def _score_updates(existing, scores):
    if existing is None:
        return {"$set": {"midpoint_alignment_scores": scores}} if scores else {}
    if not isinstance(existing, dict):
        raise ValueError("Existing midpoint_alignment_scores must be an object or null.")
    updates = {}
    for kdma in ("affiliation", "merit"):
        field = f"midpoint_alignment_scores.{kdma}"
        if kdma in scores:
            if existing.get(kdma) != scores[kdma]:
                updates.setdefault("$set", {})[field] = scores[kdma]
        elif kdma in existing:
            updates.setdefault("$unset", {})[field] = ""
    return updates


def upload_midpoints(mongo_db, dry_run=False):
    """Backfill February midpoint values and scores using the repaired sessions."""
    if matcher.requests is None or matcher.ADEPT_URL in ("", "/"):
        raise RuntimeError("requests and ADEPT_URL are required for midpoint upload.")

    collection = mongo_db["humanSimulator"]
    text_collection = mongo_db["userScenarioResults"]
    query = {"evalNumber": EVAL_NUMBER, "openWorld": True}
    cache = {}
    alignment_cache = {}
    counts = dict(processed=0, planned=0, updated=0, unchanged=0, incomplete=0, failed=0)
    print(f"Midpoint upload for eval {EVAL_NUMBER} (dry_run={dry_run}).", flush=True)

    for document in collection.find(query):
        counts["processed"] += 1
        try:
            if not document.get("pid"):
                raise ValueError("Participant ID is missing.")
            alignment = (document.get("data") or {}).get("alignment") or {}
            session_id = alignment.get("sid")
            values = matcher.compute_midpoint_values(
                document, human_session_id=session_id, cache=cache,
                text_collection=text_collection,
                existing_values=document.get("midpoint_values"), strict=True,
            )
            existing_scores = document.get("midpoint_alignment_scores")
            scores = matcher.compute_midpoint_alignment_scores(
                document, human_session_id=session_id, cache=alignment_cache,
                text_collection=text_collection, existing_scores=existing_scores, strict=True,
            )
            if sum(len(group) for group in values.values()) < 6 or len(scores) < 2:
                counts["incomplete"] += 1
            updates = _score_updates(existing_scores, scores)
            midpoint_updates = _midpoint_updates(document.get("midpoint_values"), values)
            if midpoint_updates:
                updates.setdefault("$set", {}).update(midpoint_updates)
            if not updates:
                counts["unchanged"] += 1
                continue
            counts["planned"] += 1
            if dry_run:
                continue
            for kdma, measurement in scores.items():
                current_text_session = matcher.find_text_session_for_alignment(
                    document, matcher.KDMA_MAP[kdma], collection=text_collection, strict=True,
                )
                if current_text_session != measurement["text_sid"]:
                    raise RuntimeError("Text session changed before its midpoint alignment update.")
            result = collection.update_one(
                {
                    "_id": document["_id"],
                    "pid": document["pid"],
                    "evalNumber": EVAL_NUMBER,
                    "openWorld": True,
                    "data.alignment.sid": session_id,
                    "midpoint_alignment_scores": existing_scores,
                },
                updates,
                upsert=False,
            )
            if result.matched_count != 1:
                raise RuntimeError("Analysis document changed or was removed before its midpoint update.")
            counts["updated"] += result.modified_count
        except Exception as e:
            counts["failed"] += 1
            matcher.logger.log(matcher.LogLevel.WARN, f"Midpoint upload failed for {document.get('_id')}: {e}")

    print("Midpoint upload: " + ", ".join(f"{key}={value}" for key, value in counts.items()), flush=True)
    if counts["failed"]:
        raise RuntimeError(f"Midpoint upload failed for {counts['failed']} document(s); rerun to retry.")
    return counts


def main(mongo_db, dry_run=False):
    if mongo_db is None:
        raise RuntimeError("The deployment framework did not provide a Mongo database.")
    for key in ("MONGO_URL", "ADEPT_URL"):
        if not str(config(key, default="") or "").strip():
            raise RuntimeError(f"{key} is not configured.")

    repo_root = Path(__file__).resolve().parent.parent
    steps = [
        (
            repo_root / "text_repop.py",
            ["--eval-number", str(EVAL_NUMBER), "--session-field", "combinedSessionId"],
        ),
        (repo_root / "openworld_repop.py", ["--eval-number", str(EVAL_NUMBER)]),
    ]
    for script, _ in steps:
        if not script.is_file():
            raise FileNotFoundError(f"Required February migration script not found: {script}")

    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    for script, arguments in steps:
        command = [sys.executable, str(script), *arguments]
        if dry_run:
            command.append("--dry-run")
        print(f"Running {script.name} for eval 15 (dry_run={dry_run})...", flush=True)
        subprocess.run(command, cwd=str(repo_root), env=environment, check=True)

    counts = upload_midpoints(mongo_db, dry_run=dry_run)
    print(
        "February 2026 repopulation and midpoint upload "
        + ("dry run completed." if dry_run else "completed."),
        flush=True,
    )
    return counts
