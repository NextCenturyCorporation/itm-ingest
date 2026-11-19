"""Refresh February RQ8 values; keep original text KDMAs beside *_new results.

Run from the repository root with MONGO_URL and ADEPT_URL configured:
python scripts/_1_8_2_refresh_feb2026_rq8_values.py --dry-run
python scripts/_1_8_2_refresh_feb2026_rq8_values.py --pid 202602124
The deployment runner calls main(mongo_db) for the full eval 15 refresh.
"""

import argparse
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
import hashlib
import math
from pathlib import Path
import re
import sys
from threading import Lock, local
from time import perf_counter

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bson import json_util
from decouple import config
from pymongo import MongoClient
import requests

import oct2026_probe_matcher as matcher
from openworld_repop import extract_responses as openworld_responses
from text_repop import AdeptClient, SessionGroup, group_responses, profile_problem


EVAL_NUMBER = 15
MARKER = "_rq8_refresh_1_8_2"
SCHEMA_VERSION = 2
ATTRIBUTES = {"AF": "affiliation", "MF": "merit", "PS": "personal_safety", "SS": "search"}
TEXT_IDS = tuple(f"Feb2026-{attribute}{number}-assess"
                 for attribute in ATTRIBUTES for number in (1, 2))
OW_IDS = ("Feb2026-OW_desert", "Feb2026-OW_urban")
PARAMETERS = {"intercept", "attr_weight", "medical_weight"}
MISSING = object()


class RefreshError(RuntimeError):
    pass


class ScoringPool:
    def __init__(self, client_factory, workers):
        self.executor = ThreadPoolExecutor(max_workers=workers)
        self.client_factory = client_factory
        self.thread = local()
        self.clients = []
        self.lock = Lock()

    def invoke(self, function, item):
        if not hasattr(self.thread, "client"):
            self.thread.client = self.client_factory()
            with self.lock:
                self.clients.append(self.thread.client)
        return function(self.thread.client, item)

    def map(self, function, items):
        futures = {self.executor.submit(self.invoke, function, item): index for index, item in enumerate(items)}
        results = [None] * len(futures)
        try:
            for future in as_completed(futures):
                results[futures[future]] = future.result()
        except BaseException:
            for future in futures:
                future.cancel()
            # Finish running reads before replay or publication can continue.
            wait(futures)
            raise
        return results

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.executor.shutdown(wait=True)
        for client in self.clients:
            http = getattr(client, "http", None)
            if http is not None:
                http.close()


def digest(value):
    encoded = json_util.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def same(left, right):
    return digest(left) == digest(right)


def get_path(document, path):
    value = document
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return MISSING
        value = value[part]
    return value


def remove_path(document, path):
    parts = path.split(".")
    parent = document
    parents = []
    for part in parts[:-1]:
        if not isinstance(parent, dict) or part not in parent:
            return
        parents.append((parent, part))
        parent = parent[part]
    if isinstance(parent, dict):
        parent.pop(parts[-1], None)
    for parent, part in reversed(parents):
        if parent.get(part) == {}:
            parent.pop(part)


def untouched_hash(document, paths):
    remaining = copy.deepcopy(document)
    remove_path(remaining, MARKER)
    for path in paths:
        remove_path(remaining, path)
        remove_path(remaining, path + "_old")
    return digest(remaining)


def snapshot_fields(document, paths):
    fields = []
    for path in sorted(set(paths)):
        value = get_path(document, path)
        backup = get_path(document, path + "_old")
        mode = "new" if path.endswith("_new") else "original" if is_text_midpoint(path) else "replace"
        fields.append({"path": path, "mode": mode, "present": value is not MISSING,
                       "value": None if value is MISSING else copy.deepcopy(value),
                       "backup_present": backup is not MISSING,
                       "backup": None if backup is MISSING else copy.deepcopy(backup)})
    return {"id": document["_id"], "fields": fields,
            "untouched_hash": untouched_hash(document, [f["path"] for f in fields])}


def condition(query, path, value):
    # Equality with null alone also matches a missing field in MongoDB.
    query[path] = {"$exists": False} if value is MISSING else {"$eq": value, "$exists": True}


def guard_source(query, document, excluded, prefix=""):
    for key, value in document.items():
        path = prefix + "." + key if prefix else key
        if path in excluded:
            continue
        if any(exclusion.startswith(path + ".") for exclusion in excluded) and isinstance(value, dict):
            guard_source(query, value, excluded, path)
        else:
            condition(query, path, value)


def matches_value(value, expected):
    return value is expected if value is MISSING or expected is MISSING else same(value, expected)


def load_documents(db, baselines):
    ids = {}
    for baseline in baselines:
        ids.setdefault(baseline["collection"], []).append(baseline["id"])
    return {(collection, str(document["_id"])): document
            for collection, document_ids in ids.items()
            for document in db[collection].find({"evalNumber": EVAL_NUMBER, "_id": {"$in": document_ids}})}


def publish_document(collection, baseline, values, current=MISSING):
    if current is MISSING:
        current = collection.find_one({"_id": baseline["id"], "evalNumber": EVAL_NUMBER})
    if current is None:
        raise RefreshError(f"Missing eval 15 document {baseline['id']}.")
    paths = [field["path"] for field in baseline["fields"]]
    if untouched_hash(current, paths) != baseline["untouched_hash"]:
        raise RefreshError(f"Unrelated/source data changed for {baseline['id']}.")
    query = {"_id": baseline["id"], "evalNumber": EVAL_NUMBER}
    updates = {}
    unsets = {}
    for field in baseline["fields"]:
        path = field["path"]
        mode = field.get("mode", "replace")
        previous = get_path(current, path)
        original = field["value"] if field["present"] else MISSING
        if mode == "original":
            legacy = field.get("legacy_value", MISSING)
            if not matches_value(previous, original) and not matches_value(previous, legacy):
                raise RefreshError(f"Original text midpoint changed: {baseline['id']} / {path}.")
            condition(query, path, previous)
            backup = get_path(current, path + "_old")
            expected_backup = field["backup"] if field["backup_present"] else MISSING
            if not matches_value(backup, expected_backup):
                raise RefreshError(f"Original text midpoint backup changed: {path}.")
            condition(query, path + "_old", backup)
            if not matches_value(previous, original):
                if original is MISSING:
                    unsets[path] = ""
                else:
                    updates[path] = copy.deepcopy(original)
            continue
        if path not in values:
            continue
        if not ((previous is MISSING and original is MISSING)
                or (previous is not MISSING and original is not MISSING and same(previous, original))
                or (previous is not MISSING and same(previous, values[path]))):
            raise RefreshError(f"Affected field changed concurrently: {baseline['id']} / {path}.")
        backup_path = path + "_old"
        backup = get_path(current, backup_path)
        if field["backup_present"]:
            if backup is MISSING or not same(backup, field["backup"]):
                raise RefreshError(f"Existing backup changed: {baseline['id']} / {backup_path}.")
        elif backup is not MISSING and (not field["present"] or not same(backup, original)):
            raise RefreshError(f"Unexpected backup: {baseline['id']} / {backup_path}.")
        condition(query, path, previous)
        condition(query, backup_path, backup)
        if mode == "replace" and backup is MISSING and field["present"]:
            updates[backup_path] = copy.deepcopy(original)
        if previous is MISSING or not same(previous, values[path]):
            updates[path] = copy.deepcopy(values[path])
    if not updates and not unsets:
        return False
    guard_source(query, current, set(paths + [p + "_old" for p in paths] + [MARKER]))
    operations = {"$set": updates} if updates else {}
    if unsets:
        operations["$unset"] = unsets
    result = collection.update_one(query, operations, upsert=False)
    if result.matched_count != 1:
        raise RefreshError(f"Document changed before update: {baseline['id']}.")
    return True


def is_text_midpoint(path):
    return path in {f"midpoint_values.text.{name}" for name in ATTRIBUTES.values()}


def text_new_paths():
    return [f"midpoint_values.text.{name}_new" for name in ATTRIBUTES.values()] + [
        f"text_kdmas.Participant Text {short} {parameter} KDMA_new"
        for short in ATTRIBUTES for parameter in PARAMETERS
    ]


def sim_paths(document):
    environment = "Desert" if document["scenario_id"] == OW_IDS[0] else "Urban"
    return ["data.alignment.sid", "data.alignment.kdmas"] + [
        f"actionAnalysis.{short} Alignment_{environment}" for short in ("AF", "MF")
    ] + [f"midpoint_values.text.{name}" for name in ATTRIBUTES.values()] + [
        f"midpoint_values.open_world.{name}" for name in ("affiliation", "merit")
    ] + [f"midpoint_alignment_scores.{name}" for name in ("affiliation", "merit")] + text_new_paths()


def require_profile(profile, expected):
    problem = profile_problem(profile, expected)
    if problem:
        raise RefreshError(problem)
    names = set()
    for entry in profile:
        name = entry["kdma"]
        if name in names:
            raise RefreshError(f"Duplicate KDMA {name}.")
        names.add(name)
        parameters = entry.get("parameters")
        if name not in expected:
            continue
        if not isinstance(parameters, list):
            raise RefreshError(f"Missing regression parameters for {name}.")
        parameter_names = [p.get("name") for p in parameters]
        if len(parameter_names) != len(set(parameter_names)) or not PARAMETERS <= set(parameter_names):
            raise RefreshError(f"Incomplete or duplicate regression parameters for {name}.")
        for parameter in parameters:
            value = parameter.get("value")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise RefreshError(f"Invalid regression parameter for {name}.")


def participant_groups(simulations, texts):
    groups = []
    paired = {}
    for document in texts:
        match = re.fullmatch(r"Feb2026-(AF|MF|PS|SS)([12])-assess", document["scenario_id"])
        if not match:
            raise RefreshError(f"Unexpected text scenario {document['scenario_id']}.")
        short, number = match.groups()
        pair = "AF_PS" if short in ("AF", "PS") else "MF_SS"
        paired.setdefault((pair, number), []).append(document)
    for (pair, number), documents in sorted(paired.items()):
        if len(documents) != 2 or len({d["scenario_id"] for d in documents}) != 2:
            raise RefreshError(f"Incomplete or ambiguous February text group {pair}/{number}.")
        expected = {ATTRIBUTES[short] for short in pair.split("_")}
        groups.append({"key": f"text_{pair}_{number}", "kind": "text", "members": documents,
                       "field": "combinedSessionId", "expected": expected,
                       "responses": group_responses(SessionGroup("combinedSessionId", documents))})
    for document in texts:
        if "individualSessionId" in document:
            if not re.fullmatch(r"Feb2026-MF[12]-assess", document["scenario_id"]):
                raise RefreshError("Unexpected non-MF individual text session.")
            groups.append({"key": "individual_" + digest(document["_id"])[:16], "kind": "individual",
                           "members": [document], "field": "individualSessionId", "expected": {"merit"},
                           "responses": group_responses(SessionGroup("individualSessionId", [document]))})
    for document in simulations:
        groups.append({"key": "ow_" + digest(document["_id"])[:16], "kind": "open_world",
                       "members": [document], "field": "data.alignment.sid",
                       "expected": {"affiliation", "merit"}, "responses": openworld_responses(document)})
    for group in groups:
        group["input_hash"] = digest({"responses": group["responses"], "members": [d["_id"] for d in group["members"]]})
    return groups


def build_state(db, simulations, texts, groups, server):
    documents = []
    for document in simulations:
        baseline = snapshot_fields(document, sim_paths(document))
        baseline["collection"] = "humanSimulator"
        documents.append(baseline)
    original_ids = set()
    for document in texts:
        paths = ["combinedSessionId", "combinedKdmas_new"]
        if "kdmas" in document:
            paths.append("kdmas_new")
        if "individualSessionId" in document:
            paths.append("individualSessionId")
        original_ids.update(document[p] for p in ("combinedSessionId", "individualSessionId") if document.get(p))
        baseline = snapshot_fields(document, paths)
        baseline["collection"] = "userScenarioResults"
        documents.append(baseline)
    comparisons = db["humanToADMComparison"].find({
        "evalNumber": EVAL_NUMBER, "text_session_id": {"$in": sorted(original_ids)},
    })
    for document in comparisons:
        baseline = snapshot_fields(document, ["text_session_id"])
        baseline["collection"] = "humanToADMComparison"
        documents.append(baseline)
    return {"schema_version": SCHEMA_VERSION, "server": server, "phase": "populating", "sessions": {}, "documents": documents,
            "inputs": {g["key"]: g["input_hash"] for g in groups}, "updates": []}


def upgrade_state(db, legacy):
    state = copy.deepcopy(legacy)
    current_documents = load_documents(db, state["documents"])
    for baseline in state["documents"]:
        collection = baseline["collection"]
        current = current_documents.get((collection, str(baseline["id"])))
        paths = [field["path"] for field in baseline["fields"]]
        if current is None or untouched_hash(current, paths) != baseline["untouched_hash"]:
            raise RefreshError(f"Legacy source data changed: {baseline['id']}.")
        published = document_values(state, collection, baseline["id"])
        for field in baseline["fields"]:
            path = field["path"]
            original = field["value"] if field["present"] else MISSING
            expected = published.get(path, original)
            actual = get_path(current, path)
            allowed = [expected] if legacy["phase"] == "complete" else [original, expected]
            if not any(matches_value(actual, value) for value in allowed):
                raise RefreshError(f"Legacy field changed: {baseline['id']} / {path}.")
            backup = get_path(current, path + "_old")
            if field["backup_present"]:
                if not matches_value(backup, field["backup"]):
                    raise RefreshError(f"Legacy backup changed: {path}.")
            elif backup is not MISSING and not matches_value(backup, original):
                raise RefreshError(f"Unexpected legacy backup: {path}.")
            elif legacy["phase"] == "complete" and path in published and field["present"] and backup is MISSING:
                raise RefreshError(f"Missing legacy backup: {path}.")
            if is_text_midpoint(path):
                # Earlier runs replaced text midpoints. Recover the original from
                # the saved snapshot, including the difference between null and absent.
                field.update(mode="original", backup_present=backup is not MISSING,
                             backup=None if backup is MISSING else copy.deepcopy(backup))
                if path in published:
                    field["legacy_value"] = copy.deepcopy(published.pop(path))
        added = text_new_paths() if collection == "humanSimulator" else []
        if collection == "userScenarioResults":
            added = ["combinedKdmas_new"] + (["kdmas_new"] if "kdmas" in current else [])
        baseline["fields"].extend(snapshot_fields(current, added)["fields"])
        baseline["untouched_hash"] = untouched_hash(current, paths + added)
    state["schema_version"] = SCHEMA_VERSION
    state["phase"] = "text_refresh" if legacy["phase"] in ("complete", "publishing") else "populating"
    state["check_sessions"] = legacy["phase"] == "publishing"
    return state


def save_state(collection, anchor_id, previous, state):
    query = {"_id": anchor_id, "evalNumber": EVAL_NUMBER, "openWorld": True}
    condition(query, MARKER, previous if previous is not None else MISSING)
    result = collection.update_one(query, {"$set": {MARKER: state}}, upsert=False)
    if result.matched_count != 1:
        raise RefreshError("Migration state changed concurrently; run only one refresh process.")
    return copy.deepcopy(state)


def document_values(state, collection, document_id):
    for update in state["updates"]:
        if update["collection"] == collection and update["id"] == document_id:
            return update["values"]
    update = {"collection": collection, "id": document_id, "values": {}}
    state["updates"].append(update)
    return update["values"]


def fetch_profiles(state, groups, scoring):
    expected = {}
    for group in groups:
        sid = state["sessions"][group["key"]]["sid"]
        expected.setdefault(sid, set()).update(group["expected"])

    def fetch(client, item):
        sid, names = item
        profile = client.profile(sid)
        require_profile(profile, names)
        return sid, profile

    return dict(scoring.map(fetch, list(expected.items())))


def fetch_midpoints(state, groups, scoring):
    expected = {}
    for group in groups:
        if group["kind"] != "individual":
            sid = state["sessions"][group["key"]]["sid"]
            expected.setdefault(sid, set()).update(group["expected"])

    def fetch(client, item):
        sid, names = item
        profile = matcher.get_midpoint_profile(
            sid, strict=True, validate=True, http=getattr(client, "http", None),
        )
        if any(name not in profile or not matcher.is_valid_midpoint_value(profile[name]) for name in names):
            raise RefreshError(f"Incomplete midpoint profile for session {sid}.")
        return sid, profile

    return dict(scoring.map(fetch, list(expected.items())))


def fetch_text_values(state, groups, client, include_midpoints=True, profiles=None, midpoint_profiles=None):
    coefficients, midpoints = {}, {}
    cache = {}
    for group in groups:
        if group["kind"] != "text":
            continue
        sid = state["sessions"][group["key"]]["sid"]
        profile = client.profile(sid) if profiles is None else profiles[sid]
        require_profile(profile, group["expected"])
        for document in group["members"]:
            values = document_values(state, "userScenarioResults", document["_id"])
            values["combinedKdmas_new"] = profile
            if "kdmas" in document:
                values["kdmas_new"] = profile
        midpoint_profile = {}
        if include_midpoints:
            midpoint_profile = (midpoint_profiles[sid] if midpoint_profiles is not None else
                                matcher.get_midpoint_profile(sid, cache=cache, strict=True, validate=True,
                                                             http=getattr(client, "http", None)))
        for name in group["expected"]:
            short = matcher.KDMA_MAP[name]
            entry = next(item for item in profile if item["kdma"] == name)
            for parameter in entry["parameters"]:
                if parameter["name"] in PARAMETERS:
                    path = f"text_kdmas.Participant Text {short} {parameter['name']} KDMA_new"
                    if path in coefficients and not same(coefficients[path], parameter["value"]):
                        raise RefreshError(f"Conflicting refreshed text coefficient: {path}.")
                    coefficients[path] = parameter["value"]
            if include_midpoints:
                if name not in midpoint_profile or not matcher.is_valid_midpoint_value(midpoint_profile[name]):
                    raise RefreshError(f"Missing or invalid refreshed text midpoint: {name}.")
                midpoints[f"midpoint_values.text.{name}_new"] = {"sid": sid, "value": midpoint_profile[name]}
    for group in groups:
        if group["kind"] == "open_world":
            values = document_values(state, "humanSimulator", group["members"][0]["_id"])
            values.update(coefficients)
            values.update(midpoints)


def fetch_values(state, groups, client, profiles=None, scoring=None, midpoint_profiles=None):
    text_sessions = {}
    replacement_ids = {}
    original_fields = {(b["collection"], str(b["id"])): b["fields"] for b in state["documents"]}
    for group in groups:
        sid = state["sessions"][group["key"]]["sid"]
        collection = "humanSimulator" if group["kind"] == "open_world" else "userScenarioResults"
        for document in group["members"]:
            document_values(state, collection, document["_id"])[group["field"]] = sid
            for field in original_fields[(collection, str(document["_id"]))]:
                if field["path"] == group["field"] and field["present"] and field["value"]:
                    old_sid = field["value"]
                    if old_sid in replacement_ids and replacement_ids[old_sid] != sid:
                        raise RefreshError("One original session belongs to conflicting replacement groups.")
                    replacement_ids[old_sid] = sid
        if group["kind"] == "text":
            for name in group["expected"]:
                if name in text_sessions and text_sessions[name] != sid:
                    raise RefreshError(f"Ambiguous February text session for {name}.")
                text_sessions[name] = sid
    for baseline in state["documents"]:
        if baseline["collection"] == "humanToADMComparison":
            old_sid = baseline["fields"][0]["value"]
            document_values(state, baseline["collection"], baseline["id"])["text_session_id"] = replacement_ids[old_sid]
    fetch_text_values(state, groups, client, include_midpoints=False, profiles=profiles)
    midpoint_cache = {} if midpoint_profiles is None else midpoint_profiles

    def score_openworld(worker, group):
        document = group["members"][0]
        sid = state["sessions"][group["key"]]["sid"]
        profile = worker.profile(sid) if profiles is None else profiles[sid]
        require_profile(profile, group["expected"])
        values = {"data.alignment.kdmas": profile}
        http = getattr(worker, "http", None)
        regular = matcher.compute_alignment_scores(document, human_session_id=sid,
                                                   text_session_ids=text_sessions, strict=True, http=http)
        midpoints = matcher.compute_midpoint_values(document, human_session_id=sid, cache=midpoint_cache,
                                                    text_session_ids=text_sessions, strict=True, http=http)
        alignments = matcher.compute_midpoint_alignment_scores(
            document, human_session_id=sid, text_session_ids=text_sessions, strict=True, http=http,
        )
        environment = "Desert" if document["scenario_id"] == OW_IDS[0] else "Urban"
        expected_regular = {f"{short} Alignment_{environment}"
                            for short, name in (("AF", "affiliation"), ("MF", "merit")) if name in text_sessions}
        if set(regular) != expected_regular or any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            for value in regular.values()
        ):
            raise RefreshError("Missing or invalid regular alignment results.")
        if set(midpoints.get("open_world", {})) != {"affiliation", "merit"}:
            raise RefreshError("Incomplete open-world midpoint profile.")
        if set(midpoints.get("text", {})) != set(text_sessions):
            raise RefreshError("Incomplete text midpoint profile.")
        if set(alignments) != ({"affiliation", "merit"} & set(text_sessions)):
            raise RefreshError("Incomplete midpoint alignment results.")
        for modality, measurements in midpoints.items():
            for name, measurement in measurements.items():
                expected_sid = sid if modality == "open_world" else text_sessions[name]
                if (not isinstance(measurement, dict) or measurement.get("sid") != expected_sid
                        or not matcher.is_valid_midpoint_value(measurement.get("value"))):
                    raise RefreshError(f"Invalid {modality} midpoint measurement for {name}.")
        for name, measurement in alignments.items():
            if (not isinstance(measurement, dict) or measurement.get("open_world_sid") != sid
                    or measurement.get("text_sid") != text_sessions[name]
                    or not matcher.is_valid_midpoint_value(measurement.get("score"))):
                raise RefreshError(f"Invalid midpoint alignment measurement for {name}.")
        for key, score in regular.items():
            values["actionAnalysis." + key] = score
        # Honor the dashboard's precedence if this representation already exists.
        if "alignment_scores" in document:
            raise RefreshError("Unexpected February alignment_scores representation; review before updating.")
        for modality, measurements in midpoints.items():
            for name, measurement in measurements.items():
                suffix = "_new" if modality == "text" else ""
                values[f"midpoint_values.{modality}.{name}{suffix}"] = measurement
        for name, measurement in alignments.items():
            values[f"midpoint_alignment_scores.{name}"] = measurement
        return document["_id"], values

    openworld = [group for group in groups if group["kind"] == "open_world"]
    results = (scoring.map(score_openworld, openworld) if scoring is not None else
               [score_openworld(client, group) for group in openworld])
    for document_id, values in results:
        document_values(state, "humanSimulator", document_id).update(values)


def verify_documents(db, state):
    current_documents = load_documents(db, state["documents"])
    for baseline in state["documents"]:
        current = current_documents.get((baseline["collection"], str(baseline["id"])))
        if current is None or untouched_hash(current, [f["path"] for f in baseline["fields"]]) != baseline["untouched_hash"]:
            raise RefreshError(f"Verification found missing or changed unrelated data: {baseline['id']}.")
        values = document_values(state, baseline["collection"], baseline["id"])
        for field in baseline["fields"]:
            path = field["path"]
            mode = field.get("mode", "replace")
            if mode == "original":
                expected = field["value"] if field["present"] else MISSING
                if not matches_value(get_path(current, path), expected):
                    raise RefreshError(f"Original text midpoint was changed: {path}.")
                backup = field["backup"] if field["backup_present"] else MISSING
                if not matches_value(get_path(current, path + "_old"), backup):
                    raise RefreshError(f"Original text midpoint backup changed: {path}.")
                continue
            if path not in values:
                original = field["value"] if field["present"] else MISSING
                current_value = get_path(current, path)
                if not ((original is MISSING and current_value is MISSING)
                        or (original is not MISSING and current_value is not MISSING and same(original, current_value))):
                    raise RefreshError(f"Unrefreshed field changed: {baseline['id']} / {path}.")
                continue
            value = get_path(current, path)
            if value is MISSING or not same(value, values[path]):
                raise RefreshError(f"Verification mismatch: {baseline['id']} / {path}.")
            backup = get_path(current, path + "_old")
            if mode == "new":
                expected_backup = field["backup"] if field["backup_present"] else MISSING
                if not matches_value(backup, expected_backup):
                    raise RefreshError(f"Unexpected backup for rescored text field: {path}.")
                continue
            if field["backup_present"]:
                if backup is MISSING or not same(backup, field["backup"]):
                    raise RefreshError(f"Existing backup was changed: {path}.")
            elif field["present"]:
                if backup is MISSING or not same(backup, field["value"]):
                    raise RefreshError(f"Missing original backup: {path}.")
            elif backup is not MISSING:
                raise RefreshError(f"An originally absent field acquired a backup: {path}.")


def run(mongo_db, client, pids=None, dry_run=False, verify_only=False,
        scoring_workers=2, scoring_client_factory=None):
    if scoring_workers not in (1, 2):
        raise ValueError("Use one or two scoring workers.")
    if scoring_client_factory is None:
        def scoring_client_factory():
            return AdeptClient(client.url, timeout=client.timeout, http=requests.Session())

    simulations = list(mongo_db["humanSimulator"].find({"evalNumber": EVAL_NUMBER, "openWorld": True}))
    selected = {str(pid) for pid in pids} if pids else None
    participants = {}
    for document in simulations:
        if selected is not None and str(document.get("pid")) not in selected:
            continue
        if not document.get("pid") or document.get("scenario_id") not in OW_IDS:
            raise RefreshError("Unexpected eval 15 open-world participant or scenario.")
        participants.setdefault(str(document["pid"]), []).append(document)
    if not participants or (selected is not None and selected - set(participants)):
        raise RefreshError("No matching February simulator records for the requested participant(s).")
    counts = dict(participants=0, sessions_created=0, sessions_reused=0, documents_updated=0,
                  completed=0, missing_text=0, failed=0)
    plans = []
    for pid, sims in sorted(participants.items()):
        sims.sort(key=lambda d: str(d["_id"]))
        if len({d["scenario_id"] for d in sims}) != len(sims):
            raise RefreshError(f"Duplicate February environments for participant {pid}.")
        candidates = [pid] + ([int(pid)] if pid.isdigit() else [])
        texts = list(mongo_db["userScenarioResults"].find({
            "evalNumber": EVAL_NUMBER, "participantID": {"$in": candidates}, "scenario_id": {"$in": TEXT_IDS},
        }))
        texts.sort(key=lambda d: str(d["_id"]))
        groups = participant_groups(sims, texts)
        for group in groups:
            client.check_scenarios(group["responses"])
        state = sims[0].get(MARKER)
        if state is not None:
            if state.get("server") != client.url or state.get("inputs") != {g["key"]: g["input_hash"] for g in groups}:
                raise RefreshError(f"Source responses, group membership, or ADEPT server changed for {pid}.")
            if state.get("schema_version") is None:
                if verify_only:
                    raise RefreshError(f"Participant {pid} needs the text _new extension; rerun the refresh first.")
                state = upgrade_state(mongo_db, state)
            elif state.get("schema_version") != SCHEMA_VERSION:
                raise RefreshError(f"Unsupported February refresh schema for participant {pid}.")
        elif verify_only:
            raise RefreshError(f"Participant {pid} has not been refreshed.")
        else:
            state = build_state(mongo_db, sims, texts, groups, client.url)
        plans.append((pid, sims[0], texts, groups, state))
    print(f"February eval 15: {len(plans)} participants, {sum(len(p[3]) for p in plans)} session groups; dry_run={dry_run}, verify_only={verify_only}.", flush=True)
    with ScoringPool(scoring_client_factory, scoring_workers) as scoring:
        for pid, anchor, texts, groups, state in plans:
            started = perf_counter()
            timings = dict(replay=0.0, profiles=0.0, scores=0.0)
            counts["participants"] += 1
            if not texts:
                counts["missing_text"] += 1
                print(f"Participant {pid}: no recorded text assessments; refreshing open-world values only.", flush=True)
            if dry_run:
                print(f"Participant {pid}: {len(groups)} groups, {sum(len(g['responses']) for g in groups)} saved responses; no writes.", flush=True)
                continue
            try:
                if state["phase"] == "complete" or verify_only:
                    verify_documents(mongo_db, state)
                    counts["completed"] += 1
                    print(f"Participant {pid}: already complete; verified {len(state['documents'])} documents "
                          f"in {perf_counter() - started:.1f}s.", flush=True)
                    continue
                saved = copy.deepcopy(anchor.get(MARKER))
                if saved is None or saved.get("schema_version") != SCHEMA_VERSION:
                    saved = save_state(mongo_db["humanSimulator"], anchor["_id"], saved, state)
                profiles = {}
                if state["phase"] == "publishing" or state.get("check_sessions"):
                    print(f"Participant {pid}: validating saved sessions with {scoring_workers} scoring workers.", flush=True)
                    phase_started = perf_counter()
                    profiles = fetch_profiles(state, groups, scoring)
                    timings["profiles"] += perf_counter() - phase_started
                    state["check_sessions"] = False
                if state["phase"] == "populating":
                    print(f"Participant {pid}: replaying missing sessions; reusing {len(state['sessions'])} saved sessions.", flush=True)
                    phase_started = perf_counter()
                    for group in groups:
                        if state["sessions"].get(group["key"]):
                            counts["sessions_reused"] += 1
                            continue
                        sid, _ = client.populate(group["responses"], fetch_profile=False,
                                                 justification="February 2026 RQ8 refresh 1.8.2")
                        # Save only fully acknowledged replays, before expensive scoring.
                        state["sessions"][group["key"]] = {"sid": sid, "verified": False}
                        saved = save_state(mongo_db["humanSimulator"], anchor["_id"], saved, state)
                        counts["sessions_created"] += 1
                    timings["replay"] = perf_counter() - phase_started
                    print(f"Participant {pid}: validating {len(groups)} profiles with {scoring_workers} scoring workers.", flush=True)
                    phase_started = perf_counter()
                    profiles = fetch_profiles(state, groups, scoring)
                    for session in state["sessions"].values():
                        session["verified"] = True
                    saved = save_state(mongo_db["humanSimulator"], anchor["_id"], saved, state)
                    timings["profiles"] += perf_counter() - phase_started
                    print(f"Participant {pid}: fetching midpoint profiles and alignment scores.", flush=True)
                    phase_started = perf_counter()
                    midpoint_profiles = fetch_midpoints(state, groups, scoring)
                    fetch_values(state, groups, client, profiles=profiles, scoring=scoring,
                                 midpoint_profiles=midpoint_profiles)
                    timings["scores"] = perf_counter() - phase_started
                    state["phase"] = "publishing"
                    saved = save_state(mongo_db["humanSimulator"], anchor["_id"], saved, state)
                if state["phase"] == "text_refresh":
                    text_groups = [group for group in groups if group["kind"] == "text"]
                    print(f"Participant {pid}: refreshing text values with {scoring_workers} scoring workers.", flush=True)
                    phase_started = perf_counter()
                    if not profiles:
                        profiles = fetch_profiles(state, text_groups, scoring)
                    timings["profiles"] += perf_counter() - phase_started
                    phase_started = perf_counter()
                    midpoint_profiles = fetch_midpoints(state, text_groups, scoring)
                    fetch_text_values(state, groups, client, profiles=profiles, midpoint_profiles=midpoint_profiles)
                    timings["scores"] = perf_counter() - phase_started
                    state["phase"] = "publishing"
                    saved = save_state(mongo_db["humanSimulator"], anchor["_id"], saved, state)
                phase_started = perf_counter()
                current_documents = load_documents(mongo_db, state["documents"])
                for baseline in state["documents"]:
                    values = document_values(state, baseline["collection"], baseline["id"])
                    current = current_documents.get((baseline["collection"], str(baseline["id"])))
                    counts["documents_updated"] += int(publish_document(
                        mongo_db[baseline["collection"]], baseline, values, current=current,
                    ))
                verify_documents(mongo_db, state)
                state["phase"] = "complete"
                save_state(mongo_db["humanSimulator"], anchor["_id"], saved, state)
                counts["completed"] += 1
                timings["publish/verify"] = perf_counter() - phase_started
                details = ", ".join(f"{phase} {seconds:.1f}s" for phase, seconds in timings.items())
                print(f"Participant {pid}: verified {len(state['documents'])} documents "
                      f"in {perf_counter() - started:.1f}s ({details}).", flush=True)
            except Exception as error:
                counts["failed"] += 1
                print(f"Participant {pid}: FAILED after {perf_counter() - started:.1f}s: "
                      f"{type(error).__name__}: {error}", flush=True)
    print("February refresh: " + ", ".join(f"{key}={value}" for key, value in counts.items()), flush=True)
    if counts["failed"]:
        raise RefreshError(f"{counts['failed']} participant(s) incomplete; rerun the same entry point to retry.")
    return counts


def main(mongo_db, dry_run=False, pids=None, verify_only=False, scoring_workers=2):
    url = str(config("ADEPT_URL", default="") or "").strip()
    if not url:
        raise RefreshError("ADEPT_URL is required.")
    with requests.Session() as http:
        return run(mongo_db, AdeptClient(url, http=http), pids=pids, dry_run=dry_run,
                   verify_only=verify_only, scoring_workers=scoring_workers)


def cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", action="append", help="Select one participant; repeat to select several")
    parser.add_argument("--scoring-workers", type=int, choices=(1, 2), default=2,
                        help="Concurrent scoring reads; session replay and database updates remain sequential (default: 2)")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true", help="Validate saved responses and scenarios without any writes")
    modes.add_argument("--verify-only", action="store_true", help="Verify previously published values, backups, and untouched data")
    args = parser.parse_args(argv)
    mongo_url = str(config("MONGO_URL", default="") or "").strip()
    if not mongo_url:
        parser.error("MONGO_URL is required")
    try:
        with MongoClient(mongo_url, serverSelectionTimeoutMS=10000) as mongo:
            main(mongo["dashboard"], dry_run=args.dry_run, pids=args.pid,
                 verify_only=args.verify_only, scoring_workers=args.scoring_workers)
    except Exception as error:
        print(f"February refresh failed: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
