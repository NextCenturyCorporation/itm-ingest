# feb2026_probe_matcher.py
#
# Feb 2026 Probe Matcher (Open World)
# - Handles Feb 2026 OW Desert/Urban files
# - Robust to participantId being non-numeric (e.g., "test"), while still treating numeric PIDs as ints when needed
# - Fixes InjuryTreatmentComplete parsing bug (string "False" previously evaluated truthy)
# - Derives required procedures + triage ground truth from CSV (PATIENT_RECORD / INJURY_RECORD) instead of hardcoding
# - Adds --testdata mode so repo fixtures can be processed without Mongo participantLog/date gating
#
# Usage examples:
#   python feb2026_probe_matcher.py -i testdata_probe_matcher_openworld -n -v --testdata
#   python feb2026_probe_matcher.py -i /path/to/runs --eval_prefix feb2026 --eval_name "Phase II February 2026 Evaluation" -v
#
import argparse
import copy
import csv
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests
import yaml
from dateutil import parser as dateparser
from decouple import config
from pymongo import MongoClient

from logger import LogLevel, Logger


# -------------------------
# Runtime Flags / Defaults
# -------------------------
SEND_TO_MONGO = True
CALC_KDMAS = True
VERBOSE = False

DEFAULT_EVAL_PREFIX = "feb2026"
DEFAULT_EVAL_NAME = "Phase II February 2026 Evaluation"
DEFAULT_EVAL_NUM = 15  # You can override via CLI; keep numeric for dashboards if needed.

ADEPT_URL = config("ADEPT_URL", default="").rstrip("/") + "/"

KDMA_MAP = {
    "affiliation": "AF",
    "merit": "MF",
    "personal_safety": "PS",
    "search": "SS",
    "Moral judgement": "MJ",
    "Ingroup Bias": "IO",
}

# These are used to derive expected tag colors (ground truth) from PATIENT_RECORD triage level.
# Your Feb CSV uses TagType colors like "red", "yellow", "green" (and possibly "gray").
TRIAGE_LEVEL_TO_TAG_COLOR = {
    "IMMEDIATE": "red",
    "DELAYED": "yellow",
    "MINIMAL": "green",
    "EXPECTANT": "gray",
}

# Procedures considered "hemorrhage control" for the hemorrhage metric.
HEMORRHAGE_CONTROL_PROCS = {"tourniquet", "woundpack", "israeliWrap"}


# -------------------------
# Mongo Globals (set in main)
# -------------------------
mongo_collection_matches = None
mongo_collection_raw = None
participant_log_collection = None
text_scenario_collection = None


# -------------------------
# Helpers
# -------------------------
def _safe_bool_from_csv(value) -> bool:
    """
    Convert CSV string-ish booleans to actual bool.
    Handles: True/False, true/false, 1/0, yes/no, empty.
    """
    if value is None:
        return False
    s = str(value).strip().lower()
    return s in ("true", "1", "yes", "y", "t")


def _timestamp_to_seconds(ts_str: str) -> float:
    # CSV Timestamp is like "2/19/2026 11:42:39 AM"
    # dateutil can parse it.
    return datetime.fromisoformat(str(dateparser.parse(ts_str))).timestamp()


def _parse_action_iso_to_epoch_ms(iso_str: str) -> Optional[int]:
    """
    JSON actionList timestamp is commonly ISO Zulu, e.g. 2026-02-19T16:42:39.123Z
    """
    try:
        return int(datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp() * 1000)
    except Exception:
        try:
            return int(dateparser.parse(iso_str).timestamp() * 1000)
        except Exception:
            return None


def _is_numeric_pid(pid: str) -> bool:
    return isinstance(pid, str) and pid.isdigit()


def _find_json_files(input_dir: str) -> List[str]:
    """
    Recursively find JSON files under input_dir. We treat each JSON file as a run.
    """
    hits = []
    for root, _, files in os.walk(input_dir):
        for f in files:
            if f.lower().endswith(".json"):
                hits.append(os.path.join(root, f))
    return hits


def _find_csv_for_run(json_path: str) -> Optional[str]:
    """
    The matcher expects a CSV in the same folder as the JSON.

    Priority:
      1) <json_basename>.csv
      2) <foldername>.csv
      3) if exactly one CSV exists in the folder, use it
    """
    run_dir = os.path.dirname(json_path)
    json_base = os.path.splitext(os.path.basename(json_path))[0]
    folder_base = os.path.basename(run_dir)

    candidates = [
        os.path.join(run_dir, f"{json_base}.csv"),
        os.path.join(run_dir, f"{folder_base}.csv"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    csvs = [os.path.join(run_dir, f) for f in os.listdir(run_dir) if f.lower().endswith(".csv")]
    if len(csvs) == 1:
        return csvs[0]
    return None


def _read_csv_rows(csv_path: str) -> Tuple[List[str], List[List[str]]]:
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        data = [row for row in reader]
    return header, data


def _index_map(header: List[str]) -> Dict[str, int]:
    return {name: i for i, name in enumerate(header)}


def _get_cell(row: List[str], idx: Dict[str, int], col: str, default=None):
    i = idx.get(col)
    if i is None or i >= len(row):
        return default
    return row[i]


def _clean_patient_name(p: str) -> str:
    # Old matcher stripped " Root"; keep same behavior.
    return (p or "").split(" Root")[0].strip()


def _infer_env_from_json(json_data: dict) -> Optional[str]:
    """
    Returns "desert" / "urban" if it can infer it, else None.
    """
    # Prefer scenario name / narrative description
    name = str(json_data.get("configData", {}).get("scenarioData", {}).get("name", "")).lower()
    narrative = str(json_data.get("configData", {}).get("narrative", {}).get("narrativeDescription", "")).lower()

    blob = f"{name} {narrative}"
    if "desert" in blob:
        return "desert"
    if "urban" in blob:
        return "urban"
    return None


def _is_tutorial(json_data: dict) -> bool:
    cfg = json_data.get("configData", {})
    if cfg.get("teleportPointOverride") == "Tutorial":
        return True
    # Defensive narrative parsing
    try:
        sections = cfg.get("narrative", {}).get("narrativeSections", [])
        if sections and "Tutorial" in (sections[0].get("sectionDescription", "") or ""):
            return True
    except Exception:
        pass
    return False


# -------------------------
# Probe Matcher Class
# -------------------------
class ProbeMatcher:
    logger = Logger("feb2026_probeMatcher")

    def __init__(
        self,
        json_path: str,
        csv_path: str,
        eval_prefix: str,
        eval_name: str,
        eval_num: int,
        testdata_mode: bool,
    ):
        self.eval_prefix = eval_prefix
        self.eval_name = eval_name
        self.eval_num = eval_num
        self.testdata_mode = testdata_mode

        self.json_path = json_path
        self.csv_path = csv_path

        self.json_filename = ""
        self.json_data = None
        self.output_ow = None
        self.ow_yaml = None

        self.participant_id: str = ""
        self.participant_id_int: Optional[int] = None
        self.pid_in_log: bool = False

        self.environment_yaml: str = ""  # e.g., feb2026-desert-openworld.yaml
        self.environment_short: str = ""  # "Desert" or "Urban"
        self.timestamp_ms: Optional[int] = None

        # Load JSON
        with open(json_path, "r", encoding="utf-8") as jf:
            self.json_data = json.load(jf)
            self.json_filename = jf.name

        # Filter tutorial / no-actions
        if _is_tutorial(self.json_data):
            self.logger.log(LogLevel.CRITICAL_INFO, "Tutorial level, not processing data")
            return
        if len(self.json_data.get("actionList", [])) <= 1:
            self.logger.log(LogLevel.WARN, "No actions taken")
            return

        # Timestamp from first action
        first_ts = self.json_data["actionList"][0].get("timestamp")
        self.timestamp_ms = _parse_action_iso_to_epoch_ms(first_ts) if first_ts else None
        if self.timestamp_ms is None and first_ts:
            self.logger.log(
                LogLevel.WARN,
                f"Could not convert {first_ts} to timestamp ms. Continuing without timestamp.",
            )

        # Participant ID (string-first, but store int when numeric)
        pid = str(self.json_data.get("participantId") or "").strip()
        if pid == "":
            pid = str(self.json_data.get("sessionId") or "").strip()
        if pid == "":
            pid = "unknown"
        self.participant_id = pid
        self.participant_id_int = int(pid) if _is_numeric_pid(pid) else None

        # Participant log gating (skip in testdata mode)
        if not self.testdata_mode and participant_log_collection is not None and self.participant_id_int is not None:
            self.pid_in_log = participant_log_collection.count_documents({"ParticipantID": self.participant_id_int}) > 0
        else:
            self.pid_in_log = False

        # Determine environment
        env = _infer_env_from_json(self.json_data)
        if env is None:
            self.logger.log(LogLevel.WARN, "Unable to infer environment (desert/urban) from JSON; skipping.")
            return

        self.environment_short = "Desert" if env == "desert" else "Urban"
        self.environment_yaml = f"{self.eval_prefix}-{env}-openworld.yaml"
        self.logger.log(LogLevel.INFO, f"Environment: {self.environment_yaml}")

        # Create output directory & output file
        try:
            os.makedirs(f"output_{self.eval_prefix}", exist_ok=True)
        except Exception:
            self.logger.log(LogLevel.ERROR, f"Could not create output directory output_{self.eval_prefix}")

        out_name = os.path.join(
            f"output_{self.eval_prefix}",
            f"{self.eval_prefix}-{env}-openworld_{self.participant_id}.json",
        )
        if VERBOSE:
            self.logger.log(LogLevel.INFO, f"Create output file {out_name}")
        self.output_ow = open(out_name, "w", encoding="utf-8")

        # Load YAML
        yaml_filename = os.path.join("phase2", self.eval_prefix, "openworld", self.environment_yaml)
        try:
            if VERBOSE:
                self.logger.log(LogLevel.INFO, f"Opening {yaml_filename}")
            with open(yaml_filename, "r", encoding="utf-8") as yf:
                self.ow_yaml = yaml.load(yf, Loader=yaml.CLoader)
        except Exception as e:
            self.logger.log(
                LogLevel.ERROR,
                "Error loading open world yaml file. Ensure it's valid YAML and exists.\n\n" + str(e) + "\n",
            )
            self.ow_yaml = None

        # Clean JSON actions (dedupe adjacent breathing/pulse checks)
        self.clean_json()

    def __del__(self):
        if self.output_ow:
            try:
                self.output_ow.close()
            except Exception:
                pass

    def is_ready(self) -> bool:
        return bool(self.environment_yaml) and self.json_data is not None and self.ow_yaml is not None

    def clean_json(self):
        actions = self.json_data.get("actionList", [])
        if not actions:
            return
        new_actions = []
        for i in range(len(actions) - 1):
            a = actions[i]
            b = actions[i + 1]
            if a.get("actionType") in ["Breathing", "Pulse"]:
                if b.get("actionType") == a.get("actionType") and b.get("casualty") == a.get("casualty"):
                    continue
            new_actions.append(a)
        new_actions.append(actions[-1])
        self.json_data["actionList"] = new_actions

    # -------------------------
    # TA1 / ADEPT KDMA calls
    # -------------------------
    def get_ta1_calculations(self, scenario_id: str, probes: list) -> Tuple[Optional[str], Optional[list]]:
        if not probes:
            return None, None
        if not ADEPT_URL or ADEPT_URL == "/":
            self.logger.log(LogLevel.WARN, "ADEPT_URL not set; skipping KDMA computation.")
            return None, None
        try:
            session_id = requests.post(f"{ADEPT_URL}api/v1/new_session").text.replace('"', "").strip()
            if VERBOSE:
                self.logger.log(LogLevel.INFO, f"--> Sending probes: {probes}")
            for probe in probes:
                requests.post(
                    f"{ADEPT_URL}api/v1/response",
                    json={
                        "response": {
                            "probe_id": probe["probe_id"],
                            "choice": probe["choice"],
                            "justification": "justification",
                            "scenario_id": scenario_id,
                        },
                        "session_id": session_id,
                    },
                    timeout=30,
                )
            kdmas = requests.get(
                f"{ADEPT_URL}api/v1/computed_kdma_profile?session_id={session_id}",
                timeout=30,
            ).json()
        except Exception:
            self.logger.log(LogLevel.WARN, "TA1 Server request failed; no KDMAs generated.")
            return None, None
        return session_id, kdmas

    # -------------------------
    # Probe matching + analysis
    # -------------------------
    def match_probes(self):
        env = self.environment_short
        self.match_ow_probes(env)
        self.analyze_openworld(env)

    def match_ow_probes(self, env: str):
        """
        OpenWorld: each probe is a choice between Patient A and Patient B.
        We parse YAML scenes to map probe_id -> {sim_patient_name -> choice_id}
        Then we find which patient was first engaged by user in JSON actionList.
        """
        self.logger.log(LogLevel.INFO, f"Processing probe match for {env}")

        # Build probe map from YAML
        probe_map: Dict[str, Dict[str, str]] = {}
        for scene in self.ow_yaml.get("scenes", []):
            patient_name_map = {}
            response_map = {}
            for character in scene.get("state", {}).get("characters", []):
                # Sim patient name is after semicolon in 'unstructured'
                unstructured = character.get("unstructured", "")
                sim_patient_name = unstructured.split(";")[-1].strip()
                patient_name_map[character.get("id")] = sim_patient_name
            for mapping in scene.get("action_mapping", []):
                probe_id = mapping.get("probe_id")
                choice_id = mapping.get("choice")
                character_id = mapping.get("character_id")
                if probe_id and choice_id and character_id in patient_name_map:
                    response_map[patient_name_map[character_id]] = choice_id
                    probe_map[probe_id] = response_map

        # Engagement actions in Feb JSON are Pulse/Treatment/Tag
        engagement_actions = {"Pulse", "Treatment", "Tag"}
        action_list: list = [a for a in self.json_data.get("actionList", []) if a.get("actionType") in engagement_actions]

        def first_engaged(characters: List[str]) -> Optional[str]:
            for a in action_list:
                casualty = a.get("casualty")
                for ch in characters:
                    if casualty == ch:
                        return ch
            return None

        probes: list = []
        match_rows: list = []
        for probe_id, response_map in probe_map.items():
            first_char = first_engaged(list(response_map.keys()))
            if first_char:
                probes.append({"probe_id": probe_id, "choice": response_map[first_char]})
                match_rows.append(
                    {
                        "scene_id": probe_id,
                        "probe_id": probe_id,
                        "found_match": True,
                        "response": response_map[first_char],
                        "user_action": {},
                    }
                )
            else:
                self.logger.log(LogLevel.WARN, f"Unmatched probe {probe_id}.")
                match_rows.append(
                    {"scene_id": probe_id, "probe_id": probe_id, "found_match": False, "response": "", "user_action": {}}
                )

        self.logger.log(LogLevel.INFO, f"Found {len(probes)} out of {len(probe_map)} probes.")

        ow_align = {}
        if CALC_KDMAS:
            ow_align["sid"], ow_align["kdmas"] = self.get_ta1_calculations(self.ow_yaml.get("id", ""), probes)

        match_data = {"alignment": ow_align, "data": match_rows}

        # Save match data
        if SEND_TO_MONGO and mongo_collection_matches is not None:
            mongo_id = f"{self.participant_id}_ow_{self.environment_yaml.split('.yaml')[0]}"
            doc = {
                "scenario_id": self.ow_yaml.get("id", ""),
                "timestamp": self.timestamp_ms,
                "evalNumber": self.eval_num,
                "evalName": self.eval_name,
                "data": match_data,
                "ta1": "ow",
                "env": self.environment_yaml.split(".yaml")[0],
                "pid": self.participant_id,
                "_id": mongo_id,
                "openWorld": True,
            }
            try:
                mongo_collection_matches.insert_one(doc)
            except Exception:
                mongo_collection_matches.update_one({"_id": mongo_id}, {"$set": doc}, upsert=True)

        json.dump(match_data, self.output_ow, indent=4)

    def analyze_openworld(self, env: str):
        """
        Computes OpenWorld metrics using CSV + JSON.
        Key Feb changes:
          - Derive expected tags from PATIENT_RECORD triage level
          - Derive required procedures from INJURY_RECORD
          - Fix InjuryTreatmentComplete string->bool parsing
        """
        results = {
            "pid": self.participant_id,
            f"{env} Assess_patient": 0,
            f"{env} Assess_total": 0,
            f"{env} Treat_patient": 0,
            f"{env} Treat_total": 0,
            f"{env} Triage_time": 0,
            f"{env} Triage_time_patient": 0,
            f"{env} Engage_patient": 0,
            f"{env} Tag_ACC": None,
            f"{env} Tag_Expectant": None,
            f"{env} Hemorrhage control": None,
            f"{env} Hemorrhage control_time": None,
            f"{env} Triage Performance": None,
        }

        header, data = _read_csv_rows(self.csv_path)
        idx = _index_map(header)

        # -------------------------
        # Derive ground-truth tags from PATIENT_RECORD
        # -------------------------
        expected_tag_color: Dict[str, str] = {}
        for row in data:
            if _get_cell(row, idx, "EventName") == "PATIENT_RECORD":
                pid = _clean_patient_name(_get_cell(row, idx, "PatientID", ""))
                triage_level = str(_get_cell(row, idx, "PatientTriageLevel", "")).strip().upper()
                if triage_level in TRIAGE_LEVEL_TO_TAG_COLOR:
                    expected_tag_color[pid] = TRIAGE_LEVEL_TO_TAG_COLOR[triage_level]

        # -------------------------
        # Derive required procedures from INJURY_RECORD
        # patient -> list of InjuryName required
        # injury -> required procedure (tool category)
        # -------------------------
        required_injuries: Dict[str, List[str]] = {}
        required_proc_for_injury: Dict[Tuple[str, str], str] = {}  # (patient, injuryname) -> required proc
        for row in data:
            if _get_cell(row, idx, "EventName") == "INJURY_RECORD":
                patient = _clean_patient_name(_get_cell(row, idx, "PatientID", ""))
                injury = str(_get_cell(row, idx, "InjuryName", "")).strip()
                proc = str(_get_cell(row, idx, "InjuryRequiredProcedure", "")).strip()
                if patient and injury:
                    required_injuries.setdefault(patient, []).append(injury)
                    required_proc_for_injury[(patient, injury)] = proc

        # -------------------------
        # Utility: engagement metrics
        # -------------------------
        def find_patients_engaged():
            engagement_events = {"TOOL_APPLIED", "TAG_APPLIED", "PULSE_TAKEN", "SP_O2_TAKEN", "BREATHING_CHECKED"}
            engagement_order = []
            treated = []
            for row in data:
                ev = _get_cell(row, idx, "EventName")
                if ev in engagement_events:
                    patient = _clean_patient_name(_get_cell(row, idx, "PatientID", ""))
                    if not patient or any(x in patient for x in ["Level Core", "Simulation", "Player"]):
                        continue
                    engagement_order.append(patient)
                    if ev == "TOOL_APPLIED":
                        treated.append(patient)

            simple_order = []
            for p in engagement_order:
                if simple_order and p == simple_order[-1]:
                    continue
                simple_order.append(p)

            engaged_unique = len(set(engagement_order))
            treated_unique = len(set(treated))
            return {"engaged": engaged_unique, "treated": treated_unique, "order": simple_order}

        engaged_counts = find_patients_engaged()
        patients_engaged = engaged_counts["engaged"]
        patients_treated = engaged_counts["treated"]
        patient_order_engaged = engaged_counts["order"]
        engagement_times = list({p: patient_order_engaged.count(p) for p in set(patient_order_engaged)}.values())
        results[f"{env} Engage_patient"] = sum(engagement_times) / max(1, len(engagement_times))

        # -------------------------
        # Assessments (Feb: pulse is the main one; keep others if present)
        # -------------------------
        def count_assessment_actions():
            assessment_events = {"SP_O2_TAKEN", "BREATHING_CHECKED", "PULSE_TAKEN"}
            count = 0
            last_done = {}
            per_patient = {}
            for row in data:
                ev = _get_cell(row, idx, "EventName")
                if ev in assessment_events:
                    ts = _get_cell(row, idx, "Timestamp")
                    if not ts:
                        continue
                    ts_sec = _timestamp_to_seconds(ts)
                    # only count events more than 5 seconds apart from last same type
                    if ev not in last_done or (ts_sec - last_done[ev]) > 5:
                        last_done[ev] = ts_sec
                        count += 1
                        patient = _clean_patient_name(_get_cell(row, idx, "PatientID", ""))
                        per_patient[patient] = per_patient.get(patient, 0) + 1
            return {"count": count, "per_patient": per_patient}

        assessments = count_assessment_actions()
        results[f"{env} Assess_total"] = assessments["count"]
        results[f"{env} Assess_patient"] = results[f"{env} Assess_total"] / max(1, patients_engaged)

        # -------------------------
        # Treatments
        # -------------------------
        def count_treatment_actions():
            count = 0
            per_patient = {}
            for row in data:
                ev = _get_cell(row, idx, "EventName")
                if ev == "TOOL_APPLIED":
                    tool = str(_get_cell(row, idx, "ToolType", "") or "")
                    if "Pulse Oximeter" in tool:
                        continue
                    count += 1
                    patient = _clean_patient_name(_get_cell(row, idx, "PatientID", ""))
                    per_patient[patient] = per_patient.get(patient, 0) + 1
            return {"count": count, "per_patient": per_patient}

        treatments = count_treatment_actions()
        results[f"{env} Treat_total"] = treatments["count"]
        results[f"{env} Treat_patient"] = results[f"{env} Treat_total"] / max(1, patients_treated)

        # -------------------------
        # Triage time
        # -------------------------
        def get_triage_time_seconds():
            if len(data) > 1:
                try:
                    start = float(_get_cell(data[0], idx, "ElapsedTime", 0))
                    # near-last row is safer due to possible trailing rows
                    end = float(_get_cell(data[-2], idx, "ElapsedTime", 0))
                    return (end - start) / 1000.0
                except Exception:
                    return 0.0
            return 0.0

        results[f"{env} Triage_time"] = get_triage_time_seconds()

        # -------------------------
        # Tag accuracy: compare last TAG_APPLIED to expected color (from PATIENT_RECORD)
        # -------------------------
        def get_tags():
            tags_applied = {}
            for row in data:
                if _get_cell(row, idx, "EventName") == "TAG_APPLIED":
                    patient = _clean_patient_name(_get_cell(row, idx, "PatientID", ""))
                    tag = str(_get_cell(row, idx, "TagType", "")).strip().lower()
                    if patient:
                        tags_applied[patient] = tag

            if not expected_tag_color:
                # No ground-truth; return applied tags but no accuracy
                return {"correct": 0, "count": 0, "tags": tags_applied, "acc": None}

            correct = 0
            count = 0
            for patient, applied in tags_applied.items():
                expected = expected_tag_color.get(patient)
                if expected is None:
                    continue
                count += 1
                if expected == applied:
                    correct += 1
            acc = correct / max(1, count) if count > 0 else None
            return {"correct": correct, "count": count, "tags": tags_applied, "acc": acc}

        tag_counts = get_tags()
        results[f"{env} Tag_ACC"] = tag_counts["acc"]

        # Expectant tagging: did any EXPECTANT patient receive the gray tag?
        expectant_patients = [p for p, col in expected_tag_color.items() if col == "gray"]
        results[f"{env} Tag_Expectant"] = None
        if expectant_patients:
            any_gray = any(tag_counts["tags"].get(p) == "gray" for p in expectant_patients)
            results[f"{env} Tag_Expectant"] = "Yes" if any_gray else "No"

        # -------------------------
        # Time per patient: total time engaged per patient based on engagement events
        # -------------------------
        def find_time_per_patient():
            interactions = {}
            cur_p = None
            start_time = 0.0
            last_time = 0.0

            engagement_events = {"TOOL_APPLIED", "TAG_APPLIED", "PULSE_TAKEN", "SP_O2_TAKEN", "BREATHING_CHECKED"}
            for row in data:
                ev = _get_cell(row, idx, "EventName")
                if ev not in engagement_events:
                    continue
                patient = _clean_patient_name(_get_cell(row, idx, "PatientID", ""))
                if not patient or any(x in patient for x in ["Level Core", "Simulation", "Player"]):
                    continue
                try:
                    t = float(_get_cell(row, idx, "ElapsedTime", 0))
                except Exception:
                    continue

                interactions.setdefault(patient, [])

                if cur_p is None:
                    cur_p = patient
                    start_time = last_time if last_time != 0 else t
                    last_time = t
                    continue

                if cur_p != patient:
                    # close previous segment
                    interactions[cur_p].append((start_time, last_time if last_time != 0 else t))
                    cur_p = patient
                    start_time = t
                    last_time = t
                else:
                    last_time = t

            if cur_p is not None:
                interactions[cur_p].append((start_time, last_time))

            total_time_ms = 0.0
            per_patient_seconds = {}
            for patient, segs in interactions.items():
                patient_ms = 0.0
                for s, e in segs:
                    patient_ms += max(0.0, e - s)
                total_time_ms += patient_ms
                per_patient_seconds[patient] = patient_ms / 1000.0

            return {"interactions": per_patient_seconds, "total": total_time_ms / 1000.0}

        triage_times = find_time_per_patient()
        results[f"{env} Triage_time_patient"] = triage_times["total"] / max(1, patients_engaged)

        # -------------------------
        # Evacuation answers (Feb JSON questions)
        # -------------------------
        def get_evaced_patients_from_json():
            answers = []
            # Map answer label -> patient ID is scenario-specific; keep a hook.
            # If your Feb scenarios keep consistent answer strings, put the mapping here.
            # If you don't have a mapping yet, we store raw answer text instead.
            for action in self.json_data.get("actionList", []):
                if action.get("actionType") == "Question":
                    q = str(action.get("question", "")).lower()
                    if "evacuate" in q:
                        ans = action.get("answer")
                        if ans:
                            answers.append(str(ans).strip())
            return answers

        evaced_answers = get_evaced_patients_from_json()

        # -------------------------
        # Search + Personal Safety
        # -------------------------
        def get_ps_ss():
            search_answers = []
            answer_map = {"Stay": 0, "Search": 1}
            ps1 = 0

            for action in self.json_data.get("actionList", []):
                if action.get("actionType") == "Question":
                    q = str(action.get("question", "")).lower()
                    if "search" in q:
                        ans = action.get("answer")
                        if ans in answer_map:
                            search_answers.append(answer_map[ans])
                elif action.get("actionType") == "MovedBeforeClearedByCommand":
                    if action.get("movedBeforeClearedByCommand") is True:
                        ps1 = 1

            # Keep compatibility with old output keys (Search1/Search2)
            search1 = search_answers[0] if len(search_answers) >= 1 else None
            search2 = search_answers[1] if len(search_answers) >= 2 else None
            return search1, search2, ps1

        search1, search2, ps1 = get_ps_ss()
        results[f"{env} Search1"] = search1
        results[f"{env} Search2"] = search2
        results[f"{env} Personal_safety"] = ps1

        # -------------------------
        # Hemorrhage control (derived): all injuries whose required procedure is hemorrhage control must be complete
        # -------------------------
        def get_hemorrhage_control():
            to_complete = {}  # patient -> set(injury)
            for (patient, injury), proc in required_proc_for_injury.items():
                if proc in HEMORRHAGE_CONTROL_PROCS:
                    to_complete.setdefault(patient, set()).add(injury)

            start_time_sec = None
            end_time_sec = None

            for row in data:
                ev = _get_cell(row, idx, "EventName")
                if ev == "SESSION_START":
                    ts = _get_cell(row, idx, "Timestamp")
                    if ts:
                        start_time_sec = _timestamp_to_seconds(ts)

                if ev == "INJURY_TREATED":
                    patient = _clean_patient_name(_get_cell(row, idx, "PatientID", ""))
                    injury = str(_get_cell(row, idx, "InjuryName", "")).strip()
                    completed = _safe_bool_from_csv(_get_cell(row, idx, "InjuryTreatmentComplete"))
                    if not completed:
                        continue

                    if patient in to_complete and injury in to_complete[patient]:
                        to_complete[patient].remove(injury)
                        ts = _get_cell(row, idx, "Timestamp")
                        if ts:
                            end_time_sec = _timestamp_to_seconds(ts)
                        if len(to_complete[patient]) == 0:
                            del to_complete[patient]

            res = 1 if len(to_complete) == 0 else 0
            time_to = None
            if res == 1 and start_time_sec is not None and end_time_sec is not None:
                time_to = (end_time_sec - start_time_sec)
            return {"completed": res, "time": time_to}

        hem = get_hemorrhage_control()
        results[f"{env} Hemorrhage control"] = hem["completed"]
        results[f"{env} Hemorrhage control_time"] = hem["time"]

        # -------------------------
        # Triage performance (derived):
        # hits: INJURY_TREATED complete for required injuries
        # misses: required injuries never completed
        # false alarms: TOOL_APPLIED count (except pulse ox)
        # score = hits / (tools_applied + misses) * 100
        # -------------------------
        def get_triage_performance():
            remaining = {p: set(inj_list) for p, inj_list in required_injuries.items()}
            correct_completed = 0
            total_tools_applied = 0

            for row in data:
                ev = _get_cell(row, idx, "EventName")

                if ev == "INJURY_TREATED":
                    patient = _clean_patient_name(_get_cell(row, idx, "PatientID", ""))
                    injury = str(_get_cell(row, idx, "InjuryName", "")).strip()
                    completed = _safe_bool_from_csv(_get_cell(row, idx, "InjuryTreatmentComplete"))
                    if completed and patient in remaining and injury in remaining[patient]:
                        remaining[patient].remove(injury)
                        correct_completed += 1
                        if len(remaining[patient]) == 0:
                            del remaining[patient]

                if ev == "TOOL_APPLIED":
                    tool = str(_get_cell(row, idx, "ToolType", "") or "")
                    if "Pulse Oximeter" in tool:
                        continue
                    total_tools_applied += 1

            misses = sum(len(s) for s in remaining.values())
            denom = max(1, total_tools_applied + misses)
            return (correct_completed / denom) * 100.0

        results[f"{env} Triage Performance"] = get_triage_performance()

        # -------------------------
        # Per-patient breakout
        # Use PATIENT_RECORD order if available; else engagement order
        # -------------------------
        patients_in_order = []
        for row in data:
            if _get_cell(row, idx, "EventName") == "PATIENT_RECORD":
                p = _clean_patient_name(_get_cell(row, idx, "PatientID", ""))
                if p and p not in patients_in_order:
                    patients_in_order.append(p)
        if not patients_in_order:
            patients_in_order = []
            for p in patient_order_engaged:
                if p not in patients_in_order:
                    patients_in_order.append(p)

        clean_patient_order_engaged = []
        for p in patient_order_engaged:
            if p not in clean_patient_order_engaged:
                clean_patient_order_engaged.append(p)

        for i, sim_name in enumerate(patients_in_order):
            name = f"Patient{i+1}"
            results[f"{env} {name}_time"] = triage_times["interactions"].get(sim_name, 0)
            try:
                results[f"{env} {name}_order"] = clean_patient_order_engaged.index(sim_name) + 1
            except Exception:
                results[f"{env} {name}_order"] = "N/A"
            # We don't have a stable answer->patient mapping here yet, so store raw evac answers
            results[f"{env} {name}_evac"] = "Unknown"
            results[f"{env} {name}_assess"] = assessments["per_patient"].get(sim_name, 0)
            results[f"{env} {name}_treat"] = treatments["per_patient"].get(sim_name, 0)
            results[f"{env} {name}_tag"] = tag_counts["tags"].get(sim_name, "None")
            results[f"{env} {name}_triage_truth"] = expected_tag_color.get(sim_name, None)
            results[f"{env} {name}_required_injuries"] = required_injuries.get(sim_name, [])

        # -------------------------
        # Text KDMAs join (keep old behavior; safe if Mongo not present)
        # -------------------------
        text_kdma_results = {}
        if text_scenario_collection is None:
            for kdma in KDMA_MAP.values():
                text_kdma_results[f"Participant Text {kdma} KDMA"] = ""
        else:
            try:
                text_response = text_scenario_collection.find_one(
                    {
                        "evalNumber": self.eval_num,
                        "participantID": self.participant_id,
                        "scenario_id": {"$not": {"$regex": "PS-AF"}},
                    }
                )
            except Exception:
                text_response = None

            if text_response is None:
                self.logger.log(LogLevel.WARN, f"Error getting text KDMAs for pid {self.participant_id}.")
                for kdma in KDMA_MAP.values():
                    text_kdma_results[f"Participant Text {kdma} KDMA"] = ""
            else:
                kdmas = text_response.get("kdmas", [])
                for kdma in kdmas:
                    name = kdma.get("kdma")
                    if name in KDMA_MAP:
                        text_kdma_results[f"Participant Text {KDMA_MAP[name]} KDMA"] = kdma.get("value", "")

        if VERBOSE:
            self.logger.log(LogLevel.INFO, f"\n{env} Results: {results}")

        # -------------------------
        # Save to Mongo
        # -------------------------
        self.logger.log(LogLevel.INFO, f"{'' if SEND_TO_MONGO else 'NOT '}Saving to database.")
        if SEND_TO_MONGO and mongo_collection_raw is not None and mongo_collection_matches is not None:
            env_id = self.environment_yaml.split(".yaml")[0]
            raw_id = f"{self.participant_id}_{env_id}"
            match_id = f"{self.participant_id}_ow_{env_id}"

            # raw JSON
            raw_doc = {
                "openWorld": True,
                "evalNumber": self.eval_num,
                "evalName": self.eval_name,
                "data": self.json_data,
                "pid": self.participant_id,
                "_id": raw_id,
            }
            try:
                mongo_collection_raw.insert_one(raw_doc)
            except Exception:
                mongo_collection_raw.update_one({"_id": raw_id}, {"$set": raw_doc}, upsert=True)

            # analysis
            match_doc = {
                "scenario_id": self.ow_yaml.get("id", ""),
                "timestamp": self.timestamp_ms,
                "evalNumber": self.eval_num,
                "evalName": self.eval_name,
                "actionAnalysis": results,
                "openWorld": True,
                "env": env_id,
                "text_kdmas": text_kdma_results,
                "pid": self.participant_id,
                "_id": match_id,
            }
            try:
                mongo_collection_matches.insert_one(match_doc)
            except Exception:
                mongo_collection_matches.update_one({"_id": match_id}, {"$set": match_doc}, upsert=True)

            # participant log update (only if numeric PID)
            if participant_log_collection is not None and self.participant_id_int is not None:
                try:
                    num_sim_found = mongo_collection_raw.count_documents({"pid": str(self.participant_id)})
                    log_entry = participant_log_collection.find_one({"ParticipantID": self.participant_id_int})
                    if log_entry:
                        participant_log_collection.update_one(
                            {"_id": log_entry["_id"]},
                            {"$set": {"claimed": True, "simEntryCount": num_sim_found}},
                        )
                except Exception:
                    pass


# -------------------------
# Main
# -------------------------
def main():
    global SEND_TO_MONGO, CALC_KDMAS, VERBOSE
    global mongo_collection_matches, mongo_collection_raw, participant_log_collection, text_scenario_collection

    parser = argparse.ArgumentParser(
        description="ITM - Feb 2026 Probe Matcher",
        usage="feb2026_probe_matcher.py [-h] -i PATH [-n] [-v] [--testdata] [--eval_prefix PREFIX] [--eval_name NAME] [--eval_num N]",
    )
    parser.add_argument("-i", "--input_dir", dest="input_dir", type=str, required=True, help="Directory containing run folders/files.")
    parser.add_argument("-n", "--no_output", action="store_true", dest="no_output", help="Do not send to mongo.")
    parser.add_argument("-v", "--verbose", action="store_true", dest="is_verbose", help="Verbose output.")
    parser.add_argument("--no_kdmas", action="store_true", dest="no_kdmas", help="Do not compute KDMAs via ADEPT/TA1.")
    parser.add_argument("--testdata", action="store_true", dest="testdata", help="Testdata mode (skip participantLog/date gating).")

    parser.add_argument("--eval_prefix", dest="eval_prefix", type=str, default=DEFAULT_EVAL_PREFIX, help="Eval prefix folder under phase2/")
    parser.add_argument("--eval_name", dest="eval_name", type=str, default=DEFAULT_EVAL_NAME, help="Eval name stored in Mongo")
    parser.add_argument("--eval_num", dest="eval_num", type=int, default=DEFAULT_EVAL_NUM, help="Eval number stored in Mongo")

    args = parser.parse_args()

    if args.no_output:
        SEND_TO_MONGO = False
    if args.is_verbose:
        VERBOSE = True
    if args.no_kdmas:
        CALC_KDMAS = False

    # If you're running repo fixtures, force testdata behavior by default when --no_output is used.
    testdata_mode = bool(args.testdata or args.no_output)

    # Mongo setup (only if sending)
    if SEND_TO_MONGO:
        client = MongoClient(config("MONGO_URL"))
        db = client.dashboard
        mongo_collection_matches = db["humanSimulator"]
        mongo_collection_raw = db["humanSimulatorRaw"]
        participant_log_collection = db["participantLog"]
        text_scenario_collection = db["userScenarioResults"]
    else:
        participant_log_collection = None
        text_scenario_collection = None

    # Process JSON files
    json_files = _find_json_files(args.input_dir)
    if not json_files:
        print(f"No .json files found under {args.input_dir}")
        return

    removed = []
    for json_path in json_files:
        csv_path = _find_csv_for_run(json_path)
        if not csv_path:
            if VERBOSE:
                print(f"Skipping {json_path}: could not find matching .csv in the same folder.")
            continue

        # Optional: in non-testdata mode, replicate old gating: require numeric pid in participantLog and date threshold.
        # For Feb 2026 fixtures/testing, you generally want --testdata.
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                j = json.load(f)
        except Exception:
            continue

        if _is_tutorial(j):
            continue

        # Date gating (only in non-testdata mode)
        if not testdata_mode:
            # old code used csv second line timestamp and required after 2025-06-02.
            # For Feb 2026, we still keep a sanity threshold but you can adjust as needed.
            try:
                header, rows = _read_csv_rows(csv_path)
                if rows:
                    idx = _index_map(header)
                    ts = _get_cell(rows[1], idx, "Timestamp") if len(rows) > 1 else _get_cell(rows[0], idx, "Timestamp")
                    sim_date = dateparser.parse(ts) if ts else None
                    # Use Jan 1 2026 as minimum for feb2026 runs
                    min_date = datetime(2026, 1, 1)
                    if sim_date and sim_date < min_date:
                        removed.append(os.path.dirname(json_path))
                        continue
            except Exception:
                pass

            pid = str(j.get("participantId") or j.get("sessionId") or "").strip()
            pid_int = int(pid) if _is_numeric_pid(pid) else None
            if participant_log_collection is not None and pid_int is not None:
                pid_in_log = participant_log_collection.count_documents({"ParticipantID": pid_int}) > 0
                if not pid_in_log:
                    removed.append(os.path.dirname(json_path))
                    continue

        print(f"\n** Processing {os.path.basename(json_path)} **")
        try:
            matcher = ProbeMatcher(
                json_path=json_path,
                csv_path=csv_path,
                eval_prefix=args.eval_prefix,
                eval_name=args.eval_name,
                eval_num=args.eval_num,
                testdata_mode=testdata_mode,
            )
            if matcher.is_ready():
                matcher.match_probes()
            matcher.__del__()
        except Exception:
            import traceback

            traceback.print_exc()
            raise

    if removed:
        print("\nRemove the following path(s):")
        for path in sorted(set(removed)):
            print(f"  {path}")


if __name__ == "__main__":
    main()