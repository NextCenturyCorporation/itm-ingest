"""Repair recorded ADEPT text sessions for a selected evaluation.

Usage: py text_repop.py --eval-number 18 --dry-run -v

Scenario IDs and session groups come from userScenarioResults, not a month or
evaluation-specific list. Empty/non-finite/incomplete live profiles are rebuilt.
Network/service failures abort a group instead of overwriting stored session IDs.
"""

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
import hashlib
import json
import math
import re
from typing import Any, Dict, List, Optional

import requests
from decouple import config
from pymongo import MongoClient


ATTRIBUTE_NAMES = {"AF": "affiliation", "MF": "merit", "PS": "personal_safety", "SS": "search"}
CORE_SESSION_FIELDS = {"combinedSessionId", "individualSessionId", "serverSessionId"}


class RepopError(RuntimeError):
    pass


def profile_fields(session_field, document):
    if session_field == "combinedSessionId":
        return ["combinedKdmas"] + (["kdmas"] if "kdmas" in document else [])
    if session_field == "individualSessionId":
        return ["individualKdmas"]
    if session_field == "serverSessionId":
        return ["kdmas"]
    return [session_field[:-len("_sessionId")] + "_kdmas"]


def numeric_values_are_finite(value):
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (list, tuple)):
        return bool(value) and all(numeric_values_are_finite(item) for item in value)
    if isinstance(value, dict):
        return bool(value) and all(numeric_values_are_finite(item) for item in value.values())
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def profile_problem(profile, expected_kdmas):
    """Return a reason to rebuild, or None for a usable live profile."""
    if not isinstance(profile, list) or not profile:
        return "empty or malformed KDMA profile"
    names = set()
    for entry in profile:
        if not isinstance(entry, dict) or not isinstance(entry.get("kdma"), str) or not entry["kdma"]:
            return "KDMA entry has no name"
        names.add(entry["kdma"])
        parameters = entry.get("parameters")
        if parameters:
            if not isinstance(parameters, list) or any(
                not isinstance(param, dict) or not param.get("name")
                or not numeric_values_are_finite(param.get("value")) for param in parameters
            ):
                return "KDMA parameters contain missing or non-finite values"
        elif not numeric_values_are_finite(entry.get("value")):
            return "KDMA entry has no finite value or parameters"
    missing = expected_kdmas - names
    if missing:
        return "missing expected KDMAs: " + ", ".join(sorted(missing))
    return None


def cached_names(document, session_field):
    names = set()
    for key in profile_fields(session_field, document):
        profile = document.get(key)
        if isinstance(profile, list):
            names.update(item["kdma"] for item in profile if isinstance(item, dict) and item.get("kdma"))
    return names


def scenario_attributes(scenario_id):
    tokens = re.findall(r"(?:^|[-_])(AF|MF|PS|SS)(?=\d*(?:[-_]|$))", scenario_id, re.IGNORECASE)
    return {ATTRIBUTE_NAMES[token.upper()] for token in tokens}


def response_family(document):
    """Keep binary and trinary assessments separate even with a corrupt shared ID."""
    return "trinary" if re.search(r"(?:-|_)trinary$", str(document.get("scenario_id", "")), re.I) else "binary"


def extract_responses(document):
    """Read selected responses from Scene/questions blocks or an explicit probes list."""
    scenario_id = str(document.get("scenario_id") or "")
    if not scenario_id:
        raise RepopError("Text result is missing scenario_id")
    responses = []
    if isinstance(document.get("probes"), list):
        for probe in document["probes"]:
            if not isinstance(probe, dict) or not probe.get("probe_id") or not probe.get("choice"):
                raise RepopError(f"{scenario_id}: malformed recorded probe")
            responses.append({"scenario_id": str(probe.get("scenario_id") or scenario_id),
                              "probe_id": str(probe["probe_id"]), "choice": str(probe["choice"])})
        return responses

    scenes = [(key, value) for key, value in document.items()
              if isinstance(value, dict) and re.match(r"^Scene\s+\d+$", str(key), re.I)]
    scenes.sort(key=lambda item: (int(re.search(r"\d+", str(item[0])).group()), str(item[0])))
    for scene_key, scene in scenes:
        questions = scene.get("questions", {})
        if not isinstance(questions, dict):
            raise RepopError(f"{scenario_id}/{scene_key}: malformed questions")
        for question_key, question in questions.items():
            if not isinstance(question, dict) or not str(question_key).lower().startswith("probe "):
                continue
            answer = question.get("response")
            if answer is None or answer == "":
                continue
            mapping = question.get("question_mapping", {})
            mapped = None
            if isinstance(mapping, dict):
                mapped = mapping.get(str(answer))
                if mapped is None:
                    normalized = re.sub(r"[^a-z0-9]", "", str(answer).lower())
                    matches = [value for key, value in mapping.items()
                               if re.sub(r"[^a-z0-9]", "", str(key).lower()) == normalized]
                    if len(matches) == 1:
                        mapped = matches[0]
            if not isinstance(mapped, dict) or not mapped.get("probe_id") or not mapped.get("choice"):
                raise RepopError(f"{scenario_id}/{scene_key}: selected answer has no probe/choice mapping")
            responses.append({"scenario_id": scenario_id, "probe_id": str(mapped["probe_id"]),
                              "choice": str(mapped["choice"])})
    return responses


@dataclass
class SessionGroup:
    session_field: str
    documents: List[Dict[str, Any]] = field(default_factory=list)
    old_session_id: Optional[str] = None

    @property
    def enable_subpop(self):
        return "auto" if any(str(doc.get("scenario_id", "")).lower().endswith("subpopulation")
                             for doc in self.documents) else "disabled"

    @property
    def expected_kdmas(self):
        expected = set()
        for document in self.documents:
            expected.update(cached_names(document, self.session_field))
            attributes = scenario_attributes(str(document.get("scenario_id", "")))
            if self.session_field.endswith("_sessionId"):
                attributes &= scenario_attributes(self.session_field[:-len("_sessionId")])
            expected.update(attributes)
        return expected

    @property
    def label(self):
        return self.session_field + " [" + ", ".join(str(doc.get("scenario_id")) for doc in self.documents) + "]"


def build_groups(documents, selected_fields=None):
    """Preserve shared session IDs; infer a missing ID only when unambiguous."""
    groups = {}
    pending = []
    for document in sorted(documents, key=lambda doc: (str(doc.get("scenario_id")), str(doc.get("_id")))):
        available = {key for key in document if key in CORE_SESSION_FIELDS or key.endswith("_sessionId")}
        if "serverSessionId" not in document or "combinedSessionId" in document:
            available.add("combinedSessionId")
        if selected_fields:
            available &= set(selected_fields)
        for session_field in sorted(available):
            family = response_family(document)
            sid = document.get(session_field)
            if sid:
                key = (session_field, family, str(sid))
                group = groups.setdefault(key, SessionGroup(session_field, old_session_id=str(sid)))
                group.documents.append(document)
            else:
                pending.append((session_field, family, document))

    for session_field, family, document in pending:
        possible = [group for (key_field, key_family, _), group in groups.items()
                    if key_field == session_field and key_family == family]
        if session_field in ("individualSessionId", "serverSessionId"):
            possible = []
        names = cached_names(document, session_field)
        if len(possible) > 1 and names:
            possible = [group for group in possible if group.expected_kdmas == names]
        if len(possible) > 1:
            raise RepopError(f"Cannot infer the missing {session_field} group for {document.get('scenario_id')}")
        if possible:
            possible[0].documents.append(document)
        else:
            # New combined groups collect a family's assessments. Per-scenario
            # session fields must remain individual when their IDs are missing.
            discriminator = str(document.get("_id")) if session_field in ("individualSessionId", "serverSessionId") else "missing"
            key = (session_field, family, discriminator)
            groups.setdefault(key, SessionGroup(session_field)).documents.append(document)
    return list(groups.values())


def group_responses(group):
    responses = {}
    # Sessions seeded by subpopulation responses retain that ordering.
    ordered = sorted(group.documents, key=lambda doc: not str(doc.get("scenario_id", "")).lower().endswith("subpopulation"))
    for document in ordered:
        extracted = extract_responses(document)
        if not extracted:
            raise RepopError(f"{document.get('scenario_id')}: no recorded responses to replay")
        for response in extracted:
            key = (response["scenario_id"], response["probe_id"])
            if key in responses and responses[key]["choice"] != response["choice"]:
                raise RepopError(f"Conflicting recorded choices for {key[0]} / {key[1]}")
            responses[key] = response
    return list(responses.values())


def response_fingerprint(responses, adept_url, enable_subpop="disabled"):
    payload = {"adept_url": adept_url, "enable_subpop": enable_subpop,
               "responses": sorted(responses, key=lambda item: (item["scenario_id"], item["probe_id"]))}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


class AdeptClient:
    def __init__(self, url, timeout=120, http=None):
        self.url = url.rstrip("/") + "/"
        self.timeout = timeout
        self.http = http or requests.Session()
        self.checked_scenarios = set()

    def profile(self, session_id, enable_subpop="disabled"):
        params = {"session_id": session_id}
        if enable_subpop != "disabled":
            params["enable_subpop"] = enable_subpop
        response = self.http.get(self.url + "api/v1/computed_kdma_profile",
                                 params=params, timeout=self.timeout)
        if response.status_code in (204, 404, 410):
            return []
        response.raise_for_status()
        return response.json()

    def check_scenarios(self, responses):
        for scenario_id in sorted({response["scenario_id"] for response in responses}):
            if scenario_id in self.checked_scenarios:
                continue
            response = self.http.get(self.url + "api/v1/scenario/" + requests.utils.quote(scenario_id, safe=""),
                                     timeout=self.timeout)
            if response.status_code in (204, 404, 410):
                raise RepopError(f"Scenario {scenario_id} is unavailable on ADEPT; load its recorded text definition first")
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("id") != scenario_id:
                raise RepopError(f"ADEPT did not return a scenario definition for {scenario_id}")
            self.checked_scenarios.add(scenario_id)

    def populate(self, responses, enable_subpop="disabled"):
        response = self.http.post(self.url + "api/v1/new_session", timeout=self.timeout)
        response.raise_for_status()
        try:
            session_id = response.json()
        except ValueError:
            session_id = response.text.strip().strip('"')
        if not isinstance(session_id, str) or not session_id.strip():
            raise RepopError("ADEPT returned no new session ID")
        for selected in responses:
            response = self.http.post(self.url + "api/v1/response",
                                      json={"session_id": session_id, "response": dict(
                                          selected, justification="repopulated from userScenarioResults")},
                                      timeout=self.timeout)
            response.raise_for_status()
        return session_id, self.profile(session_id, enable_subpop)


def repair_group(db, client, group, eval_number, dry_run=False, recreate=False, verbose=False):
    responses = group_responses(group)
    fingerprint = response_fingerprint(responses, client.url, group.enable_subpop)
    problem = "no stored session ID" if not group.old_session_id else None
    profile = None
    if recreate:
        problem = "forced recreation"
    elif group.old_session_id:
        # Transport errors deliberately propagate: an unavailable server is
        # different from an empty session, and must not trigger Mongo changes.
        profile = client.profile(group.old_session_id, group.enable_subpop)
        problem = profile_problem(profile, group.expected_kdmas)
        if problem is None:
            for doc in group.documents:
                previous = (doc.get("textRepop") or {}).get(group.session_field, {}).get("fingerprint")
                if previous and previous != fingerprint:
                    problem = "recorded responses or ADEPT endpoint changed"
                    break

    if problem:
        client.check_scenarios(responses)
        if dry_run:
            print(f"  Would recreate {group.label}: {problem}; {len(responses)} responses", flush=True)
            return "would_recreate"
        session_id, profile = client.populate(responses, group.enable_subpop)
        new_problem = profile_problem(profile, group.expected_kdmas)
        if new_problem:
            raise RepopError(f"New session {session_id} is unusable ({new_problem}); Mongo was not updated for this group")
        print(f"  Recreated {group.label}: {problem}; {len(responses)} responses", flush=True)
        outcome = "recreated"
    else:
        session_id = group.old_session_id
        if verbose:
            print(f"  Reusing {group.label}: live profile contains finite expected KDMAs", flush=True)
        if dry_run:
            return "reused"
        outcome = "reused"

    # Save the session ID and its verified profile together, including repaired
    # missing IDs and stale cached profiles when an existing session is reused.
    for doc in group.documents:
        metadata = {"fingerprint": fingerprint}
        values = {group.session_field: session_id,
                  f"textRepop.{group.session_field}": metadata}
        for key in profile_fields(group.session_field, doc):
            values[key] = profile
        changed = doc.get(group.session_field) != session_id or any(
            doc.get(key) != profile for key in profile_fields(group.session_field, doc)
        ) or (doc.get("textRepop") or {}).get(group.session_field) != metadata
        if changed:
            db["userScenarioResults"].update_one(
                {"_id": doc["_id"], "evalNumber": {"$in": [eval_number, str(eval_number)]}}, {"$set": values}
            )
    if group.old_session_id and group.old_session_id != session_id:
        db["humanToADMComparison"].update_many(
            {"evalNumber": {"$in": [eval_number, str(eval_number)]}, "text_session_id": group.old_session_id},
            {"$set": {"text_session_id": session_id}},
        )
    return outcome


def run(db, client, eval_number, pid=None, dry_run=False, recreate=False, selected_fields=None, verbose=False):
    query = {"evalNumber": {"$in": [eval_number, str(eval_number)]}}
    if pid is not None:
        candidates = [str(pid)]
        if str(pid).isdigit():
            candidates.append(int(pid))
        query["participantID"] = {"$in": candidates}
    documents = list(db["userScenarioResults"].find(query))
    participants = defaultdict(list)
    for document in documents:
        participant_id = document.get("participantID")
        if participant_id is None:
            raise RepopError(f"Text document {document.get('_id')} is missing participantID")
        participants[str(participant_id)].append(document)
    counts = defaultdict(int)
    print(f"Eval {eval_number}: {len(documents)} text records, {len(participants)} participants", flush=True)
    if dry_run:
        print("Dry run: ADEPT reads only; no sessions or Mongo records will be changed.", flush=True)
    for participant_id, docs in sorted(participants.items()):
        print(f"Participant {participant_id}", flush=True)
        try:
            groups = build_groups(docs, selected_fields)
        except RepopError as exc:
            print(f"  ERROR: {exc}", flush=True)
            counts["failed"] += 1
            continue
        for group in groups:
            try:
                outcome = repair_group(db, client, group, eval_number, dry_run, recreate, verbose)
                counts[outcome] += 1
            except (RepopError, requests.RequestException, ValueError) as exc:
                print(f"  ERROR: {group.label}: {exc}", flush=True)
                counts["failed"] += 1
    print("Summary: " + ", ".join(f"{key}={counts[key]}" for key in
                                 ("reused", "recreated", "would_recreate", "failed")), flush=True)
    return dict(counts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-number", "-e", type=int, required=True)
    parser.add_argument("--pid", help="Process only one participant (string/int IDs both supported)")
    parser.add_argument("--mongo-url", default=config("MONGO_URL", default=""))
    parser.add_argument("--adept-url", default=config("ADEPT_URL", default=""))
    parser.add_argument("--db-name", default="dashboard")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--recreate-sessions", action="store_true", help="Rebuild even usable sessions")
    parser.add_argument("--session-field", action="append", help="Repair only this recorded session field; may be repeated")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)
    if not args.mongo_url or not args.adept_url:
        parser.error("Set MONGO_URL and ADEPT_URL in .env or pass --mongo-url and --adept-url")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    for name in args.session_field or []:
        if name not in CORE_SESSION_FIELDS and not name.endswith("_sessionId"):
            parser.error(f"Unsupported session field: {name}")
    try:
        with MongoClient(args.mongo_url, serverSelectionTimeoutMS=int(args.timeout * 1000)) as mongo:
            with requests.Session() as http:
                counts = run(mongo[args.db_name], AdeptClient(args.adept_url, args.timeout, http),
                             args.eval_number, args.pid, args.dry_run, args.recreate_sessions,
                             args.session_field, args.verbose)
        return 1 if counts.get("failed") else 0
    except (RepopError, requests.RequestException, ValueError) as exc:
        print(f"ERROR: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
