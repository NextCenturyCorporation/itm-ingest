import copy
import unittest
from unittest.mock import Mock, patch

import oct2026_probe_matcher as matcher


def response(payload):
    result = Mock()
    result.json.return_value = payload
    return result


class RefreshHelperTests(unittest.TestCase):
    def setUp(self):
        self.http = Mock()
        self.metadata = {"pid": "101", "evalNumber": 15, "env": "feb2026-desert-openworld"}
        self.patches = [
            patch.object(matcher, "requests", self.http),
            patch.object(matcher, "ADEPT_URL", "http://adept/"),
            patch.object(matcher, "logger", Mock()),
            patch.object(matcher, "CALC_KDMAS", False),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_strict_regular_alignment_uses_staged_session_without_global_changes(self):
        self.http.get.return_value = response({"score": 0})
        original_metadata = copy.deepcopy(self.metadata)
        with patch.object(matcher, "find_text_session_for_alignment") as lookup:
            result = matcher.get_alignment_compare_score(
                "new-open-world", self.metadata, "MF", text_session_id="new-text", strict=True,
            )
        self.assertEqual(result, 0)
        lookup.assert_not_called()
        self.assertFalse(matcher.CALC_KDMAS)
        self.assertEqual(self.metadata, original_metadata)
        self.assertEqual(self.http.get.call_args.kwargs["params"], {
            "session_id_1": "new-open-world", "session_id_2": "new-text", "kdma_filter": "merit",
        })

    def test_regular_defaults_keep_disabled_calculation_behavior(self):
        result = matcher.compute_alignment_scores(self.metadata, "old-open-world")
        self.assertEqual(result, {"MF Alignment_Desert": None, "AF Alignment_Desert": None})
        self.http.get.assert_not_called()

    def test_regular_defaults_keep_database_selection(self):
        self.http.get.return_value = response({"score": 0.75})
        with patch.object(matcher, "CALC_KDMAS", True), patch.object(
            matcher, "find_text_session_for_alignment", return_value="stored-text",
        ) as lookup:
            self.assertEqual(matcher.get_alignment_compare_score("stored-ow", self.metadata, "AF"), 0.75)
        lookup.assert_called_once_with(self.metadata, "AF", strict=False)
        self.assertEqual(self.http.get.call_args.kwargs["params"]["session_id_2"], "stored-text")

    def test_strict_regular_alignment_rejects_invalid_results(self):
        for value in (None, True, float("inf"), float("nan"), "0.5"):
            with self.subTest(value=value):
                self.http.get.return_value = response({"score": value})
                with self.assertRaises(ValueError):
                    matcher.get_alignment_compare_score("ow", self.metadata, "AF", "text", strict=True)
        self.http.get.return_value = response([])
        with self.assertRaises(ValueError):
            matcher.get_alignment_compare_score("ow", self.metadata, "AF", "text", strict=True)

    def test_strict_regular_alignment_accepts_finite_regression_distances(self):
        for score in (-2.0969988926, -0.01, 1.01):
            with self.subTest(score=score):
                self.http.get.return_value = response({"score": score})
                self.assertEqual(matcher.get_alignment_compare_score(
                    "ow", self.metadata, "AF", "text", strict=True,
                ), score)

    def test_strict_regular_alignment_propagates_request_failure(self):
        self.http.get.side_effect = RuntimeError("service unavailable")
        with self.assertRaisesRegex(RuntimeError, "service unavailable"):
            matcher.get_alignment_compare_score("ow", self.metadata, "AF", "text", strict=True)
        with patch.object(matcher, "CALC_KDMAS", True):
            self.assertIsNone(matcher.get_alignment_compare_score("ow", self.metadata, "AF", "text"))

    def test_explicit_empty_text_mapping_never_looks_up_a_text_session(self):
        self.http.get.return_value = response([
            {"kdma": "affiliation", "value": 0.25}, {"kdma": "merit", "value": 0.75},
        ])
        with patch.object(matcher, "find_text_session_for_alignment") as lookup:
            self.assertEqual(matcher.compute_alignment_scores(
                self.metadata, "ow", text_session_ids={}, strict=True,
            ), {})
            self.assertEqual(matcher.compute_midpoint_alignment_scores(
                self.metadata, "ow", text_session_ids={}, strict=True,
            ), {})
            result = matcher.compute_midpoint_values(
                self.metadata, "ow", text_session_ids={}, strict=True,
            )
        lookup.assert_not_called()
        self.assertEqual(result["text"], {})
        self.assertEqual(set(result["open_world"]), {"affiliation", "merit"})

    def test_fresh_midpoint_fetches_use_staged_sessions_and_only_in_run_cache(self):
        profiles = {
            "text-af-ps": [{"kdma": "affiliation", "value": 0}, {"kdma": "personal_safety", "value": 0.2}],
            "text-mf-ss": [{"kdma": "merit", "value": 1}, {"kdma": "search", "value": 0.8}],
            "ow": [{"kdma": "affiliation", "value": 0.3}, {"kdma": "merit", "value": 0.7}],
        }
        self.http.get.side_effect = lambda url, params, timeout: response(profiles[params["session_id"]])
        text_sessions = {
            "affiliation": "text-af-ps", "personal_safety": "text-af-ps",
            "merit": "text-mf-ss", "search": "text-mf-ss",
        }
        with patch.object(matcher, "find_text_session_for_alignment") as lookup:
            result = matcher.compute_midpoint_values(
                self.metadata, "ow", text_session_ids=text_sessions, strict=True,
            )
        lookup.assert_not_called()
        self.assertEqual(self.http.get.call_count, 3)
        self.assertEqual(result["text"]["affiliation"], {"sid": "text-af-ps", "value": 0})
        self.assertEqual(result["text"]["merit"], {"sid": "text-mf-ss", "value": 1})
        self.assertEqual(result["open_world"]["merit"], {"sid": "ow", "value": 0.7})

    def test_staged_midpoint_alignment_fetches_fresh_scores(self):
        self.http.get.return_value = response({"score": 0.6})
        with patch.object(matcher, "find_text_session_for_alignment") as lookup:
            result = matcher.compute_midpoint_alignment_scores(
                self.metadata, "ow", text_session_ids={"affiliation": "text-af", "merit": "text-mf"},
                strict=True,
            )
        lookup.assert_not_called()
        self.assertEqual(self.http.get.call_count, 2)
        self.assertEqual(result["merit"], {"open_world_sid": "ow", "text_sid": "text-mf", "score": 0.6})

    def test_default_midpoint_behavior_still_reuses_saved_values(self):
        existing = {"affiliation": {"open_world_sid": "ow", "text_sid": "stored-text", "score": 0.9}}
        with patch.object(matcher, "find_text_session_for_alignment", side_effect=["stored-text", None]):
            result = matcher.compute_midpoint_alignment_scores(self.metadata, "ow", existing_scores=existing)
        self.assertEqual(result, existing)
        self.http.get.assert_not_called()

    def test_existing_strict_midpoint_calls_keep_empty_and_partial_results(self):
        self.http.get.return_value = response([])
        self.assertEqual(matcher.get_midpoint_profile("stored-session", strict=True), {})
        with patch.object(matcher, "find_text_session_for_alignment", return_value="stored-text"):
            self.assertEqual(matcher.compute_midpoint_values(
                self.metadata, "stored-ow", strict=True,
            ), {"text": {}, "open_world": {}})
        self.http.get.return_value = response({"score": None})
        with patch.object(matcher, "find_text_session_for_alignment", return_value="stored-text"):
            self.assertEqual(matcher.compute_midpoint_alignment_scores(
                self.metadata, "stored-ow", strict=True,
            ), {})

    def test_existing_strict_midpoint_calls_still_propagate_request_failures(self):
        self.http.get.side_effect = RuntimeError("service unavailable")
        with self.assertRaisesRegex(RuntimeError, "service unavailable"):
            matcher.get_midpoint_profile("stored-session", strict=True)

    def test_strict_midpoint_alignment_rejects_invalid_score(self):
        for value in (None, True, float("inf"), float("nan"), -0.1, 1.1):
            with self.subTest(value=value):
                self.http.get.return_value = response({"score": value})
                with self.assertRaises(ValueError):
                    matcher.compute_midpoint_alignment_scores(
                        self.metadata, "ow", text_session_ids={"merit": "text"}, strict=True,
                    )

    def test_strict_midpoint_profile_rejects_invalid_and_duplicate_entries(self):
        invalid_profiles = [
            [], {}, [None], [{"kdma": "merit", "value": True}],
            [{"kdma": "merit", "value": float("inf")}],
            [{"kdma": "merit", "value": 0.5}, {"kdma": "merit", "value": 0.5}],
        ]
        for payload in invalid_profiles:
            with self.subTest(payload=payload):
                self.http.get.return_value = response(payload)
                with self.assertRaises(ValueError):
                    matcher.get_midpoint_profile("session", strict=True, validate=True)

    def test_strict_midpoint_values_reject_missing_expected_attribute(self):
        self.http.get.return_value = response([{"kdma": "merit", "value": 0.5}])
        with self.assertRaisesRegex(ValueError, "Missing affiliation"):
            matcher.compute_midpoint_values(self.metadata, "ow", text_session_ids={}, strict=True)


if __name__ == "__main__":
    unittest.main()
