"""Session repair regressions: live validity, grouping, and failure isolation."""

from contextlib import redirect_stdout
import copy
import io
import unittest
from unittest.mock import MagicMock

import requests

import text_repop as repop


def document(attribute, sid="old", pid="120", eval_number=18, suffix=""):
    return {
        "_id": f"{pid}-{attribute}{suffix}", "participantID": pid, "evalNumber": eval_number,
        "scenario_id": f"AnyYear-{attribute}-assess{suffix}", "combinedSessionId": sid,
        "Scene 1": {"questions": {"probe Scene 1": {
            "response": "Treat Patient A.",
            "question_mapping": {"Treat Patient A": {"probe_id": f"Probe {attribute}", "choice": "A"}},
        }}},
    }


def profile(*attributes):
    return [{"kdma": repop.ATTRIBUTE_NAMES.get(attr, attr), "parameters": [
        {"name": "intercept", "value": 0.0}, {"name": "medical_weight", "value": 1.0},
    ]} for attr in attributes]


def matches(document, query):
    for key, wanted in query.items():
        actual = document.get(key)
        if isinstance(wanted, dict) and "$in" in wanted:
            if actual not in wanted["$in"]:
                return False
        elif actual != wanted:
            return False
    return True


class Collection:
    def __init__(self, documents):
        self.documents = copy.deepcopy(documents)
        self.updates = []

    def find(self, query):
        return copy.deepcopy([doc for doc in self.documents if matches(doc, query)])

    def update_one(self, query, update):
        self.updates.append((copy.deepcopy(query), copy.deepcopy(update)))
        for doc in self.documents:
            if matches(doc, query):
                for key, value in update["$set"].items():
                    target = doc
                    parts = key.split(".")
                    for part in parts[:-1]:
                        target = target.setdefault(part, {})
                    target[parts[-1]] = copy.deepcopy(value)
                return
        raise AssertionError("Update did not match a recorded document")

    def update_many(self, query, update):
        self.updates.append((copy.deepcopy(query), copy.deepcopy(update)))
        for doc in self.documents:
            if matches(doc, query):
                doc.update(copy.deepcopy(update["$set"]))


def database(documents, comparisons=()):
    return {"userScenarioResults": Collection(documents), "humanToADMComparison": Collection(comparisons)}


class Client:
    url = "http://localhost:8080/"

    def __init__(self, profiles=None, new_profile=None):
        self.profiles = profiles or {}
        self.new_profile = new_profile
        self.created = []
        self.checked = []

    def profile(self, session_id, enable_subpop="disabled"):
        result = self.profiles.get(session_id, [])
        if isinstance(result, Exception):
            raise result
        return copy.deepcopy(result)

    def check_scenarios(self, responses):
        self.checked.append(copy.deepcopy(responses))

    def populate(self, responses, enable_subpop="disabled"):
        sid = f"new-{len(self.created)}"
        self.created.append(copy.deepcopy(responses))
        if self.new_profile is not None:
            result = self.new_profile
        else:
            attributes = set().union(*(repop.scenario_attributes(item["scenario_id"]) for item in responses))
            result = profile(*sorted(attributes))
        self.profiles[sid] = copy.deepcopy(result)
        return sid, copy.deepcopy(result)


class TextRepopTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.redirect = redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def test_rebuilds_empty_profile_and_second_run_reuses_without_writes(self):
        db = database([document(attr) for attr in ("AF", "MF", "PS", "SS")])
        client = Client()
        first = repop.run(db, client, 18)
        self.assertEqual(first["recreated"], 1)
        self.assertEqual(len(client.created[0]), 4)
        self.assertTrue(all(doc["combinedSessionId"] == "new-0" for doc in db["userScenarioResults"].documents))
        db["userScenarioResults"].updates.clear()
        second = repop.run(db, client, 18)
        self.assertEqual(second["reused"], 1)
        self.assertEqual(len(client.created), 1)
        self.assertEqual(db["userScenarioResults"].updates, [])

    def test_rejects_nonfinite_missing_and_malformed_profiles(self):
        cases = [None, [], {}, [{"kdma": "merit"}],
                 [{"kdma": "merit", "value": float("nan")}],
                 [{"kdma": "merit", "value": float("inf")}],
                 [{"kdma": "merit", "parameters": [{"name": "intercept", "value": None}]}],
                 profile("AF")]
        for value in cases:
            with self.subTest(value=value):
                self.assertIsNotNone(repop.profile_problem(value, {"merit"}))
        self.assertIsNone(repop.profile_problem(profile("MF"), {"merit"}))
        self.assertIsNone(repop.profile_problem([{"kdma": "merit", "value": 0}], {"merit"}))

    def test_rebuilds_partial_profile_even_if_nonempty(self):
        db = database([document("AF"), document("MF")])
        counts = repop.run(db, Client({"old": profile("AF")}), 18)
        self.assertEqual(counts["recreated"], 1)

    def test_valid_profile_refreshes_cache_without_new_session(self):
        doc = document("MF")
        doc["combinedKdmas"] = []
        db = database([doc])
        client = Client({"old": profile("MF")})
        counts = repop.run(db, client, 18)
        self.assertEqual(counts["reused"], 1)
        self.assertEqual(client.created, [])
        self.assertEqual(db["userScenarioResults"].documents[0]["combinedKdmas"], profile("MF"))

    def test_dry_run_has_no_posts_or_mongo_writes(self):
        db = database([document("MF")])
        client = Client()
        counts = repop.run(db, client, 18, dry_run=True)
        self.assertEqual(counts["would_recreate"], 1)
        self.assertEqual(client.created, [])
        self.assertEqual(db["userScenarioResults"].updates, [])
        self.assertEqual(db["humanToADMComparison"].updates, [])

    def test_server_failure_does_not_trigger_recreation(self):
        db = database([document("MF")])
        client = Client({"old": requests.ConnectionError("offline")})
        self.assertEqual(repop.run(db, client, 18)["failed"], 1)
        self.assertEqual(client.created, [])
        self.assertEqual(db["userScenarioResults"].updates, [])

    def test_new_empty_profile_leaves_old_mongo_session_and_coefficients(self):
        doc = document("MF")
        doc["combinedKdmas"] = profile("MF")
        db = database([doc])
        counts = repop.run(db, Client(new_profile=[]), 18)
        self.assertEqual(counts["failed"], 1)
        self.assertEqual(db["userScenarioResults"].documents, [doc])
        self.assertEqual(db["humanToADMComparison"].updates, [])

    def test_preserves_pair_groups_and_separates_trinary(self):
        docs = [document("AF", "af-ps"), document("PS", "af-ps"),
                document("MF", "mf-ss"), document("SS", "mf-ss"),
                document("AF", "af-ps", suffix="-trinary")]
        groups = repop.build_groups(docs)
        self.assertEqual(sorted(len(group.documents) for group in groups), [1, 2, 2])
        self.assertEqual(len(groups), 3)

    def test_missing_id_attaches_to_only_compatible_combined_group(self):
        docs = [document("AF"), document("MF", None)]
        groups = repop.build_groups(docs)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].documents), 2)
        self.assertEqual(groups[0].old_session_id, "old")

    def test_ambiguous_missing_id_is_reported(self):
        with self.assertRaises(repop.RepopError):
            repop.build_groups([document("AF", "pair-a"), document("MF", "pair-b"), document("SS", None)])

    def test_repairs_existing_auxiliary_groups_and_legacy_profile_fields(self):
        docs = [document("MF"), document("SS")]
        for doc in docs:
            doc["MF-SS_sessionId"] = "old-pair"
            doc["MF-SS_kdmas"] = profile("MF", "SS")
            doc["kdmas"] = profile("MF", "SS")
        db = database(docs)
        counts = repop.run(db, Client(), 18)
        self.assertEqual(counts["recreated"], 2)
        for doc in db["userScenarioResults"].documents:
            self.assertNotEqual(doc["MF-SS_sessionId"], "old-pair")
            self.assertEqual(doc["combinedKdmas"], doc["kdmas"])

    def test_limits_eval_participant_and_comparison_updates(self):
        comparisons = [{"evalNumber": 18, "text_session_id": "old"},
                       {"evalNumber": 17, "text_session_id": "old"}]
        selected = document("MF", pid=120, eval_number="18")
        other = document("AF", pid="999")
        older = document("MF", pid=120, eval_number=17)
        db = database([selected, other, older], comparisons)
        repop.run(db, Client(), 18, pid="120")
        self.assertEqual(db["userScenarioResults"].documents[1:], [other, older])
        self.assertEqual(db["humanToADMComparison"].documents[0]["text_session_id"], "new-0")
        self.assertEqual(db["humanToADMComparison"].documents[1]["text_session_id"], "old")

    def test_changed_recorded_answer_rebuilds_previously_verified_session(self):
        db = database([document("MF")])
        client = Client()
        repop.run(db, client, 18)
        question = db["userScenarioResults"].documents[0]["Scene 1"]["questions"]["probe Scene 1"]
        question["question_mapping"]["Treat Patient A"]["choice"] = "B"
        self.assertEqual(repop.run(db, client, 18)["recreated"], 1)
        self.assertEqual(len(client.created), 2)

    def test_missing_mapping_fails_before_any_session_is_created(self):
        doc = document("MF")
        doc["Scene 1"]["questions"]["probe Scene 1"]["question_mapping"] = {}
        db = database([doc])
        client = Client()
        self.assertEqual(repop.run(db, client, 18)["failed"], 1)
        self.assertEqual(client.created, [])

    def test_http_not_found_is_empty_but_server_error_is_not(self):
        http = MagicMock()
        response = http.get.return_value
        response.status_code = 404
        client = repop.AdeptClient("http://localhost:8080/", http=http)
        self.assertEqual(client.profile("gone"), [])
        response.status_code = 500
        response.raise_for_status.side_effect = requests.HTTPError("server failed")
        with self.assertRaises(requests.HTTPError):
            client.profile("existing")

    def test_local_server_204_missing_scenario_is_reported_before_posts(self):
        http = MagicMock()
        http.get.return_value.status_code = 204
        client = repop.AdeptClient("http://localhost:8080/", http=http)
        self.assertEqual(client.profile("missing"), [])
        with self.assertRaisesRegex(repop.RepopError, "load its recorded text definition"):
            client.check_scenarios(repop.extract_responses(document("MF")))
        http.post.assert_not_called()

    def test_subpopulation_responses_are_seeded_before_assessments(self):
        seed = document("MF")
        seed["_id"] = "seed"
        seed["scenario_id"] = "AnyYear-subpopulation"
        group = repop.SessionGroup("combinedSessionId", [document("AF"), seed], "old")
        self.assertEqual(group.enable_subpop, "auto")
        self.assertEqual(repop.group_responses(group)[0]["scenario_id"], "AnyYear-subpopulation")

    def test_generic_custom_scenario_and_kdma_have_no_month_requirement(self):
        doc = document("MF")
        doc["scenario_id"] = "custom-scenario"
        doc["combinedKdmas"] = profile("CustomAxis")
        db = database([doc])
        client = Client(new_profile=profile("CustomAxis"))
        self.assertEqual(repop.run(db, client, 18)["recreated"], 1)
        self.assertEqual(client.created[0][0]["scenario_id"], "custom-scenario")


if __name__ == "__main__":
    unittest.main()
