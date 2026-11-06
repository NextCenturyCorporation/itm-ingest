import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import oct2026_probe_matcher as matcher


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


def main(mongo_db, dry_run=False, eval_number=18):
    if eval_number not in (18, 19):
        raise ValueError("Midpoint upload supports Canada eval 18 and UK eval 19 only.")
    if matcher.requests is None or matcher.ADEPT_URL in ("", "/"):
        raise RuntimeError("requests and ADEPT_URL are required for midpoint upload.")

    collection = mongo_db["humanSimulator"]
    text_collection = mongo_db["userScenarioResults"]
    query = {"evalNumber": eval_number, "openWorld": True}
    cache = {}
    alignment_cache = {}
    counts = dict(processed=0, planned=0, updated=0, unchanged=0, incomplete=0, failed=0)
    print(f"Midpoint upload for eval {eval_number} (dry_run={dry_run}).", flush=True)

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
                    "evalNumber": eval_number,
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload saved Canada/UK simulation midpoint values and alignment scores to MongoDB.")
    parser.add_argument("--eval-number", type=int, choices=(18, 19), default=18)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    client = matcher.initialize_mongo()
    try:
        main(client["dashboard"], dry_run=args.dry_run, eval_number=args.eval_number)
    finally:
        client.close()
