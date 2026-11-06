import argparse

import oct2026_probe_matcher as matcher
from text_repop import AdeptClient, RepopError, profile_problem, scenario_attributes


def extract_responses(document):
    scenario_id = document.get("scenario_id")
    if not isinstance(scenario_id, str) or not scenario_id.strip():
        raise RepopError("Open World analysis is missing its recorded scenario_id.")
    data = document.get("data")
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise RepopError("Open World analysis has no saved probe-match rows.")
    responses = {}
    for row in rows:
        if not isinstance(row, dict):
            raise RepopError("Malformed saved probe-match row.")
        if not row.get("found_match"):
            continue
        probe_id = row.get("probe_id")
        choice = row.get("response")
        if not all(isinstance(value, str) and value.strip() for value in (probe_id, choice)):
            raise RepopError("Matched probe is missing its recorded probe_id or response.")
        response = {"scenario_id": scenario_id, "probe_id": probe_id, "choice": choice}
        if probe_id in responses and responses[probe_id] != response:
            raise RepopError(f"Conflicting saved choices for {probe_id}.")
        responses[probe_id] = response
    if not responses:
        raise RepopError("No matched probe responses are available to replay.")
    return list(responses.values())


def run(mongo_db, client, eval_number=18, pid=None, dry_run=False, verbose=False):
    if eval_number not in (18, 19):
        raise ValueError("Open World repopulation supports Canada eval 18 and UK eval 19 only.")
    query = {"evalNumber": eval_number, "openWorld": True}
    if pid is not None:
        candidates = [str(pid)]
        if str(pid).isdigit():
            candidates.append(int(pid))
        query["pid"] = {"$in": candidates}
    collection = mongo_db["humanSimulator"]
    counts = dict(reused=0, recreated=0, would_recreate=0, failed=0)
    print(f"Open World repopulation for eval {eval_number} (dry_run={dry_run}).", flush=True)

    for document in collection.find(query):
        label = document.get("_id")
        try:
            if label is None or not document.get("pid"):
                raise RepopError("Open World analysis is missing its document or participant ID.")
            responses = extract_responses(document)
            expected = set().union(*(scenario_attributes(response["probe_id"]) for response in responses))
            if not expected:
                raise RepopError("Cannot identify KDMAs from the saved probe IDs.")
            alignment = document["data"].get("alignment")
            if alignment is not None and not isinstance(alignment, dict):
                raise RepopError("Open World alignment must be an object or null.")
            old_session_id = (alignment or {}).get("sid")
            problem = "no stored session ID"
            if old_session_id:
                problem = profile_problem(client.profile(str(old_session_id)), expected)
            if problem is None:
                counts["reused"] += 1
                if verbose:
                    print(f"  Reusing {label}: session {old_session_id} has a usable live profile.", flush=True)
                continue

            client.check_scenarios(responses)
            if dry_run:
                counts["would_recreate"] += 1
                print(f"  Would recreate {label}: {problem}; {len(responses)} saved responses.", flush=True)
                continue

            session_id, profile = client.populate(
                responses, justification="repopulated from humanSimulator probe matches",
            )
            new_problem = profile_problem(profile, expected)
            if new_problem:
                raise RepopError(f"Replacement session is unusable ({new_problem}); stored session ID was not changed.")
            # Publish the replacement only after every saved response and its profile succeed.
            updates = {"data.alignment.sid": session_id} if alignment is not None else {
                "data.alignment": {"sid": session_id},
            }
            result = collection.update_one(
                {
                    "_id": label, "pid": document["pid"],
                    "evalNumber": eval_number, "openWorld": True,
                    "scenario_id": document["scenario_id"],
                    "data.alignment.sid": old_session_id,
                    "data.data": document["data"]["data"],
                },
                {"$set": updates},
                upsert=False,
            )
            if result.matched_count != 1:
                raise RepopError("Analysis changed or was removed before its session update; rerun to retry.")
            counts["recreated"] += 1
            print(f"  Recreated {label}: {old_session_id} -> {session_id}; {len(responses)} saved responses.", flush=True)
        except Exception as error:
            counts["failed"] += 1
            matcher.logger.log(matcher.LogLevel.WARN, f"Open World repopulation failed for {label}: {error}")

    print("Open World repopulation: " + ", ".join(f"{key}={value}" for key, value in counts.items()), flush=True)
    return counts


def main(mongo_db, dry_run=False, eval_number=18, pid=None, verbose=False):
    if matcher.requests is None or matcher.ADEPT_URL in ("", "/"):
        raise RuntimeError("requests and ADEPT_URL are required for Open World repopulation.")
    with matcher.requests.Session() as http:
        counts = run(
            mongo_db, AdeptClient(matcher.ADEPT_URL, http=http),
            eval_number=eval_number, pid=pid, dry_run=dry_run, verbose=verbose,
        )
    if counts["failed"]:
        raise RepopError(f"Open World repopulation failed for {counts['failed']} document(s); rerun to retry.")
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Restore missing ADEPT Open World sessions from saved MongoDB probe matches.")
    parser.add_argument("--eval-number", "-e", type=int, choices=(18, 19), default=18)
    parser.add_argument("--pid", help="Restore sessions for one participant only")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    mongo_client = matcher.initialize_mongo()
    try:
        main(mongo_client["dashboard"], args.dry_run, args.eval_number, args.pid, args.verbose)
    finally:
        mongo_client.close()
