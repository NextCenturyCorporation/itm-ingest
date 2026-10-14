"""Regression checks for February scenarios and recorded eval 18 sessions."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import oct2026_probe_matcher as matcher


REPO_ROOT = Path(__file__).resolve().parents[1]
URBAN_RUN = "0549d10f-c844-49df-a7cc-e78d3b5ad3f8_202609114"


def input_path(run):
    return REPO_ROOT / "ph2_sim_files" / "oct2026" / run / f"{run}.json"


class OctoberProbeMatcherTests(unittest.TestCase):
    def setUp(self):
        self.logger_patch = patch.object(matcher, "logger")
        self.logger_patch.start()
        self.addCleanup(self.logger_patch.stop)
        self.runtime_patch = patch.multiple(
            matcher,
            EVAL_NUM=18,
            EVAL_NAME="October 2026 Evaluation",
            TEXT_SCENARIO_PREFIXES=("June2026", "Jun2026"),
            CALC_KDMAS=False,
            VERBOSE=False,
            SEND_TO_MONGO=False,
        )
        self.runtime_patch.start()
        self.addCleanup(self.runtime_patch.stop)

    def urban_input(self):
        return json.loads(input_path(URBAN_RUN).read_text(encoding="utf-8"))

    def test_old_sim_metadata_uses_february_scenario_and_selected_eval(self):
        source = self.urban_input()
        self.assertEqual(source["sessionMetadata"]["evalNumber"], 15)

        metadata = matcher.extract_run_metadata(source, URBAN_RUN)

        self.assertEqual(metadata["env"], "oct2026-urban-openworld")
        self.assertEqual(metadata["scenario_id"], "Feb2026-OW_urban")
        self.assertEqual(metadata["evalNumber"], 18)
        self.assertEqual(metadata["evalName"], "October 2026 Evaluation")
        self.assertEqual(source["sessionMetadata"]["evalNumber"], 15)
        with patch.object(matcher, "EVAL_NUM", 21):
            self.assertEqual(matcher.extract_run_metadata(source, URBAN_RUN)["evalNumber"], 21)

    def test_yaml_lookup_works_outside_repo_and_with_legacy_environment(self):
        working_dir = os.getcwd()
        with tempfile.TemporaryDirectory() as other_dir:
            try:
                os.chdir(other_dir)
                for terrain in ("urban", "desert"):
                    scenario = matcher.load_openworld_yaml_for_env(f"feb2026-{terrain}-openworld")
                    self.assertEqual(scenario["id"], f"Feb2026-OW_{terrain}")
                    for variant in (2, 3):
                        scenario = matcher.load_openworld_yaml_for_env(f"oct2026-{terrain}-openworld{variant}")
                        self.assertEqual(scenario["id"], f"Feb2026-OW_{terrain}{variant}")
            finally:
                os.chdir(working_dir)

    def test_tutorial_does_not_attempt_analysis_alignment_or_upload(self):
        with (
            patch.object(matcher, "load_csv_rows") as load_csv,
            patch.object(matcher, "extract_text_kdmas") as text,
            patch.object(matcher, "compute_openworld_match_data") as matching,
            patch.object(matcher, "compute_alignment_scores") as alignment,
            patch.object(matcher, "save_to_mongo") as upload,
            tempfile.TemporaryDirectory() as input_dir,
            tempfile.TemporaryDirectory() as output_dir,
        ):
            tutorial = Path(input_dir) / "tutorial_202609141.json"
            tutorial.write_text(json.dumps({"configData": {
                "scene": "sim-urban",
                "narrative": {"narrativeDescription": "TCCC Tutorial Narrative"},
                "scenarioData": {"name": "Urban"},
            }}), encoding="utf-8")
            self.assertFalse(matcher.process_file(str(tutorial), output_dir))
            for operation in (load_csv, text, matching, alignment, upload):
                operation.assert_not_called()
            self.assertEqual(list(Path(output_dir).iterdir()), [])

    def test_missing_eval18_text_has_no_cross_evaluation_fallback(self):
        collection = MagicMock()
        collection.find_one.return_value = None
        collection.find.return_value = []
        metadata = matcher.extract_run_metadata(self.urban_input(), URBAN_RUN)
        with patch.object(matcher, "text_scenario_collection", collection):
            self.assertIsNone(matcher.find_text_session_for_alignment(metadata, "MF"))
            self.assertTrue(all(value == "" for value in matcher.extract_text_kdmas(metadata).values()))
        collection.find_one.assert_called_once()
        collection.find.assert_called_once()
        for operation in (collection.find_one, collection.find):
            query = operation.call_args.args[0]
            self.assertEqual(query["evalNumber"], 18)
            self.assertIn("202609114", query["participantID"]["$in"])
            self.assertIn(202609114, query["participantID"]["$in"])
            self.assertTrue(all("June2026" in sid or "Jun2026" in sid for sid in query["scenario_id"]["$in"]))
            self.assertFalse(any("trinary" in sid for sid in query["scenario_id"]["$in"]))

    def test_february_assessment_prefix_uses_numbered_sets(self):
        with patch.object(matcher, "TEXT_SCENARIO_PREFIXES", ("Feb2026",)):
            ids = matcher._binary_text_scenario_ids({"evalNumber": 18})
            for attribute in ("AF", "MF", "PS", "SS"):
                self.assertIn(f"Feb2026-{attribute}1-assess", ids)
                self.assertIn(f"Feb2026-{attribute}2-assess", ids)
                self.assertNotIn(f"Feb2026-{attribute}-assess", ids)
            self.assertFalse(any("June" in sid or "trinary" in sid for sid in ids))

    def test_real_run_submits_february_probes_and_compares_recorded_text_session(self):
        source = self.urban_input()
        metadata = matcher.extract_run_metadata(source, URBAN_RUN)
        collection = MagicMock()
        def text_lookup(query, **kwargs):
            self.assertEqual(query["evalNumber"], 18)
            ids = query["scenario_id"]["$in"]
            attribute = "MF" if "June2026-MF-assess" in ids else "AF"
            return {"scenario_id": f"June2026-{attribute}-assess", "combinedSessionId": "recorded-text-session"}
        collection.find_one.side_effect = text_lookup

        new_session = MagicMock(text='"new-openworld-session"')
        profile = MagicMock()
        profile.json.return_value = [{"kdma": "merit", "value": 0.6}]
        mf_score = MagicMock()
        mf_score.json.return_value = {"score": 0.8}
        af_score = MagicMock()
        af_score.json.return_value = {"score": 0.7}

        with (
            patch.object(matcher, "CALC_KDMAS", True),
            patch.object(matcher, "ADEPT_URL", "https://adept.example/"),
            patch.object(matcher, "text_scenario_collection", collection),
            patch.object(matcher.requests, "post", return_value=new_session) as post,
            patch.object(matcher.requests, "get", side_effect=[profile, mf_score, af_score]) as get,
        ):
            result, session_id = matcher.compute_openworld_match_data(source, metadata)
            scores = matcher.compute_alignment_scores(metadata, session_id)

        self.assertEqual(session_id, "new-openworld-session")
        self.assertEqual(len(result["data"]), 10)
        self.assertTrue(all(row["found_match"] for row in result["data"]))
        self.assertEqual(post.call_count, 11)  # Session creation plus ten responses.
        for request in post.call_args_list[1:]:
            payload = request.kwargs["json"]
            self.assertEqual(payload["session_id"], session_id)
            self.assertEqual(payload["response"]["scenario_id"], "Feb2026-OW_urban")
            self.assertTrue(payload["response"]["probe_id"].startswith("Feb2026-"))
        self.assertEqual(scores, {"MF Alignment_Urban": 0.8, "AF Alignment_Urban": 0.7})
        self.assertEqual([request.kwargs["params"]["kdma_filter"] for request in get.call_args_list[1:]], ["merit", "affiliation"])
        for request in get.call_args_list[1:]:
            self.assertEqual(request.kwargs["params"]["session_id_2"], "recorded-text-session")


if __name__ == "__main__":
    unittest.main()
