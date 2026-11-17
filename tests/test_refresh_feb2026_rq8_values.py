import copy
import importlib
import io
import unittest
from contextlib import ExitStack, redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch


MISSING = object()


def get_path(document, path, default=MISSING):
    value = document
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    return value


def set_path(document, path, value):
    parts = path.split(".")
    parent = document
    for part in parts[:-1]:
        parent = parent.setdefault(part, {})
    parent[parts[-1]] = copy.deepcopy(value)


def matches(document, query):
    for path, expected in query.items():
        if path == "$and":
            if not all(matches(document, item) for item in expected):
                return False
            continue
        if path == "$or":
            if not any(matches(document, item) for item in expected):
                return False
            continue
        actual = get_path(document, path)
        if isinstance(expected, dict) and any(key.startswith("$") for key in expected):
            for operator, operand in expected.items():
                if operator == "$exists" and (actual is not MISSING) != operand:
                    return False
                if operator == "$in" and actual not in operand:
                    return False
                if operator == "$nin" and actual in operand:
                    return False
                if operator == "$ne" and actual == operand:
                    return False
                if operator == "$eq" and actual != operand:
                    return False
                if operator not in ("$exists", "$in", "$nin", "$ne", "$eq"):
                    raise AssertionError("Unsupported query operator: " + operator)
        elif actual is MISSING:
            if expected is not None:
                return False
        elif actual != expected:
            return False
    return True


class FakeCursor(list):
    def sort(self, key, direction=None):
        fields = key if isinstance(key, list) else [(key, direction)]
        for field, order in reversed(fields):
            super().sort(key=lambda item: str(get_path(item, field, "")), reverse=order == -1)
        return self

    def limit(self, amount):
        return FakeCursor(self[:amount])


class FakeCollection:
    def __init__(self, documents=()):
        self.documents = copy.deepcopy(list(documents))
        self.writes = []
        self.fail_update = None

    def find(self, query=None, projection=None, **kwargs):
        found = [copy.deepcopy(doc) for doc in self.documents if matches(doc, query or {})]
        if projection:
            selected = []
            for doc in found:
                result = {"_id": doc["_id"]} if projection.get("_id", 1) and "_id" in doc else {}
                for path, include in projection.items():
                    value = get_path(doc, path)
                    if include and value is not MISSING:
                        set_path(result, path, value)
                selected.append(result)
            found = selected
        return FakeCursor(found)

    def find_one(self, query=None, projection=None, sort=None):
        found = self.find(query, projection)
        if sort:
            found.sort(sort)
        return found[0] if found else None

    def count_documents(self, query, **kwargs):
        return len(self.find(query))

    def update_one(self, query, update, upsert=False):
        if upsert:
            raise AssertionError("Refresh must not upsert source records")
        if self.fail_update and self.fail_update(query, update):
            raise RuntimeError("Simulated MongoDB failure")
        for doc in self.documents:
            if matches(doc, query):
                before = copy.deepcopy(doc)
                for path, value in update.get("$set", {}).items():
                    set_path(doc, path, value)
                for path in update.get("$unset", {}):
                    parent_path, _, leaf = path.rpartition(".")
                    parent = get_path(doc, parent_path) if parent_path else doc
                    if isinstance(parent, dict):
                        parent.pop(leaf, None)
                self.writes.append((copy.deepcopy(query), copy.deepcopy(update)))
                return SimpleNamespace(matched_count=1, modified_count=int(before != doc))
        return SimpleNamespace(matched_count=0, modified_count=0)


class FakeDatabase(dict):
    def __missing__(self, key):
        collection = self[key] = FakeCollection()
        return collection


def profile(*attributes, value=0.25):
    return [
        {"kdma": attribute, "parameters": [
            {"name": "intercept", "value": value},
            {"name": "attr_weight", "value": value + 0.5},
            {"name": "medical_weight", "value": value + 1.0},
        ]}
        for attribute in attributes
    ]


ATTRIBUTES = {"AF": "affiliation", "MF": "merit", "PS": "personal_safety", "SS": "search"}


def fixture_database(include_text=True):
    text = []
    if include_text:
        for short, attribute in ATTRIBUTES.items():
            pair = ("affiliation", "personal_safety") if short in ("AF", "PS") else ("merit", "search")
            sid = "original-afps" if short in ("AF", "PS") else "original-mfss"
            doc = {
                "_id": "text-" + short, "evalNumber": 15, "participantID": "101",
                "scenario_id": "Feb2026-" + short + "1-assess", "timeComplete": "2026-02-01",
                "combinedSessionId": sid, "kdmas": profile(*pair), "combinedKdmas": profile(*pair),
                "probes": [{"probe_id": "Feb2026-" + short + "-1", "choice": "A"}],
                "unrelated": {"keep": [1, 2, 3]},
            }
            if short == "MF":
                doc.update(individualSessionId="original-mf", individualKdmas=profile(attribute))
            text.append(doc)
    sims = []
    for terrain in ("desert", "urban"):
        sid = "original-" + terrain
        label = terrain.title()
        sims.append({
            "_id": "sim-" + terrain, "evalNumber": 15, "pid": "101", "openWorld": True,
            "env": "feb2026-" + terrain + "-openworld", "scenario_id": "Feb2026-OW_" + terrain,
            "data": {"alignment": {"sid": sid, "kdmas": profile("affiliation", "merit")}, "data": [
                {"probe_id": "Feb2026-" + short + "-1", "found_match": True, "response": "A"}
                for short in ("AF", "MF")
            ]},
            "actionAnalysis": {"MF Alignment_" + label: 0.2, "AF Alignment_" + label: 0.3, "unrelated": 27},
            "text_kdmas": {
                "Participant Text " + short + " " + parameter + " KDMA": -1.25
                for short in ATTRIBUTES for parameter in ("intercept", "attr_weight", "medical_weight")
            },
            "midpoint_values": {
                "text": {attribute: {"sid": "original-afps" if short in ("AF", "PS") else "original-mfss", "value": 0.2}
                         for short, attribute in ATTRIBUTES.items()},
                "open_world": {attribute: {"sid": sid, "value": 0.3} for attribute in ("affiliation", "merit")},
            },
            "midpoint_alignment_scores": {
                attribute: {"open_world_sid": sid, "text_sid": "original-afps" if attribute == "affiliation" else "original-mfss", "score": 0.4}
                for attribute in ("affiliation", "merit")
            },
            "unrelated": {"keep": [4, 5, 6]},
        })
    comparisons = [{"_id": "comparison-" + name, "evalNumber": 15, "pid": "101", "text_session_id": "original-" + name, "score": 0.6}
                   for name in ("afps", "mfss", "mf")]
    for evaluation in (18, 19):
        other = copy.deepcopy(sims[0])
        other.update(_id="other-sim-" + str(evaluation), evalNumber=evaluation)
        sims.append(other)
        if include_text:
            other_text = copy.deepcopy(text[0])
            other_text.update(_id="other-text-" + str(evaluation), evalNumber=evaluation)
            text.append(other_text)
        comparisons.append({"_id": "other-comparison-" + str(evaluation), "evalNumber": evaluation,
                            "pid": "101", "text_session_id": "original-afps", "score": 0.8})
    return FakeDatabase(humanSimulator=FakeCollection(sims), userScenarioResults=FakeCollection(text),
                        humanToADMComparison=FakeCollection(comparisons))


class FakeAdeptClient:
    def __init__(self):
        self.url = "http://adept.invalid/"
        self.sessions = {}
        self.populated = []
        self.checked = []
        self.invalid_profiles = False

    def check_scenarios(self, responses):
        self.checked.extend(copy.deepcopy(responses))

    def populate(self, responses, **kwargs):
        sid = "replacement-" + str(len(self.populated) + 1)
        attributes = set()
        for response in responses:
            for short, attribute in ATTRIBUTES.items():
                if "-" + short in response["scenario_id"] or "-" + short in response["probe_id"]:
                    attributes.add(attribute)
        values = [] if self.invalid_profiles else profile(*sorted(attributes), value=0.8)
        self.sessions[sid] = values
        self.populated.append((sid, copy.deepcopy(responses)))
        return sid, copy.deepcopy(values)

    def profile(self, sid, **kwargs):
        return copy.deepcopy(self.sessions.get(sid, []))


def without_progress(document):
    result = copy.deepcopy(document)
    result.pop("_rq8_refresh_1_8_2", None)
    return result


class FebruaryRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.refresh = importlib.import_module("scripts._1_8_2_refresh_feb2026_rq8_values")

    def setUp(self):
        self.db = fixture_database()
        self.client = FakeAdeptClient()
        self.before = {name: copy.deepcopy(collection.documents) for name, collection in self.db.items()}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.regular = self.stack.enter_context(patch.object(
            self.refresh.matcher, "compute_alignment_scores", side_effect=self.alignment_scores))
        self.midpoints = self.stack.enter_context(patch.object(
            self.refresh.matcher, "compute_midpoint_values", side_effect=self.midpoint_values))
        self.midpoint_alignment = self.stack.enter_context(patch.object(
            self.refresh.matcher, "compute_midpoint_alignment_scores", side_effect=self.midpoint_scores))

    @staticmethod
    def alignment_scores(metadata, human_session_id=None, text_session_ids=None, **kwargs):
        terrain = "Desert" if "desert" in metadata["scenario_id"] else "Urban"
        return {short + " Alignment_" + terrain: 0.75
                for attribute, short in (("affiliation", "AF"), ("merit", "MF"))
                if attribute in (text_session_ids or {})}

    @staticmethod
    def midpoint_values(metadata, human_session_id=None, text_session_ids=None, **kwargs):
        return {
            "text": {attribute: {"sid": sid, "value": 0.0}
                     for attribute, sid in (text_session_ids or {}).items()},
            "open_world": {attribute: {"sid": human_session_id, "value": 0.6}
                           for attribute in ("affiliation", "merit")},
        }

    @staticmethod
    def midpoint_scores(metadata, human_session_id=None, text_session_ids=None, **kwargs):
        return {attribute: {"open_world_sid": human_session_id, "text_sid": sid, "score": 0.8}
                for attribute, sid in (text_session_ids or {}).items()
                if attribute in ("affiliation", "merit")}

    def run_refresh(self, **kwargs):
        with redirect_stdout(io.StringIO()):
            return self.refresh.run(self.db, self.client, **kwargs)

    def assert_original_active_values(self):
        for name, documents in self.before.items():
            for original in documents:
                current = self.db[name].find_one({"_id": original["_id"]})
                self.assertEqual(without_progress(current), original)

    def test_dry_run_repopulates_nothing_and_writes_nothing(self):
        self.run_refresh(dry_run=True)
        self.assertFalse(self.client.populated)
        self.assertTrue(self.client.checked)
        for collection in self.db.values():
            self.assertFalse(collection.writes)
        self.assert_original_active_values()

    def test_refresh_preserves_originals_excluded_coefficients_and_other_evaluations(self):
        self.run_refresh()
        self.assertEqual(len(self.client.populated), 5)
        for original in self.before["humanSimulator"]:
            current = self.db["humanSimulator"].find_one({"_id": original["_id"]})
            if original["evalNumber"] != 15:
                self.assertEqual(current, original)
                continue
            self.assertEqual(current["text_kdmas"], original["text_kdmas"])
            self.assertEqual(current["unrelated"], original["unrelated"])
            self.assertEqual(current["data"]["data"], original["data"]["data"])
            self.assertEqual(get_path(current, "data.alignment.kdmas_old"), get_path(original, "data.alignment.kdmas"))
            self.assertEqual(get_path(current, "data.alignment.sid_old"), get_path(original, "data.alignment.sid"))
            self.assertNotEqual(get_path(current, "data.alignment.sid"), get_path(original, "data.alignment.sid"))
            self.assertEqual(current["midpoint_values"]["text"]["merit_old"], original["midpoint_values"]["text"]["merit"])
            self.assertEqual(current["midpoint_values"]["text"]["merit"]["value"], 0.0)
            self.assertEqual(current["midpoint_alignment_scores"]["merit_old"], original["midpoint_alignment_scores"]["merit"])
            terrain = "Desert" if "desert" in original["scenario_id"] else "Urban"
            self.assertEqual(current["actionAnalysis"]["MF Alignment_" + terrain + "_old"],
                             original["actionAnalysis"]["MF Alignment_" + terrain])
            self.assertEqual(current["actionAnalysis"]["unrelated"], 27)
        for original in self.before["userScenarioResults"]:
            current = self.db["userScenarioResults"].find_one({"_id": original["_id"]})
            if original["evalNumber"] != 15:
                self.assertEqual(current, original)
                continue
            for field in ("kdmas", "combinedKdmas", "individualKdmas"):
                self.assertEqual(get_path(current, field), get_path(original, field))
                self.assertNotIn(field + "_old", current)
            self.assertEqual(current["combinedSessionId_old"], original["combinedSessionId"])
            self.assertNotEqual(current["combinedSessionId"], original["combinedSessionId"])
        for original in self.before["humanToADMComparison"]:
            current = self.db["humanToADMComparison"].find_one({"_id": original["_id"]})
            self.assertEqual(current["score"], original["score"])
            if original["evalNumber"] == 15:
                self.assertEqual(current["text_session_id_old"], original["text_session_id"])
                self.assertNotEqual(current["text_session_id"], original["text_session_id"])
            else:
                self.assertEqual(current, original)

    def test_rerun_reuses_completed_sessions_and_never_changes_backups(self):
        self.run_refresh()
        after = {name: copy.deepcopy(collection.documents) for name, collection in self.db.items()}
        self.run_refresh()
        self.assertEqual(len(self.client.populated), 5)
        for name, documents in after.items():
            self.assertEqual(self.db[name].documents, documents)

    def test_existing_null_backup_is_not_replaced(self):
        self.db["humanSimulator"].documents[0]["actionAnalysis"]["MF Alignment_Desert_old"] = None
        self.run_refresh()
        current = self.db["humanSimulator"].find_one({"_id": "sim-desert"})
        self.assertIsNone(current["actionAnalysis"]["MF Alignment_Desert_old"])
        self.assertEqual(current["actionAnalysis"]["MF Alignment_Desert"], 0.75)

    def test_negative_regression_alignment_is_published_without_clamping(self):
        def negative_alignment(*args, **kwargs):
            return {field: -8.123456789 for field in self.alignment_scores(*args, **kwargs)}

        self.regular.side_effect = negative_alignment
        self.run_refresh()
        for terrain in ("desert", "urban"):
            current = self.db["humanSimulator"].find_one({"_id": "sim-" + terrain})
            self.assertEqual(current["actionAnalysis"]["MF Alignment_" + terrain.title()], -8.123456789)
            self.assertEqual(current["actionAnalysis"]["MF Alignment_" + terrain.title() + "_old"], 0.2)
            self.assertEqual(current["midpoint_alignment_scores"]["merit"]["score"], 0.8)

    def test_nonfinite_or_boolean_regression_alignment_does_not_publish(self):
        for score in (float("inf"), float("nan"), True):
            with self.subTest(score=score):
                self.db = fixture_database()
                self.client = FakeAdeptClient()

                def invalid_alignment(*args, **kwargs):
                    return {field: score for field in self.alignment_scores(*args, **kwargs)}

                self.regular.side_effect = invalid_alignment
                with self.assertRaises(self.refresh.RefreshError):
                    self.run_refresh()
                self.assert_original_active_values()

    def test_failed_request_does_not_publish_sessions_or_values(self):
        self.midpoints.side_effect = RuntimeError("ADEPT request failed")
        with self.assertRaises(self.refresh.RefreshError):
            self.run_refresh()
        self.assert_original_active_values()

    def test_empty_populated_profile_does_not_publish_sessions_or_values(self):
        self.client.invalid_profiles = True
        with self.assertRaises(self.refresh.RefreshError):
            self.run_refresh()
        self.assert_original_active_values()

    def test_invalid_midpoint_does_not_replace_valid_values(self):
        valid = self.midpoint_values

        def invalid(*args, **kwargs):
            values = valid(*args, **kwargs)
            values["open_world"]["merit"]["value"] = float("nan")
            return values

        self.midpoints.side_effect = invalid
        with self.assertRaises(self.refresh.RefreshError):
            self.run_refresh()
        self.assert_original_active_values()

    def test_missing_midpoint_response_does_not_erase_existing_measurement(self):
        valid = self.midpoint_values

        def incomplete(*args, **kwargs):
            values = valid(*args, **kwargs)
            values["open_world"].pop("merit")
            return values

        self.midpoints.side_effect = incomplete
        with self.assertRaises(self.refresh.RefreshError):
            self.run_refresh()
        self.assert_original_active_values()

    def test_midpoint_with_wrong_session_does_not_publish(self):
        valid = self.midpoint_values

        def wrong_session(*args, **kwargs):
            values = valid(*args, **kwargs)
            values["text"]["merit"]["sid"] = "unrelated-session"
            return values

        self.midpoints.side_effect = wrong_session
        with self.assertRaises(self.refresh.RefreshError):
            self.run_refresh()
        self.assert_original_active_values()

    def test_midpoint_alignment_with_wrong_text_session_does_not_publish(self):
        valid = self.midpoint_scores

        def wrong_session(*args, **kwargs):
            values = valid(*args, **kwargs)
            values["merit"]["text_sid"] = "unrelated-session"
            return values

        self.midpoint_alignment.side_effect = wrong_session
        with self.assertRaises(self.refresh.RefreshError):
            self.run_refresh()
        self.assert_original_active_values()

    def test_new_midpoint_fields_have_no_fabricated_old_values(self):
        self.db["humanSimulator"].documents[0].pop("midpoint_alignment_scores")
        self.run_refresh()
        current = self.db["humanSimulator"].find_one({"_id": "sim-desert"})
        self.assertEqual(set(current["midpoint_alignment_scores"]), {"affiliation", "merit"})

    def test_concurrent_change_is_not_overwritten(self):
        changed = {"done": False}

        def change_before_update(query, update):
            if (matches({"_id": "sim-desert"}, {"_id": query.get("_id")}) and "data.alignment.sid" in update.get("$set", {})
                    and not changed["done"]):
                self.db["humanSimulator"].documents[0]["actionAnalysis"]["MF Alignment_Desert"] = 0.99
                changed["done"] = True
            return False

        self.db["humanSimulator"].fail_update = change_before_update
        with self.assertRaises(self.refresh.RefreshError):
            self.run_refresh()
        current = self.db["humanSimulator"].find_one({"_id": "sim-desert"})
        self.assertEqual(current["actionAnalysis"]["MF Alignment_Desert"], 0.99)
        self.assertEqual(get_path(current, "data.alignment.sid"), "original-desert")

    def test_missing_text_refreshes_open_world_and_preserves_text_dependencies(self):
        self.db = fixture_database(include_text=False)
        original = self.db["humanSimulator"].find_one({"_id": "sim-desert"})
        self.run_refresh()
        self.assertEqual(len(self.client.populated), 2)
        current = self.db["humanSimulator"].find_one({"_id": "sim-desert"})
        self.assertNotEqual(get_path(current, "data.alignment.sid"), get_path(original, "data.alignment.sid"))
        self.assertEqual(current["midpoint_values"]["text"], original["midpoint_values"]["text"])
        self.assertEqual(current["midpoint_alignment_scores"], original["midpoint_alignment_scores"])
        self.assertEqual(current["actionAnalysis"], original["actionAnalysis"])
        self.assertEqual(current["text_kdmas"], original["text_kdmas"])

    def test_verify_only_never_populates_or_updates(self):
        self.run_refresh()
        population_count = len(self.client.populated)
        write_counts = {name: len(collection.writes) for name, collection in self.db.items()}
        self.run_refresh(verify_only=True)
        self.assertEqual(len(self.client.populated), population_count)
        self.assertEqual({name: len(collection.writes) for name, collection in self.db.items()}, write_counts)

    def test_verify_only_rejects_unfinished_refresh_without_writes(self):
        with self.assertRaises(self.refresh.RefreshError):
            self.run_refresh(verify_only=True)
        self.assertFalse(self.client.populated)
        self.assertTrue(all(not collection.writes for collection in self.db.values()))

    def test_completed_marker_does_not_hide_changed_metric(self):
        self.run_refresh()
        self.db["humanSimulator"].documents[0]["actionAnalysis"]["MF Alignment_Desert"] = 0.99
        with self.assertRaises(self.refresh.RefreshError):
            self.run_refresh()
        current = self.db["humanSimulator"].find_one({"_id": "sim-desert"})
        self.assertEqual(current["actionAnalysis"]["MF Alignment_Desert"], 0.99)
        self.assertEqual(current["actionAnalysis"]["MF Alignment_Desert_old"], 0.2)

    def test_original_null_metric_is_preserved_as_null_backup(self):
        self.db["humanSimulator"].documents[0]["actionAnalysis"]["MF Alignment_Desert"] = None
        self.run_refresh()
        current = self.db["humanSimulator"].find_one({"_id": "sim-desert"})
        self.assertIsNone(current["actionAnalysis"]["MF Alignment_Desert_old"])
        self.assertEqual(current["actionAnalysis"]["MF Alignment_Desert"], 0.75)

    def test_partial_pair_publication_resumes_without_replaying_completed_sessions(self):
        failure = {"remaining": 1}

        def fail_once(query, update):
            if (matches({"_id": "text-PS"}, {"_id": query.get("_id")}) and "combinedSessionId" in update.get("$set", {})
                    and failure["remaining"]):
                failure["remaining"] -= 1
                return True
            return False

        self.db["userScenarioResults"].fail_update = fail_once
        with self.assertRaises(self.refresh.RefreshError):
            self.run_refresh()
        population_count = len(self.client.populated)
        self.run_refresh()
        self.assertEqual(len(self.client.populated), population_count)
        af = self.db["userScenarioResults"].find_one({"_id": "text-AF"})
        ps = self.db["userScenarioResults"].find_one({"_id": "text-PS"})
        self.assertEqual(af["combinedSessionId"], ps["combinedSessionId"])
        self.assertEqual(af["combinedSessionId_old"], "original-afps")
        self.assertEqual(ps["combinedSessionId_old"], "original-afps")

    def test_lost_staged_sessions_prevent_resumed_publication(self):
        with patch.object(self.refresh, "publish_document", side_effect=RuntimeError("Interrupted before publication")):
            with self.assertRaises(self.refresh.RefreshError):
                self.run_refresh()
        self.client.sessions.clear()
        with self.assertRaises(self.refresh.RefreshError):
            self.run_refresh()
        self.assert_original_active_values()


if __name__ == "__main__":
    unittest.main()
