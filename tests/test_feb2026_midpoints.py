"""Offline checks for migration 179 and February midpoint backfilling."""

from copy import deepcopy
import io
import os
from pathlib import Path
import subprocess
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

with patch.dict(os.environ, {
    "MONGO_URL": "mongodb://unit-test.invalid",
    "ADEPT_URL": "https://adept.invalid/",
    "LOG_LEVEL": "3",
}):
    import oct2026_probe_matcher as matcher
    import openworld_repop
    import text_repop
    from scripts import _1_7_9_feb2026_repop_and_midpoint_upload as migration


def field(document, path):
    value = document
    for key in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def matches(document, query):
    return all(
        field(document, key) in expected["$in"]
        if isinstance(expected, dict) and "$in" in expected
        else field(document, key) == expected
        for key, expected in query.items()
    )


class Collection:
    def __init__(self, documents=()):
        self.documents = deepcopy(list(documents))
        self.writes = []

    def find(self, query):
        return deepcopy([doc for doc in self.documents if matches(doc, query)])

    def find_one(self, query, sort=None):
        documents = self.find(query)
        if sort:
            key, direction = sort[0]
            documents.sort(key=lambda doc: doc.get(key, 0), reverse=direction < 0)
        return documents[0] if documents else None

    def update_one(self, query, updates, upsert=False):
        assert not upsert
        for document in self.documents:
            if not matches(document, query):
                continue
            original = deepcopy(document)
            for operation, changes in updates.items():
                for path, value in changes.items():
                    keys = path.split(".")
                    parent = document
                    for key in keys[:-1]:
                        parent = parent.setdefault(key, {})
                    if operation == "$set":
                        parent[keys[-1]] = deepcopy(value)
                    elif operation == "$unset":
                        parent.pop(keys[-1], None)
                    else:
                        raise AssertionError(operation)
            self.writes.append((query, updates))
            return SimpleNamespace(matched_count=1, modified_count=int(document != original))
        return SimpleNamespace(matched_count=0, modified_count=0)

    def update_many(self, query, updates):
        for document in self.find(query):
            self.update_one({"_id": document["_id"]}, updates)


def text_results():
    documents = []
    for short_name in ("PS", "AF", "MF", "SS"):
        document = {
            "_id": short_name, "evalNumber": 15, "participantID": "15001",
            "scenario_id": f"Feb2026-{short_name}2-assess",
            "combinedSessionId": "old-ps-af" if short_name in ("PS", "AF") else "old-mf-ss",
            "Scene 1": {"questions": {"probe Scene 1": {
                "response": "Patient A.",
                "question_mapping": {"Patient A": {
                    "probe_id": f"Feb2026-{short_name}-assess.Probe 1", "choice": "choice-a",
                }},
            }}},
        }
        if short_name == "MF":
            document["individualSessionId"] = "old-mf"
        documents.append(document)
    return documents


def analysis(eval_number=15):
    return {
        "_id": f"{eval_number}-ow", "evalNumber": eval_number, "pid": "15001",
        "openWorld": True, "scenario_id": "Feb2026-OW_desert2",
        "actionAnalysis": {"existing": "preserved"},
        "data": {
            "alignment": {"sid": "old-ow", "kdmas": [{"historical": True}]},
            "data": [
                {"found_match": True, "probe_id": f"Feb2026-{name}-OW_desert.Probe 1", "response": "choice-a"}
                for name in ("AF", "MF")
            ] + [{"found_match": False, "probe_id": "unmatched", "response": ""}],
        },
    }


class QuietTestCase(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)


class MigrationTests(QuietTestCase):
    def test_steps_and_dry_run_propagation(self):
        for dry_run in (False, True):
            with self.subTest(dry_run=dry_run), patch.object(migration, "config", return_value="configured"), \
                    patch.object(migration.subprocess, "run") as run, patch.object(migration, "upload_midpoints") as upload:
                db = object()
                result = migration.main(db, dry_run=dry_run)
                self.assertEqual(run.call_count, 2)
                upload.assert_called_once_with(db, dry_run=dry_run)
                self.assertIs(result, upload.return_value)
                commands = [call.args[0] for call in run.call_args_list]
                self.assertEqual([Path(command[1]).name for command in commands], [
                    "text_repop.py", "openworld_repop.py",
                ])
                self.assertEqual(commands[0][2:6], ["--eval-number", "15", "--session-field", "combinedSessionId"])
                self.assertEqual(commands[1][2:4], ["--eval-number", "15"])
                for call in run.call_args_list:
                    self.assertEqual("--dry-run" in call.args[0], dry_run)
                    self.assertTrue(call.kwargs["check"])
                    self.assertEqual(call.kwargs["env"]["PYTHONUNBUFFERED"], "1")
                    self.assertEqual(Path(call.kwargs["cwd"]), Path(migration.__file__).resolve().parents[1])

    def test_preflight_stops_before_any_child_process(self):
        with patch.object(migration.subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "Mongo database"):
                migration.main(None)
            with patch.object(migration, "config", return_value=""), self.assertRaisesRegex(RuntimeError, "MONGO_URL"):
                migration.main(object())
            with patch.object(migration, "config", return_value="configured"), \
                    patch.object(migration.Path, "is_file", return_value=False), self.assertRaises(FileNotFoundError):
                migration.main(object())
            run.assert_not_called()

    def test_failure_stops_later_steps(self):
        for failure_index in (0, 1):
            with self.subTest(failure_index=failure_index), patch.object(migration, "config", return_value="configured"), \
                    patch.object(migration.subprocess, "run", side_effect=[None] * failure_index + [
                        subprocess.CalledProcessError(1, "repop"),
                    ]) as run, patch.object(migration, "upload_midpoints") as upload, self.assertRaises(subprocess.CalledProcessError):
                migration.main(object())
            self.assertEqual(run.call_count, failure_index + 1)
            upload.assert_not_called()

    def test_upload_runs_after_both_repops_and_propagates_failure(self):
        order = []

        def run(command, **kwargs):
            order.append(Path(command[1]).name)

        def upload(db, dry_run=False):
            order.append("upload")
            raise RuntimeError("midpoint upload failed")

        with patch.object(migration, "config", return_value="configured"), \
                patch.object(migration.subprocess, "run", side_effect=run), \
                patch.object(migration, "upload_midpoints", side_effect=upload), \
                self.assertRaisesRegex(RuntimeError, "midpoint upload failed"):
            migration.main(object())
        self.assertEqual(order, ["text_repop.py", "openworld_repop.py", "upload"])

    def test_deployment_discovers_version_179(self):
        from deployment_script import ScriptManager
        manager = ScriptManager.__new__(ScriptManager)
        manager.scripts_dir = "scripts"
        with patch("deployment_script.os.listdir", return_value=[Path(migration.__file__).name]):
            updates = manager.discover_update_scripts()
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0][0], "1.7.9")
        self.assertIs(updates[0][2], migration.main)

    def test_redo_loads_179_and_passes_dry_run(self):
        import redo
        with patch.object(redo, "MongoClient") as client, patch.object(redo, "config", return_value="configured"), \
                patch("decouple.config", return_value="configured"), patch.object(migration.subprocess, "run") as run:
            redo.run_script("179", ["true"])
        self.assertEqual(run.call_count, 2)
        self.assertTrue(all("--dry-run" in call.args[0] for call in run.call_args_list))
        client.return_value.__getitem__.return_value.__getitem__.return_value.find.assert_called_once_with(
            {"evalNumber": 15, "openWorld": True},
        )
        client.return_value.close.assert_called_once()


class FebruaryBackfillTests(QuietTestCase):
    def setUp(self):
        super().setUp()
        self.db = {
            "userScenarioResults": Collection(text_results()),
            "humanSimulator": Collection([analysis(), analysis(18), analysis(19)]),
            "admTargetRuns": Collection([{
                "_id": "observe", "evalNumber": 15, "scenario": "Feb2026-MF3-observe",
                "results": {"ta1_session_id": "adm-sid"}, "history": [],
            }]),
            "admMedics": Collection([{"_id": "medic", "evalNumber": 15, "admSessionId": "adm-sid"}]),
            "humanToADMComparison": Collection([
                {"_id": "feb-comparison", "evalNumber": 15, "text_session_id": "old-ps-af"},
                {"_id": "canada-comparison", "evalNumber": 18, "text_session_id": "old-ps-af"},
            ]),
        }
        self.logger_patch = patch.object(matcher, "logger", Mock())
        self.logger_patch.start()
        self.addCleanup(self.logger_patch.stop)
        self.url_patch = patch.object(matcher, "ADEPT_URL", "https://adept.invalid/")
        self.url_patch.start()
        self.addCleanup(self.url_patch.stop)

    def recreate_text(self):
        client = Mock()
        client.profile.return_value = []

        def populate(responses, enable_subpop):
            attributes = set().union(*(text_repop.scenario_attributes(response["scenario_id"]) for response in responses))
            self.assertIn(attributes, ({"affiliation", "personal_safety"}, {"merit", "search"}))
            self.assertEqual(len(responses), 2)
            self.assertTrue(all(response["choice"] == "choice-a" for response in responses))
            session_id = "ps-af" if "affiliation" in attributes else "mf-ss"
            return session_id, [{"kdma": name, "value": 0.5} for name in attributes]

        client.populate.side_effect = populate
        counts = text_repop.run(self.db, client, eval_number=15, selected_fields=["combinedSessionId"])
        self.assertEqual(counts.get("recreated"), 2)
        self.assertEqual(counts.get("failed", 0), 0)
        self.assertEqual(client.populate.call_count, 2)
        return client

    def repair_open_world(self, dry_run=False, usable=True):
        client = Mock()
        profile = [{"kdma": name, "value": 0.5} for name in ("affiliation", "merit")]
        client.profile.return_value = []
        client.populate.return_value = ("new-ow", profile if usable else [])
        counts = openworld_repop.run(self.db, client, eval_number=15, dry_run=dry_run)
        return client, counts

    def midpoint_response(self, url, params, timeout):
        if url.endswith("computed_kdma_profile_midpoint"):
            profiles = {
                "ps-af": {"personal_safety": 0.2, "affiliation": 0.4},
                "mf-ss": {"merit": 0.0, "search": 0.7},
                "new-ow": {"affiliation": 0.5, "merit": 1.0},
            }
            payload = [{"kdma": name, "value": value} for name, value in profiles[params["session_id"]].items()]
        elif url.endswith("alignment/compare_sessions_midpoint"):
            self.assertEqual(params["session_id_1"], "new-ow")
            expected_text = "ps-af" if params["kdma_filter"] == "affiliation" else "mf-ss"
            self.assertEqual(params["session_id_2"], expected_text)
            payload = {"score": 0.8 if expected_text == "ps-af" else 0.0}
        else:
            raise AssertionError(url)
        response = Mock()
        response.json.return_value = payload
        return response

    def test_repop_then_backfill_preserves_groups_and_other_evaluations(self):
        original = deepcopy(self.db["humanSimulator"].documents)
        original_adms = deepcopy(self.db["admTargetRuns"].documents)
        original_medics = deepcopy(self.db["admMedics"].documents)
        self.recreate_text()
        client, counts = self.repair_open_world()
        self.assertEqual(counts["recreated"], 1)
        responses = client.populate.call_args.args[0]
        self.assertEqual(len(responses), 2)
        self.assertTrue(all(response["scenario_id"] == "Feb2026-OW_desert2" for response in responses))
        with patch.object(matcher.requests, "get", side_effect=self.midpoint_response) as get:
            counts = migration.upload_midpoints(self.db)
            self.assertEqual(counts["updated"], 1)
            self.assertEqual(get.call_count, 5)  # Three distinct profiles, two comparisons.
            get.reset_mock()
            self.assertEqual(migration.upload_midpoints(self.db)["unchanged"], 1)
            get.assert_not_called()
        documents = self.db["humanSimulator"].documents
        values = documents[0]["midpoint_values"]
        self.assertEqual(set(values["text"]), set(matcher.KDMA_MAP))
        self.assertEqual(values["text"]["affiliation"]["sid"], "ps-af")
        self.assertEqual(values["text"]["personal_safety"]["sid"], "ps-af")
        self.assertEqual(values["text"]["merit"], {"sid": "mf-ss", "value": 0.0})
        self.assertEqual(values["text"]["search"]["sid"], "mf-ss")
        self.assertEqual(documents[0]["midpoint_alignment_scores"]["merit"]["score"], 0.0)
        self.assertEqual(documents[0]["data"]["data"], original[0]["data"]["data"])
        self.assertEqual(documents[0]["data"]["alignment"]["kdmas"], original[0]["data"]["alignment"]["kdmas"])
        self.assertEqual(documents[0]["actionAnalysis"], original[0]["actionAnalysis"])
        self.assertEqual(documents[1:], original[1:])
        self.assertEqual(self.db["humanToADMComparison"].documents, [
            {"_id": "feb-comparison", "evalNumber": 15, "text_session_id": "ps-af"},
            {"_id": "canada-comparison", "evalNumber": 18, "text_session_id": "old-ps-af"},
        ])
        self.assertEqual(self.db["userScenarioResults"].find_one({"_id": "MF"})["individualSessionId"], "old-mf")
        self.assertEqual(self.db["admTargetRuns"].documents, original_adms)
        self.assertEqual(self.db["admMedics"].documents, original_medics)
        self.assertEqual(self.db["admTargetRuns"].writes, [])
        self.assertEqual(self.db["admMedics"].writes, [])

    def test_text_dry_run_never_populates_or_updates(self):
        before = {name: deepcopy(collection.documents) for name, collection in self.db.items()}
        client = Mock()
        client.profile.return_value = []
        counts = text_repop.run(self.db, client, eval_number=15, selected_fields=["combinedSessionId"], dry_run=True)
        self.assertEqual(counts.get("would_recreate"), 2)
        client.populate.assert_not_called()
        self.assertEqual({name: collection.documents for name, collection in self.db.items()}, before)

    def test_healthy_combined_sessions_are_reused_without_individual_repair(self):
        client = Mock()
        profiles = {
            "old-ps-af": [{"kdma": name, "value": 0.5} for name in ("affiliation", "personal_safety")],
            "old-mf-ss": [{"kdma": name, "value": 0.5} for name in ("merit", "search")],
        }
        client.profile.side_effect = lambda session_id, _: profiles[session_id]
        counts = text_repop.run(self.db, client, eval_number=15, selected_fields=["combinedSessionId"])
        self.assertEqual(counts.get("reused"), 2)
        client.populate.assert_not_called()
        self.assertEqual(self.db["userScenarioResults"].find_one({"_id": "MF"})["individualSessionId"], "old-mf")

    def test_open_world_dry_run_and_invalid_replacement_keep_old_id(self):
        for dry_run, usable in ((True, True), (False, False)):
            with self.subTest(dry_run=dry_run):
                client, counts = self.repair_open_world(dry_run=dry_run, usable=usable)
                self.assertEqual(counts["would_recreate" if dry_run else "failed"], 1)
                if dry_run:
                    client.populate.assert_not_called()
                self.assertEqual(self.db["humanSimulator"].documents[0]["data"]["alignment"]["sid"], "old-ow")
                self.assertEqual(self.db["humanSimulator"].writes, [])

    def test_midpoint_dry_run_computes_without_writing(self):
        self.recreate_text()
        self.repair_open_world()
        collection = self.db["humanSimulator"]
        before = deepcopy(collection.documents)
        with patch.object(matcher.requests, "get", side_effect=self.midpoint_response):
            counts = migration.upload_midpoints(self.db, dry_run=True)
        self.assertEqual(counts["planned"], 1)
        self.assertEqual(counts["updated"], 0)
        self.assertEqual(collection.documents, before)

    def test_missing_text_saves_open_world_results_and_reruns_without_failure(self):
        self.repair_open_world()
        self.db["userScenarioResults"] = Collection()
        with patch.object(matcher.requests, "get", side_effect=self.midpoint_response) as get:
            counts = migration.upload_midpoints(self.db)
            self.assertEqual(counts["updated"], 1)
            self.assertEqual(counts["incomplete"], 1)
            self.assertEqual(counts["failed"], 0)
            self.assertEqual(get.call_count, 1)
            get.reset_mock()
            counts = migration.upload_midpoints(self.db)
            self.assertEqual(counts["unchanged"], 1)
            self.assertEqual(counts["failed"], 0)
            get.assert_not_called()
        document = self.db["humanSimulator"].documents[0]
        self.assertEqual(document["midpoint_values"]["text"], {})
        self.assertEqual(set(document["midpoint_values"]["open_world"]), {"affiliation", "merit"})
        self.assertNotIn("midpoint_alignment_scores", document)

    def test_empty_open_world_midpoints_and_nan_scores_still_save_text_values(self):
        self.recreate_text()
        self.repair_open_world()

        def unavailable_open_world(url, params, timeout):
            if params.get("session_id") == "new-ow":
                payload = []
            elif "kdma_filter" in params:
                payload = {"score": float("nan")}
            else:
                return self.midpoint_response(url, params, timeout)
            response = Mock()
            response.json.return_value = payload
            return response

        with patch.object(matcher.requests, "get", side_effect=unavailable_open_world):
            counts = migration.upload_midpoints(self.db)
        self.assertEqual(counts["updated"], 1)
        self.assertEqual(counts["incomplete"], 1)
        self.assertEqual(counts["failed"], 0)
        document = self.db["humanSimulator"].documents[0]
        self.assertEqual(set(document["midpoint_values"]["text"]), set(matcher.KDMA_MAP))
        self.assertEqual(document["midpoint_values"]["open_world"], {})
        self.assertNotIn("midpoint_alignment_scores", document)

    def test_incomplete_dry_run_reports_gaps_without_writing(self):
        self.repair_open_world()
        self.db["userScenarioResults"] = Collection()
        collection = self.db["humanSimulator"]
        before = deepcopy(collection.documents)
        with patch.object(matcher.requests, "get", side_effect=self.midpoint_response):
            counts = migration.upload_midpoints(self.db, dry_run=True)
        self.assertEqual(counts["planned"], 1)
        self.assertEqual(counts["incomplete"], 1)
        self.assertEqual(counts["failed"], 0)
        self.assertEqual(counts["updated"], 0)
        self.assertEqual(collection.documents, before)

    def test_service_failure_does_not_publish_midpoint_results(self):
        self.recreate_text()
        self.repair_open_world()
        with patch.object(matcher.requests, "get", side_effect=RuntimeError("service unavailable")), \
                self.assertRaisesRegex(RuntimeError, "1 document"):
            migration.upload_midpoints(self.db)
        self.assertNotIn("midpoint_values", self.db["humanSimulator"].documents[0])


class PrefixTests(unittest.TestCase):
    def test_canada_uk_combined_sessions_still_group_all_four_assessments(self):
        for eval_number in (18, 19):
            documents = text_results()
            for document in documents:
                document["evalNumber"] = eval_number
                document["combinedSessionId"] = "all-four"
                document["scenario_id"] = f"June2026-{document['_id']}-assess"
            groups = text_repop.build_groups(documents, selected_fields=["combinedSessionId"])
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0].expected_kdmas, set(matcher.KDMA_MAP))

    def test_february_numbered_sets_are_selected_without_june_or_trinary(self):
        self.assertEqual(matcher.text_scenario_ids_for_alignment({"evalNumber": 15}, "AF"), [
            "Feb2026-AF1-assess", "Feb2026_AF1_assess", "Feb2026-AF2-assess", "Feb2026_AF2_assess",
        ])
        text = Collection(text_results() + [{
            "_id": "wrong-eval", "evalNumber": 18, "participantID": "15001",
            "scenario_id": "Feb2026-AF2-assess", "combinedSessionId": "wrong", "timeComplete": 999,
        }, {
            "_id": "trinary", "evalNumber": 15, "participantID": "15001",
            "scenario_id": "Feb2026-AF2-assess-trinary", "combinedSessionId": "wrong", "timeComplete": 999,
        }])
        self.assertEqual(matcher.find_text_session_for_alignment(
            {"evalNumber": 15, "pid": "15001"}, "AF", collection=text, strict=True,
        ), "old-ps-af")

    def test_canada_uk_and_explicit_prefixes_keep_existing_behavior(self):
        for eval_number in (18, 19):
            self.assertEqual(matcher.get_eval_prefix_candidates({"evalNumber": eval_number}), ["June2026", "Jun2026"])
        with patch.object(matcher, "TEXT_SCENARIO_PREFIXES", ("Custom",)):
            self.assertEqual(matcher.get_eval_prefix_candidates({"evalNumber": 18}), ["Custom"])


if __name__ == "__main__":
    unittest.main()
