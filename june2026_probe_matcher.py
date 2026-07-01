# ============================================================
# JUNE 2026 PROBE MATCHER
# ============================================================
#
# Processes June 2026 simulation JSON + CSV files and produces:
# - reusable open-world actionAnalysis/eventTotals fields
# - April-style personal-safety/search-safety probes
# - text KDMA joins from Mongo userScenarioResults
# - optional ADEPT/TA1 KDMA + alignment compare values
#
# This is intended to behave like the April probe matcher, but with the
# reusable extraction logic updated for the June/current sim log shapes.
#
# Flags:
#   -i / --input_dir     Input directory containing JSON/CSV files (required)
#   -o / --output_dir    Output directory for analysis files (default: output_sim_analysis)
#   -m / --send_to_mongo Enable MongoDB upsert using MONGO_URL from .env
#   -k / --calc_kdmas     Enable ADEPT/TA1 calls to compute open-world KDMAs
#                         and alignment compare values
#   -v / --verbose        Verbose command-line output
#
# ============================================================

import argparse
import copy
import csv
import json
import math
import os
import re
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None

try:
    import yaml
except ImportError:
    yaml = None

try:
    from decouple import config
except ImportError:
    def config(key, default=None, **kwargs):
        return os.environ.get(key, default)

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None

try:
    from logger import LogLevel, Logger
except ImportError:
    class LogLevel:
        INFO = "INFO"
        WARN = "WARN"
        ERROR = "ERROR"

    class Logger:
        def __init__(self, name):
            self.name = name

        def log(self, level, message):
            print(f"[{level}] {self.name}: {message}")

SEND_TO_MONGO = False
CALC_KDMAS = False
VERBOSE = False
ADEPT_URL = config("ADEPT_URL", default="").rstrip("/") + "/"
logger = Logger("june2026_probeMatcher")

mongo_collection_analysis = None
mongo_collection_raw = None
text_scenario_collection = None

ASSESSMENT_EVENTS = {"SP_O2_TAKEN", "BREATHING_CHECKED", "PULSE_TAKEN"}
ENGAGEMENT_EVENTS = {
    "TOOL_APPLIED",
    "TAG_APPLIED",
    "PULSE_TAKEN",
    "SP_O2_TAKEN",
    "BREATHING_CHECKED",
    "PATIENT_ENGAGED",
}

TRIAGE_LEVEL_TO_TAG_COLOR = {
    "IMMEDIATE": "red",
    "DELAYED": "yellow",
    "MINIMAL": "green",
    "EXPECTANT": "gray",
}

HEMORRHAGE_CONTROL_PROCS = {"tourniquet", "woundpack", "israeliWrap"}

MONTH_MAP = {
    "january": "jan",
    "february": "feb",
    "march": "mar",
    "april": "apr",
    "may": "may",
    # Keep June as the full month so detected open-world env values match
    # the June 2026 YAML filenames, e.g. june2026-desert-openworld.yaml.
    "june": "june",
    "july": "jul",
    "august": "aug",
    "september": "sept",
    "october": "oct",
    "november": "nov",
    "december": "dec",
}

KDMA_MAP = {
    "affiliation": "AF",
    "merit": "MF",
    "personal_safety": "PS",
    "search": "SS",
}

DEFAULT_EVAL_NUM = 17
DEFAULT_EVAL_NAME = "June 2026 Evaluation"



# April probe matcher personal-safety scoring, keyed by reusable answerIds.
# answerIds are normalized before lookup so values like
# "verbal_response/ask_for_clarification" and
# "verbal_response_/_ask_for_clarification" still map correctly.
ANSWER_ID_ALIASES = {
    "verbal_response/ask_for_clarification": "verbal_response_ask_for_clarification",
    "verbal_response_/_ask_for_clarification": "verbal_response_ask_for_clarification",
}

PERSONAL_SAFETY_SINGLE_ANSWER_SCORE_MAPS = {
    "PS2": {
        "run_to_house_stop_treating": 5,
        "stop_and_stare": 4,
        "drag_patients_to_house": 3,
        "verbal_concern": 2,
        "no_reaction": 1,
    },
}

PERSONAL_SAFETY_MULTI_ACTION_SCORE_MAPS = {
    "PS1": {
        frozenset(["remain_in_place"]): 5,
        # Matches the April probe matcher behavior: if only the verbal response
        # is recorded, score it the same as verbal response + remain in place.
        frozenset(["verbal_response_ask_for_clarification"]): 4,
        frozenset(["verbal_response_ask_for_clarification", "remain_in_place"]): 4,
        frozenset(["drag_patient_inside"]): 3,
        frozenset(["ignore_warning_and_approach_patient", "verbal_response_ask_for_clarification"]): 2,
        frozenset(["ignore_warning_and_approach_patient"]): 1,
    },
}

PERSONAL_SAFETY_CONFIG = {
    "desert": {
        "PS1": {
            "result_key": "Desert Probe_PS1",
            "actions_key": "Desert Probe_PS1_Actions",
            "multi_action": True,
            "score_map_key": "PS1",
        },
        "PS2": {
            "result_key": "Desert Probe_PS2",
            "actions_key": "Desert Probe_PS2_Actions",
            "multi_action": False,
            "answer_map_key": "PS2",
        },
    },
    "urban": {
        "PS1": {
            "result_key": "Urban Probe_PS1",
            "actions_key": "Urban Probe_PS1_Actions",
            "multi_action": True,
            "score_map_key": "PS1",
        },
    },
}


# April probe matcher inject/follow-on probe configuration.  The extraction
# below first tries to infer these patients from reusable JSON metadata, then
# falls back to these April-compatible names when the log does not provide a
# stronger signal.
INJECT_PATIENTS_FALLBACK = {
    "desert": ["US Military 6", "US Military 7"],
    "urban": ["US Military 5", "US Military 6"],
}

INJECT_RADIO_SECTION_NAME = {
    "desert": "Explosion Aftermath Radio.",
    "urban": "Explosion Aftermath Radio.",
}


# ============================================================
# BASIC HELPERS
# ============================================================

def safe_float(value, default=0.0):
    """Convert a value to float, returning a default on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_bool_from_csv(value) -> bool:
    """Convert common CSV boolean-like values into a boolean."""
    if value is None:
        return False
    return str(value).strip().lower() in ("true", "1", "yes", "y", "t")


def clean_patient_name(value):
    """Normalize patient names for consistent matching."""
    if value is None:
        return ""
    return str(value).split(" Root")[0].strip()


def is_valid_patient(patient_name):
    """Return True when the value represents a real patient entity."""
    if not patient_name:
        return False
    invalid_tokens = ["Level Core", "Simulation", "Player"]
    return not any(token in patient_name for token in invalid_tokens)


def timestamp_to_seconds(ts_value):
    """Parse a timestamp string into Unix seconds."""
    if not ts_value:
        return None

    ts_str = str(ts_value).strip()
    formats = [
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%y %I:%M:%S %p",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(ts_str, fmt).timestamp()
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(ts_str).timestamp()
    except ValueError:
        return None


# ============================================================
# FILE LOADING
# ============================================================

def load_csv_rows(csv_path):
    """Load the simulation CSV as a list of row dictionaries."""
    if not csv_path or not os.path.exists(csv_path):
        return []

    with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def build_env_prefix(env):
    """Return the output field prefix for an environment."""
    env_lower = str(env).lower()
    if "desert" in env_lower:
        return "Desert "
    if "urban" in env_lower:
        return "Urban "
    return ""


def extract_pid_from_filename(filename):
    """Extract the participant id from the run filename."""
    parts = filename.split("_")
    if len(parts) >= 2 and parts[1]:
        return parts[1]
    return parts[0] if parts else filename


def build_probe_matcher_style_id(pid, env):
    """Build the output document id."""
    return f"{pid}_ow_{env if env else 'unknown'}"

def get_nested_value(source, paths, default=None):
    """Return the first non-empty value found at one of the provided key paths."""
    if not isinstance(source, dict):
        return default

    for path in paths:
        current = source
        found = True
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                found = False
                break
        if found and current not in (None, ""):
            return current
    return default


def normalize_optional_int(value):
    """Convert numeric-looking values to int while preserving None."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def compute_spawn_location_value(sim_json, pid=None):
    """Return the reusable spawn-location value from session metadata, with PID fallback.

    Updated logs can provide sessionMetadata.spawnLocationId/spawnLocationID or
    spawnPoint.  The April matcher inferred spawn from PID parity, so that is
    retained only as a fallback for older logs without explicit metadata.
    """
    value = get_nested_value(
        sim_json,
        [
            ("sessionMetadata", "spawnLocationId"),
            ("sessionMetadata", "spawnLocationID"),
            ("sessionMetadata", "spawn_location"),
            ("sessionMetadata", "spawnLocation"),
            ("configData", "spawnLocationId"),
            ("configData", "spawnLocationID"),
            ("spawnLocationId",),
            ("spawnLocationID",),
            ("spawn_location",),
        ],
    )
    if value is not None:
        return normalize_optional_int(value)

    spawn_point = get_nested_value(
        sim_json,
        [
            ("sessionMetadata", "spawnPoint"),
            ("configData", "spawnPoint"),
            ("spawnPoint",),
        ],
    )
    if spawn_point is not None:
        return spawn_point

    pid_str = str(pid or "").strip()
    if pid_str.isdigit():
        return 0 if int(pid_str) % 2 == 0 else 1
    return None


def extract_eval_metadata(sim_json):
    """Extract evalNumber/evalName from reusable run/session metadata."""
    eval_number = get_nested_value(
        sim_json,
        [
            ("sessionMetadata", "evalNumber"),
            ("sessionMetadata", "eval_number"),
            ("configData", "evalNumber"),
            ("configData", "eval_number"),
            ("evalNumber",),
            ("eval_number",),
        ],
    )
    eval_name = get_nested_value(
        sim_json,
        [
            ("sessionMetadata", "evalName"),
            ("sessionMetadata", "eval_name"),
            ("configData", "evalName"),
            ("configData", "eval_name"),
            ("evalName",),
            ("eval_name",),
        ],
    )
    return {
        "evalNumber": normalize_optional_int(eval_number),
        "evalName": eval_name,
    }


def extract_patient_map_shown(sim_json):
    """Extract patientMapShown from session metadata, preserving 0/1 semantics."""
    value = get_nested_value(
        sim_json,
        [
            ("sessionMetadata", "patientMapShown"),
            ("sessionMetadata", "patient_map_shown"),
            ("configData", "patientMapShown"),
            ("configData", "patient_map_shown"),
            ("patientMapShown",),
            ("patient_map_shown",),
        ],
    )
    return normalize_optional_int(value)


def _split_patient_ids(value):
    """Normalize evac patient identifiers from list/scalar/comma-delimited values."""
    if value is None:
        return []
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = str(value).split(",")
    return [clean_patient_name(item) for item in raw_values if clean_patient_name(item)]


def compute_evac_value_by_patient(csv_rows, sim_json, env):
    """Extract per-patient evac values from reusable JSON/CSV evac selection records.

    This follows the April matcher semantics for the value itself:
    - Desert one-casualty evac round => 1
    - Desert two-casualty evac round => 2
    - Urban three-casualty evac round => 1

    Updated reusable logs provide the selected patient IDs directly in
    EvacSelection/EVAC_SELECTION records, so no scenario-specific answer-to-
    patient mapping is needed.
    """
    env_lower = str(env or "").lower()
    env_key = "desert" if "desert" in env_lower else "urban" if "urban" in env_lower else None
    if not env_key:
        return {}

    evac_value_by_patient = {}

    def apply_selection(patient_ids, prompt_text="", evac_round=None):
        if not patient_ids:
            return

        question = str(prompt_text or "").lower()
        value = None
        if env_key == "desert":
            if "which two" in question or str(evac_round) == "2":
                value = 2
            elif "which one" in question or "which casualty" in question or str(evac_round) == "1":
                value = 1
        elif env_key == "urban":
            if "which three" in question or str(evac_round) == "1":
                value = 1

        if value is None:
            value = normalize_optional_int(evac_round) if evac_round not in (None, "") else 1

        for patient_name in patient_ids:
            if not is_valid_patient(patient_name):
                continue
            if patient_name not in evac_value_by_patient:
                evac_value_by_patient[patient_name] = value
            else:
                try:
                    evac_value_by_patient[patient_name] = min(evac_value_by_patient[patient_name], value)
                except TypeError:
                    evac_value_by_patient[patient_name] = value

    last_prompt_by_round = {}
    for action in _iter_action_items(sim_json):
        action_type = str(action.get("actionType") or action.get("action_type") or "").strip().lower()
        evac_round = action.get("evacRound") or action.get("evac_round")
        question = str(action.get("question") or "")
        if action_type == "evacprompt" or "evacuate" in question.lower():
            last_prompt_by_round[str(evac_round or "")] = question
            continue
        if action_type in {"evacselection", "evac_selection"}:
            patient_ids = _split_patient_ids(
                action.get("evacPatientIds")
                or action.get("evacPatientIDs")
                or action.get("evac_patient_ids")
                or action.get("EvacPatientIds")
            )
            prompt = last_prompt_by_round.get(str(evac_round or ""), "")
            apply_selection(patient_ids, prompt, evac_round)

    # CSV fallback for older/raw logs or if actionList was unavailable.
    last_prompt_by_round = {}
    for row in csv_rows:
        event_name = str(row.get("EventName") or "").strip().upper()
        evac_round = row.get("EvacRound")
        question = str(row.get("QuestionPrompt") or row.get("NarrativeDescription") or "")
        if event_name == "EVAC_PROMPT":
            last_prompt_by_round[str(evac_round or "")] = question
        elif event_name == "EVAC_SELECTION":
            patient_ids = _split_patient_ids(row.get("EvacPatientIds") or row.get("EvacPatientId"))
            prompt = last_prompt_by_round.get(str(evac_round or ""), "")
            apply_selection(patient_ids, prompt, evac_round)

    return evac_value_by_patient


def derive_salt_categories(csv_rows, sim_json):
    """Build a reusable patient -> SALT-category mapping from JSON with CSV fallback."""
    salt = {}

    for patient_def in _iter_patient_definitions(sim_json or {}):
        patient = _extract_patient_name_from_definition(patient_def)
        salt_value = (
            patient_def.get("salt_category")
            or patient_def.get("saltCategory")
            or patient_def.get("salt")
            or patient_def.get("triageSort")
        )
        if patient and salt_value:
            salt[patient] = str(salt_value).strip().lower()

    for row in csv_rows:
        if row.get("EventName") != "PATIENT_RECORD":
            continue
        patient = clean_patient_name(row.get("PatientID", ""))
        salt_value = row.get("PatientTriageSort")
        if patient and salt_value and patient not in salt:
            salt[patient] = str(salt_value).strip().lower()

    return salt


def compute_salt_errors(csv_rows, salt_categories):
    """Return reusable SALT mismatches between recorded patient rows and JSON truth.

    When the updated logs include both JSON salt_category and CSV
    PatientTriageSort, this gives a small validation map of mismatches.  An
    empty dict means no mismatches were found or there was nothing to compare.
    """
    errors = {}
    for row in csv_rows:
        if row.get("EventName") != "PATIENT_RECORD":
            continue
        patient = clean_patient_name(row.get("PatientID", ""))
        observed = str(row.get("PatientTriageSort") or "").strip().lower()
        expected = str(salt_categories.get(patient) or "").strip().lower()
        if patient and observed and expected and observed != expected:
            errors[patient] = {"expected": expected, "observed": observed}
    return errors


def extract_month_year_label(*texts):
    """Extract short and pretty month-year labels from free text."""
    combined = " ".join(str(t or "") for t in texts)
    pattern = re.compile(
        r"\b("
        r"january|jan|february|feb|march|mar|april|apr|may|june|jun|"
        r"july|jul|august|aug|september|sept|sep|october|oct|"
        r"november|nov|december|dec"
        r")\s+(\d{4})\b",
        re.IGNORECASE,
    )

    match = pattern.search(combined)
    if not match:
        return None, None

    month_raw = match.group(1).lower()
    year = match.group(2)

    normalized = {
        "jan": "january",
        "feb": "february",
        "mar": "march",
        "apr": "april",
        "jun": "june",
        "jul": "july",
        "aug": "august",
        "sep": "september",
        "sept": "september",
        "oct": "october",
        "nov": "november",
        "dec": "december",
    }.get(month_raw, month_raw)

    short_month = MONTH_MAP[normalized]
    pretty_month = short_month.capitalize()
    return f"{short_month}{year}", f"{pretty_month}{year}"


# ============================================================
# METADATA EXTRACTION
# ============================================================

# Fields extracted:
# - pid
# - env
# - scenario_id
# - openWorld
def extract_run_metadata(sim_json, filename):
    """Extract top-level run metadata from the JSON and filename."""
    pid = extract_pid_from_filename(filename)

    config = sim_json.get("configData", {})
    narrative = config.get("narrative", {})
    scenario_data = config.get("scenarioData", {})

    scene = str(config.get("scene", ""))
    narrative_desc = str(narrative.get("narrativeDescription", ""))
    scenario_name = str(scenario_data.get("name", ""))
    bucket = str(config.get("CACIUploadToS3Bucket", ""))

    text_blob = " ".join([scene, narrative_desc, scenario_name, bucket]).lower()
    open_world = "ow" in text_blob or "open world" in text_blob

    terrain = "unknown"
    if "desert" in text_blob:
        terrain = "desert"
    elif "urban" in text_blob:
        terrain = "urban"

    short_label, pretty_label = extract_month_year_label(
        narrative_desc, bucket, scenario_name
    )

    if open_world and terrain != "unknown":
        env = f"{short_label}-{terrain}-openworld" if short_label else f"{terrain}-openworld"
    elif terrain != "unknown":
        env = terrain
    else:
        env = "unknown"

    if open_world and terrain != "unknown":
        scenario_id = f"{pretty_label}-OW_{terrain}" if pretty_label else f"OW_{terrain}"
    else:
        scenario_id = "unknown"

    eval_metadata = extract_eval_metadata(sim_json)
    patient_map_shown = extract_patient_map_shown(sim_json)

    return {
        "pid": pid,
        "env": env,
        "scenario_id": scenario_id,
        "openWorld": open_world,
        "evalNumber": eval_metadata.get("evalNumber"),
        "evalName": eval_metadata.get("evalName"),
        "patientMapShown": patient_map_shown,
    }


# ============================================================
# EVENT METRICS
# ============================================================

def compute_triage_time_seconds(csv_rows):
    """Compute overall triage time from elapsed time values."""
    if len(csv_rows) <= 1:
        return 0.0

    try:
        start = safe_float(csv_rows[0].get("ElapsedTime", 0))
        end = safe_float(csv_rows[-2].get("ElapsedTime", 0))
        return max(0.0, (end - start) / 1000.0)
    except Exception:
        return 0.0


def compute_assessment_metrics(csv_rows):
    """Count assessment events and break them out by patient."""
    count = 0
    last_done = {}
    per_patient = {}

    for row in csv_rows:
        ev = row.get("EventName")
        if ev not in ASSESSMENT_EVENTS:
            continue

        ts_sec = timestamp_to_seconds(row.get("Timestamp"))
        if ts_sec is None:
            continue

        if ev not in last_done or (ts_sec - last_done[ev]) > 5:
            last_done[ev] = ts_sec
            count += 1

            patient = clean_patient_name(row.get("PatientID", ""))
            if is_valid_patient(patient):
                per_patient[patient] = per_patient.get(patient, 0) + 1

    return {"count": count, "per_patient": per_patient}


def compute_treatment_metrics(csv_rows):
    """Count tool applications and break them out by patient."""
    count = 0
    per_patient = {}

    for row in csv_rows:
        if row.get("EventName") != "TOOL_APPLIED":
            continue

        tool = str(row.get("ToolType", "") or "")
        if "Pulse Oximeter" in tool:
            continue

        count += 1
        patient = clean_patient_name(row.get("PatientID", ""))
        if is_valid_patient(patient):
            per_patient[patient] = per_patient.get(patient, 0) + 1

    return {"count": count, "per_patient": per_patient}


# Fields extracted:
# - Triage_time
# - Assess_total
# - Treat_total
def extract_event_totals(csv_rows, env):
    """Build the eventTotals section using CSV-derived aggregate counts."""
    prefix = build_env_prefix(env)
    assessments = compute_assessment_metrics(csv_rows)
    treatments = compute_treatment_metrics(csv_rows)

    return {
        f"{prefix}Triage_time": compute_triage_time_seconds(csv_rows),
        f"{prefix}Assess_total": assessments["count"],
        f"{prefix}Treat_total": treatments["count"],
    }


# ============================================================
# PATIENT INTERACTION LOGIC
# ============================================================

def compute_patient_engagement(csv_rows):
    """Compute patient engagement counts and order."""
    engagement_order = []
    treated = []

    for row in csv_rows:
        ev = row.get("EventName")
        if ev not in ENGAGEMENT_EVENTS:
            continue

        patient = clean_patient_name(row.get("PatientID", ""))
        if not is_valid_patient(patient):
            continue

        engagement_order.append(patient)
        if ev == "TOOL_APPLIED":
            treated.append(patient)

    simple_order = []
    for patient in engagement_order:
        if simple_order and patient == simple_order[-1]:
            continue
        simple_order.append(patient)

    return {
        "engaged": len(set(engagement_order)),
        "treated": len(set(treated)),
        "order": simple_order,
    }


# Fields extracted:
# - patient_interactions
# - interaction_time
# - interaction_visits
# - patient_order
def compute_patient_interactions(csv_rows):
    """Build patient interaction timing and visit summaries."""
    raw_interactions = {}
    cur_p = None
    start_time = 0.0
    last_time = 0.0

    for row in csv_rows:
        ev = row.get("EventName")
        if ev not in ENGAGEMENT_EVENTS:
            continue

        patient = clean_patient_name(row.get("PatientID", ""))
        if not is_valid_patient(patient):
            continue

        try:
            t = float(row.get("ElapsedTime", 0))
        except Exception:
            continue

        raw_interactions.setdefault(patient, [])

        if cur_p is None:
            cur_p = patient
            start_time = last_time if last_time != 0 else t
            last_time = t
            continue

        if cur_p != patient:
            raw_interactions[cur_p].append((start_time, last_time if last_time != 0 else t))
            cur_p = patient
            start_time = t
            last_time = t
        else:
            last_time = t

    if cur_p is not None:
        raw_interactions.setdefault(cur_p, [])
        raw_interactions[cur_p].append((start_time, last_time))

    total_time_ms = 0.0
    per_patient_seconds = {}
    patient_interactions = {}
    interaction_time = {}
    interaction_visits = {}

    ordered_patients = []
    for row in csv_rows:
        ev = row.get("EventName")
        if ev not in ENGAGEMENT_EVENTS:
            continue

        patient = clean_patient_name(row.get("PatientID", ""))
        if not is_valid_patient(patient):
            continue

        if not ordered_patients or ordered_patients[-1] != patient:
            ordered_patients.append(patient)

    patient_visit_indices = {}
    for idx, patient in enumerate(ordered_patients):
        patient_visit_indices.setdefault(patient, []).append(idx)

    for patient, segs in raw_interactions.items():
        patient_ms = 0.0
        clean_segments = []

        for start, end in segs:
            start_ms = float(start)
            end_ms = max(float(end), float(start))
            clean_segments.append([start_ms, end_ms])
            patient_ms += max(0.0, end_ms - start_ms)

        total_seconds = round(patient_ms / 1000.0, 3)
        total_time_ms += patient_ms

        per_patient_seconds[patient] = total_seconds
        interaction_time[patient] = total_seconds
        interaction_visits[patient] = len(clean_segments)
        patient_interactions[patient] = {
            "total_time": total_seconds,
            "indices_visited": patient_visit_indices.get(patient, []),
            "times_visited": len(clean_segments),
            "all_data": clean_segments,
        }

    patient_order = []
    for patient in ordered_patients:
        if patient not in patient_order:
            patient_order.append(patient)

    return {
        "interactions": per_patient_seconds,
        "total": total_time_ms / 1000.0,
        "patient_interactions": patient_interactions,
        "interaction_time": interaction_time,
        "interaction_visits": interaction_visits,
        "patient_order": patient_order,
    }


def compute_patients_in_order(csv_rows, engagement_order):
    """Determine the patient breakout order."""
    patients_in_order = []

    for row in csv_rows:
        if row.get("EventName") == "PATIENT_RECORD":
            patient = clean_patient_name(row.get("PatientID", ""))
            if is_valid_patient(patient) and patient not in patients_in_order:
                patients_in_order.append(patient)

    if not patients_in_order:
        for patient in engagement_order:
            if patient not in patients_in_order:
                patients_in_order.append(patient)

    return patients_in_order


# ============================================================
# TRIAGE / TAG LOGIC
# ============================================================

# Fields extracted:
# - PatientN_triage_truth
def derive_expected_tag_color(csv_rows):
    """Build expected tag colors from patient record rows."""
    expected_tag_color = {}

    for row in csv_rows:
        if row.get("EventName") != "PATIENT_RECORD":
            continue

        patient = clean_patient_name(row.get("PatientID", ""))
        triage_level = str(row.get("PatientTriageLevel", "")).strip().upper()

        if patient and triage_level in TRIAGE_LEVEL_TO_TAG_COLOR:
            expected_tag_color[patient] = TRIAGE_LEVEL_TO_TAG_COLOR[triage_level]

    return expected_tag_color


def _iter_patient_definitions(sim_json):
    """Yield patient definitions from known JSON locations."""
    if not isinstance(sim_json, dict):
        return

    candidate_lists = [
        sim_json.get("patientDataList"),
        sim_json.get("patientList"),
        sim_json.get("patients"),
        sim_json.get("configData", {}).get("patientDataList"),
        sim_json.get("configData", {}).get("patientList"),
        sim_json.get("configData", {}).get("patients"),
    ]

    scenario_data = sim_json.get("configData", {}).get("scenarioData", {})
    candidate_lists.extend(
        [
            scenario_data.get("patientDataList"),
            scenario_data.get("patientList"),
            scenario_data.get("patients"),
        ]
    )

    seen_ids = set()
    for candidate in candidate_lists:
        if not isinstance(candidate, list):
            continue
        for patient_def in candidate:
            if not isinstance(patient_def, dict):
                continue
            obj_id = id(patient_def)
            if obj_id in seen_ids:
                continue
            seen_ids.add(obj_id)
            yield patient_def


def _extract_patient_name_from_definition(patient_def):
    """Return the best patient identifier from a JSON patient definition."""
    for key in ("name", "patientId", "patientID", "id", "patientName"):
        value = patient_def.get(key)
        patient = clean_patient_name(value)
        if is_valid_patient(patient):
            return patient
    return ""


def _as_clean_list(value):
    """Normalize scalar/list values into a list of non-empty strings."""
    if value is None:
        return []
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = [value]
    return [str(item).strip() for item in raw_values if str(item).strip()]


def normalize_treatment_token(value):
    """Normalize treatment/procedure strings for cross-source comparisons."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


# Fields extracted:
# - PatientN_required_injuries
def derive_required_injuries_and_procs(csv_rows, sim_json=None):
    """Build required injuries and their required procedures from JSON, with CSV fallback."""
    required_injuries = {}
    required_proc_for_injury = {}

    for patient_def in _iter_patient_definitions(sim_json or {}):
        patient = _extract_patient_name_from_definition(patient_def)
        if not patient:
            continue

        for injury_def in patient_def.get("injuries", []) or []:
            if not isinstance(injury_def, dict):
                continue
            injury = str(
                injury_def.get("type")
                or injury_def.get("name")
                or injury_def.get("injuryName")
                or ""
            ).strip()
            proc = str(
                injury_def.get("requiredProcedure")
                or injury_def.get("required_procedure")
                or injury_def.get("procedure")
                or ""
            ).strip()

            if patient and injury:
                required_injuries.setdefault(patient, [])
                if injury not in required_injuries[patient]:
                    required_injuries[patient].append(injury)
                if proc:
                    required_proc_for_injury[(patient, injury)] = proc

    for row in csv_rows:
        if row.get("EventName") != "INJURY_RECORD":
            continue

        patient = clean_patient_name(row.get("PatientID", ""))
        injury = str(row.get("InjuryName", "")).strip()
        proc = str(row.get("InjuryRequiredProcedure", "")).strip()

        if patient and injury:
            required_injuries.setdefault(patient, [])
            if injury not in required_injuries[patient]:
                required_injuries[patient].append(injury)
            if proc and (patient, injury) not in required_proc_for_injury:
                required_proc_for_injury[(patient, injury)] = proc

    return required_injuries, required_proc_for_injury


def derive_supplemental_procedures(sim_json):
    """Build a per-patient supplemental procedure map from JSON patient definitions."""
    supplemental_map = {}

    for patient_def in _iter_patient_definitions(sim_json or {}):
        patient = _extract_patient_name_from_definition(patient_def)
        if not patient:
            continue

        procedures = _as_clean_list(
            patient_def.get("supplementalProcedures")
            or patient_def.get("supplemental_procedures")
            or patient_def.get("approvedSupplementalProcedures")
        )
        supplemental_map[patient] = procedures

    return supplemental_map


# ============================================================
# TREATMENT METRICS
# ============================================================

# Fields extracted:
# - Treat_hits_required
# - Treat_false_alarms_required
# - Treat_repeat_hits_required
# - Treat_repeat_false_alarms_required
# - PatientN_treat_hits_required
# - PatientN_treat_false_alarms_required
# - PatientN_treat_repeat_hits_required
# - PatientN_treat_repeat_false_alarms_required
def compute_treatment_submetrics_required(csv_rows, required_injuries):
    """Compute required-only treatment submetrics."""
    to_complete = {patient: list(injuries)[:] for patient, injuries in required_injuries.items()}
    hits = {}
    false_alarms = {}
    repeat_hits = {}
    repeat_false_alarms = {}
    false_alarm_tracker = {}

    for row in csv_rows:
        if row.get("EventName") != "INJURY_TREATED":
            continue

        patient = clean_patient_name(row.get("PatientID", ""))
        if not is_valid_patient(patient):
            continue

        injury = str(row.get("InjuryName", "")).strip()
        completed = safe_bool_from_csv(row.get("InjuryTreatmentComplete"))
        if not completed:
            continue

        patient_required = required_injuries.get(patient, [])

        if patient_required:
            if injury in patient_required:
                if patient in to_complete and injury in to_complete[patient]:
                    to_complete[patient].remove(injury)
                    hits[patient] = hits.get(patient, 0) + 1
                    if not to_complete[patient]:
                        del to_complete[patient]
                else:
                    repeat_hits[patient] = repeat_hits.get(patient, 0) + 1
            else:
                if false_alarm_tracker.get(patient, {}).get(injury, 0) > 0:
                    repeat_false_alarms[patient] = repeat_false_alarms.get(patient, 0) + 1
                else:
                    false_alarms[patient] = false_alarms.get(patient, 0) + 1
                false_alarm_tracker.setdefault(patient, {})
                false_alarm_tracker[patient][injury] = false_alarm_tracker[patient].get(injury, 0) + 1
        else:
            if false_alarm_tracker.get(patient, {}).get(injury, 0) > 0:
                repeat_false_alarms[patient] = repeat_false_alarms.get(patient, 0) + 1
            else:
                false_alarms[patient] = false_alarms.get(patient, 0) + 1
            false_alarm_tracker.setdefault(patient, {})
            false_alarm_tracker[patient][injury] = false_alarm_tracker[patient].get(injury, 0) + 1

    return {
        "total_hits": sum(hits.values()),
        "total_false_alarms": sum(false_alarms.values()),
        "total_repeat_hits": sum(repeat_hits.values()),
        "total_repeat_false_alarms": sum(repeat_false_alarms.values()),
        "per_patient_hits": hits,
        "per_patient_false_alarms": false_alarms,
        "per_patient_repeat_hits": repeat_hits,
        "per_patient_repeat_false_alarms": repeat_false_alarms,
    }


def _procedure_is_supplemental(tool, patient, supplemental_map):
    """Return True when a tool matches one of the patient's supplemental procedures."""
    normalized_tool = normalize_treatment_token(tool)
    return any(
        normalize_treatment_token(proc) == normalized_tool
        for proc in supplemental_map.get(patient, [])
    )


# Fields extracted:
# - Treat_hits_w_supp
# - Treat_false_alarms_w_supp
# - Treat_repeat_hits_w_supp
# - Treat_repeat_false_alarms_w_supp
# - PatientN_treat_hits_w_supp
# - PatientN_treat_false_alarms_w_supp
# - PatientN_treat_repeat_hits_w_supp
# - PatientN_treat_repeat_false_alarms_w_supp
def compute_treatment_submetrics_w_supp(csv_rows, required_injuries, supplemental_map):
    """Compute required + supplemental treatment submetrics using reusable JSON metadata.

    This mirrors the April probe matcher logic:
    - completed required injuries count as hits the first time and repeat hits after that
    - supplemental TOOL_APPLIED rows count as hits/repeat hits
    - non-required/non-supplemental treatments count as false alarms/repeat false alarms
    - the TOOL_APPLIED row paired with a just-completed required injury is not double-counted
    """
    to_complete = {patient: list(injuries)[:] for patient, injuries in required_injuries.items()}
    hits = {}
    false_alarms = {}
    repeat_hits = {}
    repeat_false_alarms = {}
    supplemental_tracker = {}
    false_alarm_tracker = {}
    just_completed = None

    for row in csv_rows:
        event_name = row.get("EventName")

        if event_name == "INJURY_TREATED":
            patient = clean_patient_name(row.get("PatientID", ""))
            if not is_valid_patient(patient):
                continue

            injury = str(row.get("InjuryName", "")).strip()
            completed = safe_bool_from_csv(row.get("InjuryTreatmentComplete"))
            if not completed:
                continue

            patient_required = required_injuries.get(patient, [])
            if patient_required:
                if injury in patient_required:
                    if patient in to_complete and injury in to_complete[patient]:
                        to_complete[patient].remove(injury)
                        just_completed = patient
                        hits[patient] = hits.get(patient, 0) + 1
                        if not to_complete[patient]:
                            del to_complete[patient]
                    else:
                        repeat_hits[patient] = repeat_hits.get(patient, 0) + 1
                else:
                    if false_alarm_tracker.get(patient, {}).get(injury, 0) > 0:
                        repeat_false_alarms[patient] = repeat_false_alarms.get(patient, 0) + 1
                    else:
                        false_alarms[patient] = false_alarms.get(patient, 0) + 1
                    false_alarm_tracker.setdefault(patient, {})
                    false_alarm_tracker[patient][injury] = false_alarm_tracker[patient].get(injury, 0) + 1
            else:
                if false_alarm_tracker.get(patient, {}).get(injury, 0) > 0:
                    repeat_false_alarms[patient] = repeat_false_alarms.get(patient, 0) + 1
                else:
                    false_alarms[patient] = false_alarms.get(patient, 0) + 1
                false_alarm_tracker.setdefault(patient, {})
                false_alarm_tracker[patient][injury] = false_alarm_tracker[patient].get(injury, 0) + 1

        if event_name == "TOOL_APPLIED":
            patient = clean_patient_name(row.get("PatientID", ""))
            if not is_valid_patient(patient):
                just_completed = None
                continue

            tool = str(row.get("ToolType", "") or "").strip()
            if "Pulse Oximeter" in tool:
                just_completed = None
                continue

            if _procedure_is_supplemental(tool, patient, supplemental_map):
                if supplemental_tracker.get(patient, {}).get(tool, 0) > 0:
                    repeat_hits[patient] = repeat_hits.get(patient, 0) + 1
                else:
                    hits[patient] = hits.get(patient, 0) + 1
                supplemental_tracker.setdefault(patient, {})
                supplemental_tracker[patient][tool] = supplemental_tracker[patient].get(tool, 0) + 1
            else:
                if patient != just_completed:
                    if false_alarm_tracker.get(patient, {}).get(tool, 0) > 0:
                        repeat_false_alarms[patient] = repeat_false_alarms.get(patient, 0) + 1
                    else:
                        false_alarms[patient] = false_alarms.get(patient, 0) + 1
                    false_alarm_tracker.setdefault(patient, {})
                    false_alarm_tracker[patient][tool] = false_alarm_tracker[patient].get(tool, 0) + 1
            just_completed = None

    return {
        "total_hits": sum(hits.values()),
        "total_false_alarms": sum(false_alarms.values()),
        "total_repeat_hits": sum(repeat_hits.values()),
        "total_repeat_false_alarms": sum(repeat_false_alarms.values()),
        "per_patient_hits": hits,
        "per_patient_false_alarms": false_alarms,
        "per_patient_repeat_hits": repeat_hits,
        "per_patient_repeat_false_alarms": repeat_false_alarms,
    }


# Fields extracted:
# - triage_performance
def compute_triage_performance_w_supp(csv_rows, required_injuries, supplemental_map):
    """Compute supplemental-aware triage performance using April probe matcher logic."""
    to_complete = {patient: list(injuries)[:] for patient, injuries in required_injuries.items()}

    supplemental_points = {}
    total_tools_applied = 0
    correct_tools_applied = 0
    misses = 0

    for row in csv_rows:
        event_name = row.get("EventName")

        if event_name == "INJURY_TREATED":
            patient = clean_patient_name(row.get("PatientID", ""))
            if not is_valid_patient(patient):
                continue

            injury = str(row.get("InjuryName", "")).strip()
            completed = safe_bool_from_csv(row.get("InjuryTreatmentComplete"))
            if not completed:
                continue

            if patient in to_complete and injury in to_complete[patient]:
                to_complete[patient].remove(injury)
                correct_tools_applied += 1
                if not to_complete[patient]:
                    del to_complete[patient]

        if event_name == "TOOL_APPLIED":
            total_tools_applied += 1
            patient = clean_patient_name(row.get("PatientID", ""))
            tool = str(row.get("ToolType", "") or "").strip()
            if not is_valid_patient(patient):
                continue

            if _procedure_is_supplemental(tool, patient, supplemental_map):
                supplemental_points[patient] = supplemental_points.get(patient, 0) + 1

    for remaining_injuries in to_complete.values():
        misses += len(remaining_injuries)

    for patient, supp_count in supplemental_points.items():
        if patient not in to_complete:
            correct_tools_applied += supp_count

    return (correct_tools_applied / max(1, total_tools_applied + misses)) * 100


# Fields extracted:
# - tag_colors
# - PatientN_tag
def compute_last_applied_tags(csv_rows):
    """Return the last applied tag per patient."""
    tags_applied = {}

    for row in csv_rows:
        if row.get("EventName") != "TAG_APPLIED":
            continue

        patient = clean_patient_name(row.get("PatientID", ""))
        tag = str(row.get("TagType", "")).strip().lower()
        if patient:
            tags_applied[patient] = tag

    return tags_applied


def normalize_tag_color(tag):
    """Normalize tag color aliases."""
    tag = str(tag or "").strip().lower()
    if tag == "yellow_orange":
        return "yellow"
    if tag == "green_blue":
        return "green"
    return tag


# Fields extracted:
# - tag_distribution_red
# - tag_distribution_yellow
# - tag_distribution_green
# - tag_distribution_gray
# - tag_distribution_black
# - percent_correct_per_patient
def compute_tag_distribution(csv_rows, expected_tag_color):
    """Compute per-patient tag distributions and percent correct."""
    counts_by_patient = {}

    for row in csv_rows:
        if row.get("EventName") != "TAG_APPLIED":
            continue

        patient = clean_patient_name(row.get("PatientID", ""))
        if not is_valid_patient(patient):
            continue

        tag = normalize_tag_color(str(row.get("TagType", "")).strip().lower())
        if tag not in {"red", "yellow", "green", "gray", "black"}:
            continue

        counts_by_patient.setdefault(
            patient,
            {"red": 0, "yellow": 0, "green": 0, "gray": 0, "black": 0},
        )
        counts_by_patient[patient][tag] += 1

    result = {
        "tag_distribution_red": {},
        "tag_distribution_yellow": {},
        "tag_distribution_green": {},
        "tag_distribution_gray": {},
        "tag_distribution_black": {},
        "percent_correct_per_patient": {},
    }

    for patient, counts in counts_by_patient.items():
        total_tags = sum(counts.values())
        expected = normalize_tag_color(expected_tag_color.get(patient))
        correct_tags = counts.get(expected, 0) if expected else 0

        result["tag_distribution_red"][patient] = counts["red"]
        result["tag_distribution_yellow"][patient] = counts["yellow"]
        result["tag_distribution_green"][patient] = counts["green"]
        result["tag_distribution_gray"][patient] = counts["gray"]
        result["tag_distribution_black"][patient] = counts["black"]
        result["percent_correct_per_patient"][patient] = round(correct_tags / max(1, total_tags), 4)

    return result


# Fields extracted:
# - correct_tags_total
# - correct_tags_correct
# - correct_tags_over
# - correct_tags_under
# - correct_tags_critical
def compute_correct_tag_breakdown(expected_tag_color, tags_applied):
    """Compute the flattened correct tag summary fields."""
    correct = 0
    total = 0
    over_triage = 0
    under_triage = 0
    critical_triage = 0

    for patient, applied_raw in tags_applied.items():
        expected = expected_tag_color.get(patient)
        if expected is None:
            continue

        applied = normalize_tag_color(applied_raw)
        expected = normalize_tag_color(expected)

        if applied == expected:
            correct += 1
        else:
            if expected == "black":
                over_triage += 1
            elif applied == "black":
                critical_triage += 1
            elif expected == "gray":
                over_triage += 1
            elif applied == "gray":
                critical_triage += 1
            elif expected == "red":
                under_triage += 1
            elif applied == "red":
                over_triage += 1
            elif expected == "yellow":
                under_triage += 1
            elif applied == "yellow":
                over_triage += 1

        total += 1

    return {
        "correct_tags_total": total,
        "correct_tags_correct": correct,
        "correct_tags_over": over_triage,
        "correct_tags_under": under_triage,
        "correct_tags_critical": critical_triage,
    }


# Fields extracted:
# - Tag_ACC
# - Tag_Expectant
def compute_tag_metrics(expected_tag_color, tags_applied):
    """Compute aggregate tag metrics."""
    if not expected_tag_color:
        tag_acc = None
    else:
        correct = 0
        count = 0
        for patient, applied in tags_applied.items():
            expected = expected_tag_color.get(patient)
            if expected is None:
                continue
            count += 1
            if applied == expected:
                correct += 1
        tag_acc = correct / max(1, count) if count > 0 else None

    expectant_patients = [p for p, col in expected_tag_color.items() if col == "gray"]
    tag_expectant = None
    if expectant_patients:
        tag_expectant = "Yes" if any(tags_applied.get(p) == "gray" for p in expectant_patients) else "No"

    return {"tag_acc": tag_acc, "tag_expectant": tag_expectant}


# ============================================================
# HEMORRHAGE CONTROL
# ============================================================

# Fields extracted:
# - Hemorrhage control
# - Hemorrhage control_time
# - missed_hemorrhage_control
def compute_hemorrhage_control(csv_rows, required_proc_for_injury):
    """Compute hemorrhage control completion, time, and missed count."""
    to_complete = {}

    for (patient, injury), proc in required_proc_for_injury.items():
        if proc in HEMORRHAGE_CONTROL_PROCS:
            to_complete.setdefault(patient, set()).add(injury)

    start_time_sec = None
    end_time_sec = None

    for row in csv_rows:
        ev = row.get("EventName")

        if ev == "SESSION_START":
            ts = row.get("Timestamp")
            if ts:
                start_time_sec = timestamp_to_seconds(ts)

        if ev == "INJURY_TREATED":
            patient = clean_patient_name(row.get("PatientID", ""))
            injury = str(row.get("InjuryName", "")).strip()
            completed = safe_bool_from_csv(row.get("InjuryTreatmentComplete"))

            if not completed:
                continue

            if patient in to_complete and injury in to_complete[patient]:
                to_complete[patient].remove(injury)
                ts = row.get("Timestamp")
                if ts:
                    end_time_sec = timestamp_to_seconds(ts)

                if not to_complete[patient]:
                    del to_complete[patient]

    completed = 1 if not to_complete else 0
    time_to = None
    if completed == 1 and start_time_sec is not None and end_time_sec is not None:
        time_to = end_time_sec - start_time_sec

    return {
        "hemorrhage_control": completed,
        "hemorrhage_control_time": time_to,
        "missed_hemorrhage_control": sum(len(v) for v in to_complete.values()),
    }


# Fields extracted:
# - patient_hc_time
def compute_patient_hc_time(csv_rows, patient_interactions, required_proc_for_injury):
    """Compute per-patient hemorrhage control timing within visit segments."""
    times_controlled = {}

    for row in csv_rows:
        if row.get("EventName") != "INJURY_TREATED":
            continue

        patient = clean_patient_name(row.get("PatientID", ""))
        injury = str(row.get("InjuryName", "")).strip()
        completed = safe_bool_from_csv(row.get("InjuryTreatmentComplete"))
        if not completed:
            continue

        req_proc = required_proc_for_injury.get((patient, injury))
        if req_proc not in HEMORRHAGE_CONTROL_PROCS:
            continue

        tx = safe_float(row.get("ElapsedTime"), 0.0)
        times_controlled.setdefault(patient, []).append(
            {"procedure": [patient, req_proc, injury], "time": tx}
        )

    control_times = {}

    for patient, controlled_list in times_controlled.items():
        interaction_times = patient_interactions.get(patient, {}).get("all_data", [])
        last_t2 = 0.0
        last_t1 = 0.0

        for controlled in controlled_list:
            tx = float(controlled["time"])
            for t1, t2 in interaction_times:
                if t1 == last_t2:
                    t1 = last_t1
                last_t1 = t1
                last_t2 = t2

                if tx >= t1 and tx <= t2:
                    control_times.setdefault(patient, []).append(
                        {
                            "procedure": controlled["procedure"],
                            "time": round((tx - t1) / 1000.0, 3),
                        }
                    )
                    break

    return control_times


def compute_patient_averages(csv_rows, assessments, treatments, triage_times):
    """Compute aggregate patient-based averages."""
    engaged_counts = compute_patient_engagement(csv_rows)
    patients_engaged = engaged_counts["engaged"]
    patients_treated = engaged_counts["treated"]
    patient_order_engaged = engaged_counts["order"]

    engagement_times = list({p: patient_order_engaged.count(p) for p in set(patient_order_engaged)}.values())

    return {
        "engage_patient": sum(engagement_times) / max(1, len(engagement_times)),
        "assess_patient": assessments["count"] / max(1, patients_engaged),
        "treat_patient": treatments["count"] / max(1, patients_treated),
        "triage_time_patient": triage_times["total"] / max(1, patients_engaged),
        "patients_engaged": patients_engaged,
        "patient_order_engaged": patient_order_engaged,
    }


# ============================================================
# MOVEMENT / DRAG LOGIC
# ============================================================

def parse_vec3(pos_str):
    """Parse a string vector into a 3-tuple."""
    if not pos_str:
        return None
    s = str(pos_str).strip().strip("()")
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 3:
        return None
    try:
        return tuple(float(p) for p in parts)
    except Exception:
        return None


def vec3_distance(a, b):
    """Compute Euclidean distance between two 3D points."""
    if not a or not b:
        return 0.0
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    dz = a[2] - b[2]
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def is_zero_vec3(pos):
    """Return True when a parsed vector is the Unity/default zero position."""
    if not pos:
        return True
    return all(abs(value) < 1e-9 for value in pos)


def format_vec3(pos):
    """Format a parsed vector for stable JSON output."""
    if not pos:
        return None
    return f"({round(pos[0], 3)}, {round(pos[1], 3)}, {round(pos[2], 3)})"


def extract_patient_start_locations(sim_json):
    """Return patient starting positions from configData.patientDataList.

    Keys are normalized simulation patient names, such as "US Military 1".
    Values are parsed (x, y, z) tuples from positionAngle.position.
    """
    start_locations = {}
    patient_data_list = (
        sim_json.get("configData", {}).get("patientDataList")
        or sim_json.get("patientDataList")
        or []
    )

    for patient_data in patient_data_list:
        if not isinstance(patient_data, dict):
            continue
        patient_name = clean_patient_name(patient_data.get("name", ""))
        if not patient_name or not is_valid_patient(patient_name):
            continue

        position = (
            patient_data.get("positionAngle", {})
            .get("position", {})
        )
        try:
            start_locations[patient_name] = (
                float(position.get("x", 0.0)),
                float(position.get("y", 0.0)),
                float(position.get("z", 0.0)),
            )
        except Exception:
            continue

    return start_locations


# Fields extracted:
# - PatientN_dragged
# - PatientN_drag_times
# - PatientN_total_drag_time
# - PatientN_drag_start_location
# - PatientN_drag_end_location
def compute_drag_metrics(csv_rows, sim_json=None, min_drag_distance=1.0):
    """Return drag metrics for meaningful patient drags.

    Drag duration is calculated from DRAG_START to the matching DRAG_STOP for the
    same patient, then summed per patient. A drag only counts if the start/stop
    positions are more than min_drag_distance apart, matching the existing
    PatientN_dragged and PatientN_drag_times behavior.

    For location output, only one start and end location is returned per patient:
    - drag_start_location is the patient's original scenario position from JSON
      when available, falling back to the first meaningful DragStartPosition.
    - drag_end_location is the final meaningful DragStopPosition found in the CSV.
    """
    dragged_patients = set()
    drag_times_by_patient = {}
    total_drag_time_by_patient = {}
    drag_start_location_by_patient = {}
    drag_end_location_by_patient = {}
    first_meaningful_drag_start_by_patient = {}
    active_drag_start = {}

    patient_start_locations = extract_patient_start_locations(sim_json or {})

    for row in csv_rows:
        ev = row.get("EventName")
        patient = clean_patient_name(row.get("PatientID", ""))

        if not patient or not is_valid_patient(patient):
            continue

        if ev == "DRAG_START":
            start_elapsed_seconds = safe_float(row.get("ElapsedTime", 0)) / 1000.0
            active_drag_start[patient] = {
                "position": parse_vec3(row.get("DragStartPosition", "")),
                "elapsed_seconds": start_elapsed_seconds,
            }
        elif ev == "DRAG_STOP":
            if patient not in active_drag_start:
                continue
            start_data = active_drag_start.pop(patient, None) or {}
            start_pos = start_data.get("position")
            stop_pos = parse_vec3(row.get("DragStopPosition", ""))
            stop_elapsed_seconds = safe_float(row.get("ElapsedTime", 0)) / 1000.0
            start_elapsed_seconds = safe_float(start_data.get("elapsed_seconds", 0.0))

            if is_zero_vec3(stop_pos):
                continue

            if vec3_distance(start_pos, stop_pos) > min_drag_distance:
                drag_duration = max(0.0, stop_elapsed_seconds - start_elapsed_seconds)
                dragged_patients.add(patient)
                drag_times_by_patient.setdefault(patient, []).append(
                    round(start_elapsed_seconds, 3)
                )
                total_drag_time_by_patient[patient] = round(
                    total_drag_time_by_patient.get(patient, 0.0) + drag_duration,
                    3,
                )

                if patient not in first_meaningful_drag_start_by_patient:
                    first_meaningful_drag_start_by_patient[patient] = start_pos
                drag_end_location_by_patient[patient] = stop_pos

    for patient in dragged_patients:
        drag_start_location_by_patient[patient] = (
            patient_start_locations.get(patient)
            or first_meaningful_drag_start_by_patient.get(patient)
        )

    return {
        "dragged_patients": dragged_patients,
        "drag_times_by_patient": drag_times_by_patient,
        "total_drag_time_by_patient": total_drag_time_by_patient,
        "drag_start_location_by_patient": drag_start_location_by_patient,
        "drag_end_location_by_patient": drag_end_location_by_patient,
    }


def compute_dragged_patients(csv_rows, min_drag_distance=1.0):
    """Backward-compatible helper returning only the dragged-patient set."""
    return compute_drag_metrics(csv_rows, min_drag_distance=min_drag_distance)["dragged_patients"]



# ============================================================
# PERSONAL SAFETY PROBE LOGIC
# ============================================================

# Fields extracted:
# - Desert Probe_PS1
# - Desert Probe_PS1_Actions
# - Desert Probe_PS2
# - Desert Probe_PS2_Actions
# - Urban Probe_PS1
# - Urban Probe_PS1_Actions
def normalize_answer_id(value):
    """Normalize sim-provided answerIds into stable lookup keys."""
    raw_value = str(value or "").strip().lower()
    if raw_value in ANSWER_ID_ALIASES:
        return ANSWER_ID_ALIASES[raw_value]

    normalized_value = re.sub(r"[^a-z0-9]+", "_", raw_value)
    normalized_value = re.sub(r"_+", "_", normalized_value).strip("_")
    return ANSWER_ID_ALIASES.get(normalized_value, normalized_value)


def _iter_action_items(sim_json):
    """Yield action dictionaries from known raw and wrapped JSON locations."""
    if not isinstance(sim_json, dict):
        return

    candidate_lists = [
        sim_json.get("actionList"),
        sim_json.get("action_list"),
        sim_json.get("actions"),
        sim_json.get("data", {}).get("actionList") if isinstance(sim_json.get("data"), dict) else None,
        sim_json.get("data", {}).get("action_list") if isinstance(sim_json.get("data"), dict) else None,
        sim_json.get("data", {}).get("actions") if isinstance(sim_json.get("data"), dict) else None,
        sim_json.get("configData", {}).get("actionList") if isinstance(sim_json.get("configData"), dict) else None,
        sim_json.get("configData", {}).get("action_list") if isinstance(sim_json.get("configData"), dict) else None,
        sim_json.get("sessionMetadata", {}).get("actionList") if isinstance(sim_json.get("sessionMetadata"), dict) else None,
    ]

    seen_ids = set()
    for candidate in candidate_lists:
        if not isinstance(candidate, list):
            continue
        for action in candidate:
            if not isinstance(action, dict):
                continue
            obj_id = id(action)
            if obj_id in seen_ids:
                continue
            seen_ids.add(obj_id)
            yield action


def _coerce_string_list(value):
    """Normalize scalar/list fields into a list of non-empty strings."""
    if value is None:
        return []
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = [value]
    return [str(item).strip() for item in raw_values if str(item).strip()]


def get_answer_ids_from_question_action(action):
    """Return normalized answerIds from a structured Question action."""
    answer_ids = []

    for key in ("answerIds", "answerIDs", "answer_ids", "answerids", "answerId", "answerID", "answer_id"):
        answer_ids.extend(_coerce_string_list(action.get(key)))

    # Fallback only if answerIds were not present. This keeps answerIds as the
    # preferred source, but prevents null outputs if a log version only has
    # answerChoice/answer.
    if not answer_ids:
        for choice in get_answer_choices_from_question_action(action):
            answer_ids.append(choice)

    normalized_ids = []
    for answer_id in answer_ids:
        normalized = normalize_answer_id(answer_id)
        if normalized and normalized not in normalized_ids:
            normalized_ids.append(normalized)

    return normalized_ids


def get_answer_choices_from_question_action(action):
    """Return display answer choices for *_Actions output fields."""
    answer_choices = []
    for key in ("answerChoice", "answerChoices", "answer_choice", "answer_choices", "answer"):
        answer_choices.extend(_coerce_string_list(action.get(key)))

    # If there is no display answer text, use the raw answerIds so the Actions
    # field still shows what was recorded instead of remaining null.
    if not answer_choices:
        for key in ("answerIds", "answerIDs", "answer_ids", "answerids", "answerId", "answerID", "answer_id"):
            answer_choices.extend(_coerce_string_list(action.get(key)))

    clean_choices = []
    for choice in answer_choices:
        if choice not in clean_choices:
            clean_choices.append(choice)
    return clean_choices


def _is_question_action(action):
    """Return True when an action appears to represent a question response.

    Current reusable logs record questions as a lifecycle of events:
    QuestionPrompted -> AnswerSelected -> QuestionAnswered.  The final
    QuestionAnswered event is the best scoring source because it contains
    the populated answerIds, while older logs may still use actionType=Question.
    """
    action_type = str(action.get("actionType") or action.get("action_type") or "").strip().lower()
    question_action_types = {
        "question",
        "questionprompted",
        "question_prompted",
        "answerselected",
        "answer_selected",
        "questionanswered",
        "question_answered",
    }
    if action_type in question_action_types:
        return True
    return any(key in action for key in ("questionId", "questionID", "question_id", "question"))


def _question_action_priority(action):
    """Prefer final answered question records over prompt/selection records."""
    action_type = str(action.get("actionType") or action.get("action_type") or "").strip().lower()
    if action_type in {"questionanswered", "question_answered", "question"}:
        return 0
    if action_type in {"answerselected", "answer_selected"}:
        return 1
    if action_type in {"questionprompted", "question_prompted"}:
        return 2
    return 3


def _get_question_id(action):
    """Return a normalized question id such as PS1 or PS2."""
    question_id = str(
        action.get("questionId")
        or action.get("questionID")
        or action.get("question_id")
        or action.get("probeId")
        or action.get("probeID")
        or action.get("probe_id")
        or ""
    ).strip().upper()

    return question_id


def _get_question_type(action):
    """Return a normalized question type/category."""
    value = str(
        action.get("questionType")
        or action.get("question_type")
        or action.get("questionCategory")
        or action.get("question_category")
        or action.get("category")
        or ""
    ).strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def _question_text_matches_ps_key(action, ps_key):
    """Fallback matcher for older/free-text question records."""
    question_text = str(action.get("question") or action.get("questionText") or "").strip().lower()
    if ps_key == "PS1":
        return "warning" in question_text and "remain in place" in question_text
    if ps_key == "PS2":
        return "drones" in question_text and "flew over" in question_text
    return False


def compute_personal_safety_values(sim_json, env):
    """Compute April-style personal-safety probe fields from structured answerIds.

    Scoring prefers answerIds from the final QuestionAnswered record. If an
    older/raw log does not have QuestionAnswered, it falls back to Question or
    AnswerSelected-style records. answerChoice is used for the *_Actions display
    string and only used for scoring as a last-resort fallback when answerIds
    are missing.
    """
    env_lower = str(env or "").lower()
    env_key = "desert" if "desert" in env_lower else "urban" if "urban" in env_lower else None
    if not env_key:
        return {}

    result = {}
    env_config = PERSONAL_SAFETY_CONFIG.get(env_key, {})

    for ps_key, ps_config in env_config.items():
        matching_actions = []

        for action in _iter_action_items(sim_json):
            if not _is_question_action(action):
                continue

            question_id = _get_question_id(action)
            question_type = _get_question_type(action)

            question_id_matches = question_id == ps_key
            question_text_matches = not question_id and _question_text_matches_ps_key(action, ps_key)
            personal_safety_type = question_type in ("", "personal_safety", "personalsafety")

            # Prefer structured PS ids, but do not require questionType because
            # some log versions omit it or vary its naming/capitalization.
            if not ((question_id_matches and personal_safety_type) or question_text_matches):
                continue

            matching_actions.append(action)

        # Use the best available event for this probe. In the current logs,
        # QuestionAnswered contains the populated answerIds. AnswerSelected may
        # only contain the display answerChoice, and QuestionPrompted is empty.
        matching_actions.sort(key=_question_action_priority)

        matched_answer_ids = []
        matched_answer_choices = []

        for action in matching_actions:
            action_answer_ids = get_answer_ids_from_question_action(action)
            action_answer_choices = get_answer_choices_from_question_action(action)

            if action_answer_ids or action_answer_choices:
                matched_answer_ids = action_answer_ids
                matched_answer_choices = action_answer_choices
                break

        if not matched_answer_ids and matched_answer_choices:
            matched_answer_ids = [normalize_answer_id(choice) for choice in matched_answer_choices]

        matched_value = None
        if matched_answer_ids:
            if ps_config.get("multi_action"):
                score_map = PERSONAL_SAFETY_MULTI_ACTION_SCORE_MAPS[ps_config["score_map_key"]]
                matched_value = score_map.get(frozenset(matched_answer_ids))
            else:
                answer_map = PERSONAL_SAFETY_SINGLE_ANSWER_SCORE_MAPS[ps_config["answer_map_key"]]
                # Matches the April probe matcher's single-answer behavior by using
                # the last recorded answer when multiple answers are present.
                matched_value = answer_map.get(matched_answer_ids[-1])

        result[ps_config["result_key"]] = matched_value
        result[ps_config["actions_key"]] = " | ".join(matched_answer_choices) if matched_answer_choices else None


    return result


def _derive_inject_patients_from_json(sim_json, env_key):
    """Infer inject patients from reusable JSON metadata with April-compatible fallback.

    Desert logs usually activate inject patients during the explosion section.
    Urban June logs do not have that activation section, but mark the follow-on
    patients as not already engaged in patientDataList.  If neither signal is
    present, fall back to the April matcher patient names.
    """
    if not env_key:
        return []

    sections = (
        sim_json.get("configData", {})
        .get("narrative", {})
        .get("narrativeSections", [])
    )

    active_state_patients = []
    for section in sections:
        desc = str(section.get("sectionDescription", "")).lower()
        if not any(token in desc for token in ("explosion", "drone", "strike")):
            continue
        for item in section.get("patientsToChangeActiveState", []) or []:
            if not isinstance(item, dict):
                continue
            active_state = item.get("activeState")
            if active_state is True or str(active_state).strip().lower() == "true":
                patient = clean_patient_name(
                    item.get("patientName")
                    or item.get("patient")
                    or item.get("patientId")
                    or item.get("patientID")
                )
                if patient and patient not in active_state_patients:
                    active_state_patients.append(patient)

    if active_state_patients:
        return active_state_patients

    not_engaged_patients = []
    for patient_def in _iter_patient_definitions(sim_json or {}):
        patient = _extract_patient_name_from_definition(patient_def)
        if not patient:
            continue
        engaged = patient_def.get("engaged")
        if engaged is False or str(engaged).strip().lower() == "false":
            not_engaged_patients.append(patient)

    if not_engaged_patients:
        fallback_order = INJECT_PATIENTS_FALLBACK.get(env_key, [])
        ordered = [p for p in fallback_order if p in not_engaged_patients]
        ordered.extend([p for p in not_engaged_patients if p not in ordered])
        return ordered

    return list(INJECT_PATIENTS_FALLBACK.get(env_key, []))


def _get_radio_elapsed_seconds(sim_json, env_key):
    """Return cumulative narrative elapsed seconds at the inject radio section."""
    sections = (
        sim_json.get("configData", {})
        .get("narrative", {})
        .get("narrativeSections", [])
    )
    target_section = str(INJECT_RADIO_SECTION_NAME.get(env_key, "")).strip().lower()
    running_elapsed = 0.0

    for section in sections:
        running_elapsed += safe_float(section.get("delayInSeconds", 0))
        desc = str(section.get("sectionDescription", "")).strip().lower()
        if target_section and desc == target_section:
            return running_elapsed

    # Reusable fallback: if the exact April section name changed slightly,
    # treat the first section containing both explosion/aftermath and radio as
    # the inject radio anchor.
    running_elapsed = 0.0
    for section in sections:
        running_elapsed += safe_float(section.get("delayInSeconds", 0))
        desc = str(section.get("sectionDescription", "")).strip().lower()
        if "explosion" in desc and "radio" in desc:
            return running_elapsed

    return None


# Fields extracted:
# - Desert Probe_PS3
# - Desert Probe_SS1
# - Urban Probe_PS2
# - Urban Probe_SS1
def compute_inject_probe_values(csv_rows, sim_json, env):
    """Compute April-style inject-derived personal-safety/search-safety probes.

    This mirrors April matcher behavior while deriving patient and timing anchors
    from the updated sim JSON when possible:
    - PS value is 1 if any inject patient was engaged, else 0.
    - SS value is the visit-count distance from the radio anchor to the first
      inject-patient engagement, capped to 0..10.  If no inject patient was
      engaged, SS is 10.
    """
    env_lower = str(env or "").lower()
    env_key = "desert" if "desert" in env_lower else "urban" if "urban" in env_lower else None
    if not env_key:
        return {}

    inject_patients = set(_derive_inject_patients_from_json(sim_json, env_key))
    engaged_patients = set()
    engagement_rows = []

    for row in csv_rows:
        ev = row.get("EventName")
        if ev not in ENGAGEMENT_EVENTS:
            continue
        patient = clean_patient_name(row.get("PatientID", ""))
        if not is_valid_patient(patient):
            continue
        elapsed_sec = safe_float(row.get("ElapsedTime", 0)) / 1000.0
        engagement_rows.append({"patient": patient, "elapsed_sec": elapsed_sec})
        engaged_patients.add(patient)

    inject_engaged = any(patient in engaged_patients for patient in inject_patients)
    radio_elapsed_sec = _get_radio_elapsed_seconds(sim_json, env_key)

    baseline_visit_index = 0
    first_inject_visit_index = None
    if engagement_rows:
        if radio_elapsed_sec is not None:
            for idx, event in enumerate(engagement_rows, start=1):
                if event["elapsed_sec"] <= radio_elapsed_sec:
                    baseline_visit_index = idx
                if (
                    first_inject_visit_index is None
                    and event["elapsed_sec"] >= radio_elapsed_sec
                    and event["patient"] in inject_patients
                ):
                    first_inject_visit_index = idx
        else:
            for idx, event in enumerate(engagement_rows, start=1):
                if event["patient"] in inject_patients:
                    first_inject_visit_index = idx
                    break
            baseline_visit_index = 0

    if first_inject_visit_index is None:
        ss_value = 10
    else:
        ss_value = max(0, min(10, first_inject_visit_index - baseline_visit_index))

    if env_key == "desert":
        return {
            "Desert Probe_PS3": 1 if inject_engaged else 0,
            "Desert Probe_SS1": ss_value,
        }
    return {
        "Urban Probe_PS2": 1 if inject_engaged else 0,
        "Urban Probe_SS1": ss_value,
    }

# ============================================================
# ACTION ANALYSIS
# ============================================================

# Fields extracted:
# - Assess_patient
# - Treat_patient
# - Triage_time_patient
# - Engage_patient
# - PatientN_time
# - PatientN_order
# - PatientN_assess
# - PatientN_treat
def extract_action_analysis(csv_rows, sim_json, env, pid=None):
    """Build the actionAnalysis section using reusable CSV + JSON-based metrics."""

    prefix = build_env_prefix(env)
    action_analysis = {}

    assessments = compute_assessment_metrics(csv_rows)
    treatments = compute_treatment_metrics(csv_rows)
    triage_times = compute_patient_interactions(csv_rows)
    expected_tag_color = derive_expected_tag_color(csv_rows)
    required_injuries, required_proc_for_injury = derive_required_injuries_and_procs(csv_rows, sim_json)
    supplemental_map = derive_supplemental_procedures(sim_json)
    treatment_submetrics_required = compute_treatment_submetrics_required(csv_rows, required_injuries)
    treatment_submetrics_w_supp = compute_treatment_submetrics_w_supp(csv_rows, required_injuries, supplemental_map)
    triage_performance = compute_triage_performance_w_supp(csv_rows, required_injuries, supplemental_map)
    tags_applied = compute_last_applied_tags(csv_rows)
    drag_metrics = compute_drag_metrics(csv_rows, sim_json, min_drag_distance=1.0)
    dragged_patients = drag_metrics["dragged_patients"]
    drag_times_by_patient = drag_metrics["drag_times_by_patient"]
    total_drag_time_by_patient = drag_metrics["total_drag_time_by_patient"]
    drag_start_location_by_patient = drag_metrics["drag_start_location_by_patient"]
    drag_end_location_by_patient = drag_metrics["drag_end_location_by_patient"]

    aggregate_patient_metrics = compute_patient_averages(
        csv_rows, assessments, treatments, triage_times
    )
    patient_order_engaged = aggregate_patient_metrics["patient_order_engaged"]

    tag_metrics = compute_tag_metrics(expected_tag_color, tags_applied)
    hem_metrics = compute_hemorrhage_control(csv_rows, required_proc_for_injury)

    spawn_location = compute_spawn_location_value(sim_json, pid)
    if spawn_location is not None and prefix:
        action_analysis[f"{prefix}Spawn_location"] = spawn_location

    evac_value_by_patient = compute_evac_value_by_patient(csv_rows, sim_json, env)

    personal_safety_values = compute_personal_safety_values(sim_json, env)
    action_analysis.update(personal_safety_values)

    inject_probe_values = compute_inject_probe_values(csv_rows, sim_json, env)
    action_analysis.update(inject_probe_values)

    action_analysis[f"{prefix}Assess_patient"] = aggregate_patient_metrics["assess_patient"]
    action_analysis[f"{prefix}Treat_patient"] = aggregate_patient_metrics["treat_patient"]
    action_analysis[f"{prefix}Triage_time_patient"] = aggregate_patient_metrics["triage_time_patient"]
    action_analysis[f"{prefix}Engage_patient"] = aggregate_patient_metrics["engage_patient"]
    action_analysis[f"{prefix}Tag_ACC"] = tag_metrics["tag_acc"]
    action_analysis[f"{prefix}Tag_Expectant"] = tag_metrics["tag_expectant"]
    action_analysis[f"{prefix}Hemorrhage control"] = hem_metrics["hemorrhage_control"]
    action_analysis[f"{prefix}Hemorrhage control_time"] = hem_metrics["hemorrhage_control_time"]
    action_analysis[f"{prefix}Treat_hits_required"] = treatment_submetrics_required["total_hits"]
    action_analysis[f"{prefix}Treat_false_alarms_required"] = treatment_submetrics_required["total_false_alarms"]
    action_analysis[f"{prefix}Treat_repeat_hits_required"] = treatment_submetrics_required["total_repeat_hits"]
    action_analysis[f"{prefix}Treat_repeat_false_alarms_required"] = treatment_submetrics_required["total_repeat_false_alarms"]
    action_analysis[f"{prefix}Treat_hits_w_supp"] = treatment_submetrics_w_supp["total_hits"]
    action_analysis[f"{prefix}Treat_false_alarms_w_supp"] = treatment_submetrics_w_supp["total_false_alarms"]
    action_analysis[f"{prefix}Treat_repeat_hits_w_supp"] = treatment_submetrics_w_supp["total_repeat_hits"]
    action_analysis[f"{prefix}Treat_repeat_false_alarms_w_supp"] = treatment_submetrics_w_supp["total_repeat_false_alarms"]
    action_analysis[f"{prefix}Triage Performance"] = triage_performance

    patients_in_order = compute_patients_in_order(csv_rows, patient_order_engaged)

    clean_patient_order_engaged = []
    for patient in patient_order_engaged:
        if patient not in clean_patient_order_engaged:
            clean_patient_order_engaged.append(patient)

    for i, sim_name in enumerate(patients_in_order):
        name = f"{prefix}Patient{i + 1}"

        action_analysis[f"{name}_time"] = round(triage_times["interactions"].get(sim_name, 0), 3)

        try:
            action_analysis[f"{name}_order"] = clean_patient_order_engaged.index(sim_name) + 1
        except Exception:
            action_analysis[f"{name}_order"] = "N/A"

        action_analysis[f"{name}_dragged"] = "Yes" if sim_name in dragged_patients else "No"
        action_analysis[f"{name}_drag_times"] = ", ".join(str(t) for t in drag_times_by_patient.get(sim_name, []))
        action_analysis[f"{name}_total_drag_time"] = total_drag_time_by_patient.get(sim_name, 0)
        action_analysis[f"{name}_drag_start_location"] = format_vec3(
            drag_start_location_by_patient.get(sim_name)
        ) if sim_name in dragged_patients else None
        action_analysis[f"{name}_drag_end_location"] = format_vec3(
            drag_end_location_by_patient.get(sim_name)
        ) if sim_name in dragged_patients else None
        action_analysis[f"{name}_evac"] = evac_value_by_patient.get(sim_name, 0)
        action_analysis[f"{name}_assess"] = assessments["per_patient"].get(sim_name, 0)
        action_analysis[f"{name}_treat"] = treatments["per_patient"].get(sim_name, 0)
        action_analysis[f"{name}_tag"] = tags_applied.get(sim_name, "None")
        action_analysis[f"{name}_triage_truth"] = expected_tag_color.get(sim_name, None)
        action_analysis[f"{name}_required_injuries"] = required_injuries.get(sim_name, [])
        action_analysis[f"{name}_treat_hits_required"] = treatment_submetrics_required["per_patient_hits"].get(sim_name, 0)
        action_analysis[f"{name}_treat_false_alarms_required"] = treatment_submetrics_required["per_patient_false_alarms"].get(sim_name, 0)
        action_analysis[f"{name}_treat_repeat_hits_required"] = treatment_submetrics_required["per_patient_repeat_hits"].get(sim_name, 0)
        action_analysis[f"{name}_treat_repeat_false_alarms_required"] = treatment_submetrics_required["per_patient_repeat_false_alarms"].get(sim_name, 0)
        action_analysis[f"{name}_treat_hits_w_supp"] = treatment_submetrics_w_supp["per_patient_hits"].get(sim_name, 0)
        action_analysis[f"{name}_treat_false_alarms_w_supp"] = treatment_submetrics_w_supp["per_patient_false_alarms"].get(sim_name, 0)
        action_analysis[f"{name}_treat_repeat_hits_w_supp"] = treatment_submetrics_w_supp["per_patient_repeat_hits"].get(sim_name, 0)
        action_analysis[f"{name}_treat_repeat_false_alarms_w_supp"] = treatment_submetrics_w_supp["per_patient_repeat_false_alarms"].get(sim_name, 0)

    return action_analysis



# ============================================================
# TA1 / ADEPT / ALIGNMENT
# ============================================================

def get_eval_number(metadata):
    """Return the best evalNumber for this run, defaulting to June 2026."""
    value = metadata.get("evalNumber")
    return value if value is not None else DEFAULT_EVAL_NUM


def get_eval_name(metadata):
    """Return the best evalName for this run, defaulting to June 2026."""
    value = metadata.get("evalName")
    return value if value else DEFAULT_EVAL_NAME


def get_eval_prefix(metadata):
    """Derive a text/open-world scenario prefix such as Jun2026 or June2026."""
    scenario_id = str(metadata.get("scenario_id", "") or "")
    for separator in ("-OW", "_OW", "-ow", "_ow"):
        if separator in scenario_id:
            prefix = scenario_id.split(separator)[0]
            if prefix:
                return prefix

    eval_name = str(get_eval_name(metadata) or "")
    match = re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|June|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s*(\d{4})\b", eval_name, re.IGNORECASE)
    if match:
        month = match.group(1).lower()
        year = match.group(2)
        month_short = {
            "january": "Jan", "jan": "Jan",
            "february": "Feb", "feb": "Feb",
            "march": "Mar", "mar": "Mar",
            "april": "Apr", "apr": "Apr",
            "may": "May",
            "june": "Jun", "jun": "Jun",
            "july": "Jul", "jul": "Jul",
            "august": "Aug", "aug": "Aug",
            "september": "Sept", "sept": "Sept", "sep": "Sept",
            "october": "Oct", "oct": "Oct",
            "november": "Nov", "nov": "Nov",
            "december": "Dec", "dec": "Dec",
        }.get(month, month[:3].title())
        return f"{month_short}{year}"

    return "Jun2026"


def get_eval_prefix_candidates(metadata):
    """Return possible prefixes used by June text/open-world scenario ids."""
    base = get_eval_prefix(metadata)
    candidates = [base]
    if base.lower().startswith("jun") and not base.lower().startswith("june"):
        candidates.append("June" + base[3:])
    if base.lower().startswith("june"):
        candidates.append("Jun" + base[4:])
    # Include the known June 2026 variants as fallbacks.
    for fallback in ("Jun2026", "June2026"):
        if fallback not in candidates:
            candidates.append(fallback)
    return candidates


def load_openworld_yaml_for_env(env):
    """Load the June 2026 open-world YAML matching the detected environment.

    The June 2026 YAML filenames use the full `june2026` prefix, for example
    `june2026-desert-openworld.yaml` and `june2026-urban-openworld.yaml`.
    """
    if yaml is None:
        logger.log(LogLevel.WARN, "PyYAML is not installed; skipping open-world YAML matching.")
        return None

    env = str(env or "")
    env_lower = env.lower()
    terrain = "desert" if "desert" in env_lower else "urban" if "urban" in env_lower else env
    candidate_paths = [
        os.path.join("phase2", "june2026", "openworld", f"{env}.yaml"),
        os.path.join("phase2", "june2026", "openworld", f"{terrain}.yaml"),
    ]

    for yaml_filename in candidate_paths:
        if not os.path.exists(yaml_filename):
            continue
        try:
            if VERBOSE:
                logger.log(LogLevel.INFO, f"Opening {yaml_filename}")
            with open(yaml_filename, "r", encoding="utf-8") as yf:
                loader = getattr(yaml, "CLoader", yaml.SafeLoader)
                return yaml.load(yf, Loader=loader)
        except Exception as e:
            logger.log(LogLevel.ERROR, f"Error loading open world yaml file {yaml_filename}.\n\n{e}\n")
            return None

    if VERBOSE:
        logger.log(LogLevel.WARN, f"No open-world YAML file found for environment {env}.")
    return None


def get_ta1_calculations(scenario_id, probes):
    """Create a TA1 session, send probe choices, and fetch computed KDMAs."""
    if not CALC_KDMAS:
        return None, None
    if requests is None:
        logger.log(LogLevel.WARN, "requests is not installed; skipping TA1/KDMA computation.")
        return None, None
    if not probes:
        return None, None
    if not ADEPT_URL or ADEPT_URL == "/":
        logger.log(LogLevel.WARN, "ADEPT_URL not set; skipping KDMA computation.")
        return None, None
    try:
        session_id = requests.post(f"{ADEPT_URL}api/v1/new_session", timeout=120).text.replace('"', '').strip()
        if VERBOSE:
            logger.log(LogLevel.INFO, f"--> Sending probes: {probes}")
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
                timeout=120,
            )
        kdmas = requests.get(
            f"{ADEPT_URL}api/v1/computed_kdma_profile?session_id={session_id}",
            timeout=120,
        ).json()
    except Exception as e:
        logger.log(LogLevel.WARN, f"TA1/KDMA request failed: {e}")
        return None, None
    return session_id, kdmas


def _norm_casualty_name(name):
    """Normalize casualty naming differences between YAML, JSON, and CSV."""
    if not name:
        return ""
    n = clean_patient_name(name)
    if n.lower().startswith("us "):
        n = n[3:].lstrip()
    return n.strip()


def _iter_probe_engagement_actions(sim_json):
    """Yield action records usable for YAML probe matching across log shapes."""
    engagement_action_types = {
        "pulse", "treatment", "tag", "disarmpatientweapon", "question",
        "tool_applied", "tag_applied", "pulse_taken", "sp_o2_taken",
        "breathing_checked", "patient_engaged", "questionanswered",
        "question_answered", "answerselected", "answer_selected",
    }
    for action in _iter_action_items(sim_json):
        action_type = str(action.get("actionType") or action.get("action_type") or action.get("EventName") or "").strip().lower()
        action_type_norm = re.sub(r"[^a-z0-9]+", "_", action_type).strip("_")
        action_type_compact = action_type_norm.replace("_", "")
        if action_type_norm in engagement_action_types or action_type_compact in engagement_action_types:
            yield action


def _get_action_casualty(action):
    """Return the patient/casualty referenced by a sim action."""
    return clean_patient_name(
        action.get("casualty")
        or action.get("patient")
        or action.get("patientId")
        or action.get("patientID")
        or action.get("PatientID")
        or action.get("character")
        or action.get("characterId")
        or ""
    )


def compute_openworld_match_data(sim_json, metadata):
    """Run open-world YAML probe matching and return match data plus human session id."""
    env = metadata.get("env", "")
    if VERBOSE:
        logger.log(LogLevel.INFO, f"Processing probe match for {env}")

    ow_yaml = load_openworld_yaml_for_env(env)
    if not ow_yaml:
        return {"alignment": {}, "data": []}, None

    probe_map = {}
    for scene in ow_yaml.get("scenes", []) or []:
        patient_name_map = {}
        response_map = {}
        for character in scene.get("state", {}).get("characters", []) or []:
            unstructured = character.get("unstructured", "")
            sim_patient_name = unstructured.split(";")[-1].strip() if unstructured else character.get("name", "")
            patient_name_map[character.get("id")] = sim_patient_name
        for mapping in scene.get("action_mapping", []) or []:
            probe_id = mapping.get("probe_id")
            choice_id = mapping.get("choice")
            character_id = mapping.get("character_id")
            if probe_id and choice_id and character_id in patient_name_map:
                response_map[patient_name_map[character_id]] = choice_id
                probe_map[probe_id] = dict(response_map)

    action_list = list(_iter_probe_engagement_actions(sim_json))

    def first_engaged(characters):
        candidates = {_norm_casualty_name(ch) for ch in characters}
        for action in action_list:
            casualty = _norm_casualty_name(_get_action_casualty(action))
            if casualty in candidates:
                for ch in characters:
                    if _norm_casualty_name(ch) == casualty:
                        return ch
        return None

    probes = []
    match_rows = []
    real_probe_count = 0
    for probe_id, response_map in probe_map.items():
        if "fake" in str(probe_id).lower():
            continue
        real_probe_count += 1
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
            if VERBOSE:
                logger.log(LogLevel.WARN, f"Unmatched probe {probe_id}.")
            match_rows.append(
                {
                    "scene_id": probe_id,
                    "probe_id": probe_id,
                    "found_match": False,
                    "response": "",
                    "user_action": {},
                }
            )

    if VERBOSE:
        logger.log(LogLevel.INFO, f"Found {len(probes)} out of {real_probe_count} probes.")

    ow_align = {}
    human_session_id = None
    if CALC_KDMAS:
        if not probes:
            logger.log(LogLevel.WARN, "No probes available for KDMA calculation.")
        else:
            logger.log(LogLevel.INFO, f"Calling TA1 server for KDMA calculation with {len(probes)} probes...")
            human_session_id, kdmas = get_ta1_calculations(ow_yaml.get("id", metadata.get("scenario_id", "")), probes)
            if human_session_id and kdmas is not None:
                logger.log(LogLevel.INFO, f"KDMA calculation complete (session_id={human_session_id})")
            else:
                logger.log(LogLevel.WARN, "TA1 server request failed; no KDMAs generated.")
            ow_align["sid"] = human_session_id
            ow_align["kdmas"] = kdmas
    elif VERBOSE:
        logger.log(LogLevel.INFO, "KDMA calculation disabled (use -k to enable).")

    return {"alignment": ow_align, "data": match_rows}, human_session_id


def find_text_session_for_alignment(metadata, alignment_type):
    """Find the matching MF/AF text combinedSessionId for alignment compare."""
    if text_scenario_collection is None:
        logger.log(LogLevel.WARN, f"text_scenario_collection is unavailable; cannot look up {alignment_type} text session.")
        return None

    pid = metadata.get("pid")
    pid_candidates = [pid]
    if str(pid).isdigit():
        pid_candidates.append(int(pid))

    eval_number = get_eval_number(metadata)
    eval_name = get_eval_name(metadata)
    scenario_candidates = []
    for prefix in get_eval_prefix_candidates(metadata):
        scenario_candidates.append(f"{prefix}-{alignment_type}-assess")
        scenario_candidates.append(f"{prefix}_{alignment_type}_assess")

    queries = []
    for pid_val in pid_candidates:
        for scenario_id in scenario_candidates:
            queries.append({"evalNumber": eval_number, "participantID": pid_val, "scenario_id": scenario_id})
            queries.append({"participantID": pid_val, "scenario_id": scenario_id})
        # Fallbacks for naming differences.
        queries.append({
            "evalNumber": eval_number,
            "participantID": pid_val,
            "scenario_id": {"$regex": f"{alignment_type}.*assess", "$options": "i"},
        })
        queries.append({
            "evalName": eval_name,
            "participantID": pid_val,
            "scenario_id": {"$regex": f"{alignment_type}.*assess", "$options": "i"},
        })

    for query in queries:
        try:
            try:
                text_doc = text_scenario_collection.find_one(query, sort=[("timeComplete", -1)])
            except TypeError:
                text_doc = text_scenario_collection.find_one(query)
        except Exception:
            text_doc = None

        if not text_doc:
            continue

        session_id = text_doc.get("combinedSessionId")
        if session_id:
            if VERBOSE:
                logger.log(LogLevel.INFO, f"Retrieved combinedSessionId for {alignment_type}: {session_id}")
            return str(session_id)

        logger.log(LogLevel.WARN, f"Found text document for {alignment_type} alignment but combinedSessionId was missing.")
        return None

    logger.log(LogLevel.WARN, f"Could not find text document for {alignment_type} alignment (pid={pid}, evalNumber={eval_number}).")
    return None


def get_alignment_compare_score(human_session_id, metadata, alignment_type):
    """Compare the current human session against the matching text session."""
    if not CALC_KDMAS:
        return None
    if requests is None:
        logger.log(LogLevel.WARN, "requests is not installed; skipping alignment compare calculation.")
        return None
    if not human_session_id:
        logger.log(LogLevel.WARN, f"No human session_id available for {alignment_type} alignment.")
        return None
    if not ADEPT_URL or ADEPT_URL == "/":
        logger.log(LogLevel.WARN, "ADEPT_URL not set; skipping alignment compare calculation.")
        return None

    text_session_id = find_text_session_for_alignment(metadata, alignment_type)
    if not text_session_id:
        return None

    kdma_filter = "merit" if alignment_type == "MF" else "affiliation"
    try:
        response = requests.get(
            f"{ADEPT_URL}api/v1/alignment/compare_sessions",
            params={
                "session_id_1": str(human_session_id),
                "session_id_2": str(text_session_id),
                "kdma_filter": kdma_filter,
            },
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        score = payload.get("score")
        if score is None:
            logger.log(LogLevel.WARN, f"{alignment_type} alignment compare returned null for pid {metadata.get('pid')}.")
            return None
        score_value = float(score)
        if math.isnan(score_value):
            logger.log(LogLevel.WARN, f"{alignment_type} alignment compare returned NaN for pid {metadata.get('pid')}.")
            return None
        return score_value
    except Exception as e:
        logger.log(LogLevel.WARN, f"Alignment compare request failed for {alignment_type} / pid {metadata.get('pid')}: {e}")
        return None


# Fields extracted:
# - MF Alignment_Desert
# - AF Alignment_Desert
# - MF Alignment_Urban
# - AF Alignment_Urban
def compute_alignment_scores(metadata, human_session_id=None):
    """Return MF/AF alignment fields for the current run."""
    prefix = build_env_prefix(metadata.get("env", ""))
    env_name = prefix.strip() or metadata.get("env", "")
    return {
        f"MF Alignment_{env_name}": get_alignment_compare_score(human_session_id, metadata, "MF"),
        f"AF Alignment_{env_name}": get_alignment_compare_score(human_session_id, metadata, "AF"),
    }


# ============================================================
# TEXT KDMAS
# ============================================================

def _is_current_eval_text_doc(doc, metadata):
    """Return True when a text scenario document appears to belong to this eval."""
    scenario_id = str(doc.get("scenario_id", "") or "")
    eval_name = str(doc.get("evalName", "") or "")
    eval_number = doc.get("evalNumber")
    eval_number_target = get_eval_number(metadata)
    eval_name_target = str(get_eval_name(metadata) or "")
    prefixes = tuple(get_eval_prefix_candidates(metadata))

    return (
        eval_number == eval_number_target
        or (eval_name_target and eval_name == eval_name_target)
        or any(scenario_id.startswith(prefix) for prefix in prefixes)
        or "June 2026" in eval_name
        or "June2026" in eval_name
    )


def _extract_kdmas_from_doc(doc):
    """Return the best available KDMA array from a text scenario doc."""
    if isinstance(doc.get("combinedKdmas"), list) and doc.get("combinedKdmas"):
        return doc.get("combinedKdmas"), "combinedKdmas"

    merged = []
    for field_name in ["AF-PS_kdmas", "MF-PS_kdmas", "AF_SS_kdmas", "MF_SS_kdmas", "AF-SS_kdmas", "MF-SS_kdmas"]:
        value = doc.get(field_name)
        if isinstance(value, list) and value:
            merged.extend(value)
    if merged:
        return merged, "merged_assess_kdmas"

    for field_name in ["kdmas", "individualKdmas"]:
        value = doc.get(field_name)
        if isinstance(value, list) and value:
            return value, field_name

    return [], None


def extract_text_kdmas(metadata):
    """Join text scenario KDMAs for the current eval, preferring combinedKdmas."""
    text_kdma_results = {
        f"Participant Text {short_name} {param_name} KDMA": ""
        for short_name in KDMA_MAP.values()
        for param_name in ["intercept", "attr_weight", "medical_weight"]
    }

    if text_scenario_collection is None:
        return text_kdma_results

    pid = metadata.get("pid")
    pid_candidates = [pid]
    if str(pid).isdigit():
        pid_candidates.append(int(pid))

    eval_number = get_eval_number(metadata)
    eval_name = get_eval_name(metadata)
    prefixes = get_eval_prefix_candidates(metadata)

    text_docs = []
    seen_ids = set()
    queries = []
    for pid_val in pid_candidates:
        queries.append({"participantID": pid_val, "evalNumber": eval_number})
        queries.append({"participantID": pid_val, "evalName": eval_name})
        for prefix in prefixes:
            queries.append({"participantID": pid_val, "scenario_id": {"$regex": f"^{prefix}", "$options": "i"}})
        queries.append({"participantID": pid_val})

    try:
        for query in queries:
            for doc in text_scenario_collection.find(query):
                doc_id = str(doc.get("_id", ""))
                if doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    text_docs.append(doc)
    except Exception as e:
        print(f"Warning: Error getting text KDMAs from database for pid {pid}: {e}")
        return text_kdma_results

    if not text_docs:
        if VERBOSE:
            print(f"Warning: No text scenario documents found for pid {pid}.")
        return text_kdma_results

    preferred_docs = [doc for doc in text_docs if _is_current_eval_text_doc(doc, metadata)]
    docs_to_use = preferred_docs if preferred_docs else text_docs
    docs_to_use.sort(
        key=lambda d: (
            0 if (isinstance(d.get("combinedKdmas"), list) and d.get("combinedKdmas")) else 1,
            0 if _is_current_eval_text_doc(d, metadata) else 1,
            str(d.get("timeComplete", "")),
        )
    )

    for doc in docs_to_use:
        scenario_id = doc.get("scenario_id", "")
        kdmas, source_field = _extract_kdmas_from_doc(doc)
        if not kdmas:
            continue

        for kdma in kdmas:
            kdma_name = kdma.get("kdma")
            if kdma_name not in KDMA_MAP:
                continue
            short_name = KDMA_MAP[kdma_name]
            for param in kdma.get("parameters", []) or []:
                param_name = param.get("name")
                param_value = param.get("value", "")
                if not param_name:
                    continue
                key = f"Participant Text {short_name} {param_name} KDMA"
                if key in text_kdma_results and text_kdma_results[key] not in ("", param_value):
                    print(
                        f"Warning: Duplicate text KDMA value for {key} on pid {pid}; "
                        f"overwriting {text_kdma_results[key]} with {param_value} from {scenario_id} ({source_field})."
                    )
                text_kdma_results[key] = param_value

        if source_field == "combinedKdmas":
            break

    return text_kdma_results

# ============================================================
# OUTPUT BUILDING
# ============================================================

def build_output_documents(
    metadata,
    event_totals,
    action_analysis,
    sim_json,
    patient_interactions=None,
    interaction_time=None,
    interaction_visits=None,
    patient_order=None,
    tag_colors=None,
    correct_tag_breakdown=None,
    patient_hc_time=None,
    missed_hemorrhage_control=None,
    tag_distribution=None,
    salt=None,
    salt_errors=None,
    text_kdmas=None,
    alignment_scores=None,
    match_data=None,
):
    """Build the raw and analysis output documents."""
    pid = metadata["pid"]
    env = metadata["env"]
    doc_id = build_probe_matcher_style_id(pid, env)

    raw_doc = {
        "_id": doc_id,
        "pid": pid,
        "env": env,
        "scenario_id": metadata["scenario_id"],
        "openWorld": metadata["openWorld"],
        "evalNumber": metadata.get("evalNumber"),
        "evalName": metadata.get("evalName"),
        "patientMapShown": metadata.get("patientMapShown"),
        "data": sim_json,
    }

    analysis_doc = {
        "_id": doc_id,
        "pid": pid,
        "env": env,
        "scenario_id": metadata["scenario_id"],
        "openWorld": metadata["openWorld"],
        "evalNumber": metadata.get("evalNumber"),
        "evalName": metadata.get("evalName"),
        "patientMapShown": metadata.get("patientMapShown"),
        "timestamp": int(datetime.utcnow().timestamp() * 1000),
        "eventTotals": event_totals,
        "actionAnalysis": action_analysis,
    }

    if patient_interactions is not None:
        analysis_doc["patient_interactions"] = patient_interactions
    if interaction_time is not None:
        analysis_doc["interaction_time"] = interaction_time
    if interaction_visits is not None:
        analysis_doc["interaction_visits"] = interaction_visits
    if patient_order is not None:
        analysis_doc["patient_order"] = patient_order
    if tag_colors is not None:
        analysis_doc["tag_colors"] = tag_colors
    if correct_tag_breakdown is not None:
        analysis_doc.update(correct_tag_breakdown)
    if patient_hc_time is not None:
        analysis_doc["patient_hc_time"] = patient_hc_time
    if missed_hemorrhage_control is not None:
        analysis_doc["missed_hemorrhage_control"] = missed_hemorrhage_control
    if tag_distribution is not None:
        analysis_doc.update(tag_distribution)
    if salt is not None:
        analysis_doc["salt"] = salt
    if salt_errors is not None:
        analysis_doc["salt_errors"] = salt_errors
    if text_kdmas is not None:
        analysis_doc["text_kdmas"] = text_kdmas
    if alignment_scores is not None:
        analysis_doc["alignment_scores"] = alignment_scores
    if match_data is not None:
        analysis_doc["data"] = match_data

    return raw_doc, analysis_doc


def save_output(output_dir, filename, analysis_doc):
    """Write the analysis document to disk."""
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{filename}_analysis.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(analysis_doc, f, indent=2)

    if VERBOSE:
        logger.log(LogLevel.INFO, f"Saved analysis: {out_path}")
    else:
        print(f"Saved analysis: {out_path}")



# ============================================================
# MONGO OUTPUT
# ============================================================

def initialize_mongo():
    """Initialize Mongo collections for reads and optional writes."""
    global mongo_collection_analysis, mongo_collection_raw, text_scenario_collection

    if MongoClient is None:
        raise RuntimeError("pymongo is not installed. Install it to use Mongo read/write features.")

    client = MongoClient(config("MONGO_URL"))
    db = client.dashboard
    mongo_collection_analysis = db["humanSimulator"]
    mongo_collection_raw = db["humanSimulatorRaw"]
    text_scenario_collection = db["userScenarioResults"]
    return client


def save_to_mongo(raw_doc, analysis_doc):
    """Upsert raw and analysis documents into Mongo collections."""
    if mongo_collection_raw is None or mongo_collection_analysis is None:
        raise RuntimeError("Mongo collections are not initialized.")

    mongo_collection_raw.update_one(
        {"_id": raw_doc["_id"]},
        {"$set": raw_doc},
        upsert=True,
    )
    mongo_collection_analysis.update_one(
        {"_id": analysis_doc["_id"]},
        {"$set": analysis_doc},
        upsert=True,
    )

# ============================================================
# PIPELINE EXECUTION
# ============================================================

def process_file(json_path, output_dir):
    """Process one simulation run from JSON/CSV inputs and write its analysis output."""
    filename = os.path.basename(json_path).replace(".json", "")

    with open(json_path, "r", encoding="utf-8") as f:
        sim_json = json.load(f)

    csv_path = json_path.replace(".json", ".csv")
    csv_rows = load_csv_rows(csv_path)

    metadata = extract_run_metadata(sim_json, filename)
    event_totals = extract_event_totals(csv_rows, metadata["env"])
    action_analysis = extract_action_analysis(csv_rows, sim_json, metadata["env"], metadata["pid"])
    triage_times = compute_patient_interactions(csv_rows)
    tag_colors = compute_last_applied_tags(csv_rows)
    expected_tag_color = derive_expected_tag_color(csv_rows)
    correct_tag_breakdown = compute_correct_tag_breakdown(expected_tag_color, tag_colors)
    tag_distribution = compute_tag_distribution(csv_rows, expected_tag_color)
    salt = derive_salt_categories(csv_rows, sim_json)
    salt_errors = compute_salt_errors(csv_rows, salt)
    _, required_proc_for_injury = derive_required_injuries_and_procs(csv_rows, sim_json)
    hem_metrics = compute_hemorrhage_control(csv_rows, required_proc_for_injury)
    patient_hc_time = compute_patient_hc_time(
        csv_rows,
        triage_times["patient_interactions"],
        required_proc_for_injury,
    )
    missed_hemorrhage_control = hem_metrics["missed_hemorrhage_control"]
    text_kdmas = extract_text_kdmas(metadata)
    match_data, human_session_id = compute_openworld_match_data(sim_json, metadata)
    alignment_scores = compute_alignment_scores(metadata, human_session_id=human_session_id)

    raw_doc, analysis_doc = build_output_documents(
        metadata,
        event_totals,
        action_analysis,
        sim_json,
        patient_interactions=triage_times["patient_interactions"],
        interaction_time=triage_times["interaction_time"],
        interaction_visits=triage_times["interaction_visits"],
        patient_order=triage_times["patient_order"],
        tag_colors=tag_colors,
        correct_tag_breakdown=correct_tag_breakdown,
        patient_hc_time=patient_hc_time,
        missed_hemorrhage_control=missed_hemorrhage_control,
        tag_distribution=tag_distribution,
        salt=salt,
        salt_errors=salt_errors,
        text_kdmas=text_kdmas,
        alignment_scores=alignment_scores,
        match_data=match_data,
    )

    save_output(output_dir, filename, analysis_doc)

    if SEND_TO_MONGO:
        save_to_mongo(raw_doc, analysis_doc)
        print(f"Upserted Mongo documents for: {analysis_doc['_id']}")

    # Keep the command-line output readable when processing many files.
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="June 2026 probe matcher")
    parser.add_argument(
        "-i",
        "--input_dir",
        required=True,
        help="Directory containing simulation JSON files",
    )
    parser.add_argument(
        "-o",
        "--output_dir",
        default="output_june2026_probe_matcher",
        help="Directory for analysis JSON files",
    )
    parser.add_argument(
        "-m",
        "--send_to_mongo",
        action="store_true",
        help="Also upsert raw and analysis documents to MongoDB",
    )
    parser.add_argument(
        "-k",
        "--calc_kdmas",
        action="store_true",
        help="Hit the ADEPT/TA1 server to compute open-world session KDMAs and alignment scores",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose command line output",
    )
    args = parser.parse_args()

    CALC_KDMAS = args.calc_kdmas
    VERBOSE = args.verbose

    if args.send_to_mongo:
        SEND_TO_MONGO = True

    # Mongo is used for text KDMA reads and alignment text-session lookups.
    # If it is unavailable, the script still runs and emits blank text_kdmas / null alignments.
    try:
        initialize_mongo()
    except Exception as e:
        logger.log(LogLevel.WARN, f"Could not initialize Mongo collections for read/write access: {e}")

    json_paths = []
    for root, _, files in os.walk(args.input_dir):
        for file in files:
            if not file.endswith(".json"):
                continue
            if file.endswith("_analysis.json"):
                continue
            json_paths.append(os.path.join(root, file))

    for json_path in json_paths:
        if VERBOSE:
            logger.log(LogLevel.INFO, f"Processing file {json_path}")
        process_file(json_path, args.output_dir)
