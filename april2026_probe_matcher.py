# ============================================================
# APR 2026 PROBE MATCHER
# ============================================================
#
# Processes simulation JSON + CSV files to generate APR 2026-style analysis outputs
# including patient interactions, treatment metrics, tagging accuracy,
# and hemorrhage control. Designed to extend the reusable sim analysis pipeline with Apr 2026 probe matcher behavior. Outputs analysis JSON files
# and optionally upserts results to MongoDB (dashboard → humanSimulator
# and humanSimulatorRaw) when the `-m` flag is used.
#
# Flags:
#   -i / --input_dir      Input directory containing JSON/CSV files (required)
#   -o / --output_dir     Output directory for analysis files (default: output_april2026_probe_matcher)
#   -m / --send_to_mongo  Enable MongoDB upsert using MONGO_URL from .env
#   -k / --calc_kdmas     Enable ADEPT/TA1 calls to compute open-world session KDMAs and alignment scores
#
# ============================================================

import argparse
import csv
import json
import os
import re
from datetime import datetime

import requests
from decouple import config
import yaml
from logger import LogLevel, Logger

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None

SEND_TO_MONGO = False
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
    "march": "march",
    "april": "april",
    "may": "may",
    "june": "june",
    "july": "july",
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


EVAC_ANSWER_TO_PATIENT = {
    "desert": {
        "Mil Amputation Big Building": "US Military 1",
        "Mil Amputation Small Building": "US Military 5",
        "Mil Wrist Broken": "US Military 2",
        "Mil Chest Puncture": "US Military 3",
        "Mil Stomach Puncture": "US Military 4",
        "Civilian Thigh Laceration": "Civilian 1",
        "Civilian Stomach Puncture": "Civilian 2",
        "Civilian Amputation": "Civilian 3",
        "Attacker Stomach Puncture": "Attacker 1",
        "Attacker Shoulder Puncture": "Attacker 2",
        "Mil Explosion Chest Puncture": "US Military 6",
        "Mil Explosion Dead": "US Military 7",
    },
    "urban": {
        "Mil Bicep Puncture": "US Military 1",
        "Mil Discharged Weapon Stomach Puncture": "US Military 2",
        "Civilian Broken Wrist": "Civilian 1",
        "Shooter Shoulder Puncture": "Shooter 1",
        "Mil Thigh Puncture": "US Military 3",
        "Civilian Chest Puncture": "Civilian 2",
        "Civilian Stomach Puncture": "Civilian 3",
        "Mil Stomach Puncture": "US Military 4",
        "Mil Explosion Burns": "US Military 5",
        "Mil Explosion Dead": "US Military 6",
    },
}

CALC_KDMAS = False
VERBOSE = False
ADEPT_URL = config("ADEPT_URL", default="").rstrip("/") + "/"
logger = Logger("april2026_probeMatcher")


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


def compute_spawn_location_value(pid):
    """Match Feb 2026 spawn logic: even numeric pid -> 0, odd numeric pid -> 1."""
    pid_str = str(pid or "").strip()
    if not pid_str.isdigit():
        return None
    return 0 if int(pid_str) % 2 == 0 else 1

def compute_evac_value_by_patient(sim_json, env):
    """Match Feb-style evac extraction, using April 2026 answer labels."""
    env_lower = str(env or "").lower()
    env_key = "desert" if "desert" in env_lower else "urban" if "urban" in env_lower else None
    if not env_key:
        return {}

    answer_map = EVAC_ANSWER_TO_PATIENT.get(env_key, {})
    evac_value_by_patient = {}

    for action in sim_json.get("actionList", []):
        if action.get("actionType") != "Question":
            continue

        question = str(action.get("question", "") or "").strip().lower()
        answer = str(action.get("answer", "") or "").strip()

        if "evacuate" not in question or not answer:
            continue

        patient_name = answer_map.get(answer)
        if not patient_name:
            continue

        evac_value = None
        if env_key == "desert":
            if (
                "which casualty do you want to evacuate" in question
                or "which one casualty do you want to evacuate" in question
            ):
                evac_value = 1
            elif "which two casualties do you want to evacuate" in question:
                evac_value = 2
        elif env_key == "urban":
            if "which three casualties do you want to evacuate" in question:
                evac_value = 1

        if evac_value is None:
            continue

        if patient_name not in evac_value_by_patient:
            evac_value_by_patient[patient_name] = evac_value
        else:
            evac_value_by_patient[patient_name] = min(
                evac_value_by_patient[patient_name], evac_value
            )

    return evac_value_by_patient


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

    return {
        "pid": pid,
        "env": env,
        "scenario_id": scenario_id,
        "openWorld": open_world,
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


# Fields extracted:
# - PatientN_required_injuries
def derive_required_injuries_and_procs(csv_rows):
    """Build required injuries and their required procedures."""
    required_injuries = {}
    required_proc_for_injury = {}

    for row in csv_rows:
        if row.get("EventName") != "INJURY_RECORD":
            continue

        patient = clean_patient_name(row.get("PatientID", ""))
        injury = str(row.get("InjuryName", "")).strip()
        proc = str(row.get("InjuryRequiredProcedure", "")).strip()

        if patient and injury:
            required_injuries.setdefault(patient, []).append(injury)
            required_proc_for_injury[(patient, injury)] = proc

    return required_injuries, required_proc_for_injury


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


# Fields extracted:
# - PatientN_dragged
def compute_dragged_patients(csv_rows, min_drag_distance=1.0):
    """Return the set of patients dragged beyond the distance threshold."""
    dragged_patients = set()
    active_drag_start = {}

    for row in csv_rows:
        ev = row.get("EventName")
        patient = clean_patient_name(row.get("PatientID", ""))

        if not patient or not is_valid_patient(patient):
            continue

        if ev == "DRAG_START":
            active_drag_start[patient] = parse_vec3(row.get("DragStartPosition", ""))
        elif ev == "DRAG_STOP":
            if patient not in active_drag_start:
                continue
            start_pos = active_drag_start.pop(patient, None)
            stop_pos = parse_vec3(row.get("DragStopPosition", ""))
            if vec3_distance(start_pos, stop_pos) > min_drag_distance:
                dragged_patients.add(patient)

    return dragged_patients


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
    """Build the actionAnalysis section using reusable CSV-based metrics."""

    prefix = build_env_prefix(env)
    action_analysis = {}

    assessments = compute_assessment_metrics(csv_rows)
    treatments = compute_treatment_metrics(csv_rows)
    triage_times = compute_patient_interactions(csv_rows)
    expected_tag_color = derive_expected_tag_color(csv_rows)
    required_injuries, required_proc_for_injury = derive_required_injuries_and_procs(csv_rows)
    treatment_submetrics_required = compute_treatment_submetrics_required(csv_rows, required_injuries)
    tags_applied = compute_last_applied_tags(csv_rows)
    dragged_patients = compute_dragged_patients(csv_rows, min_drag_distance=1.0)

    aggregate_patient_metrics = compute_patient_averages(
        csv_rows, assessments, treatments, triage_times
    )
    patient_order_engaged = aggregate_patient_metrics["patient_order_engaged"]

    tag_metrics = compute_tag_metrics(expected_tag_color, tags_applied)
    hem_metrics = compute_hemorrhage_control(csv_rows, required_proc_for_injury)

    spawn_location = compute_spawn_location_value(pid)
    if spawn_location is not None and prefix:
        action_analysis[f"{prefix}Spawn_location"] = spawn_location

    evac_value_by_patient = compute_evac_value_by_patient(sim_json, env)

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

    return action_analysis


# ============================================================
# TA1 / ALIGNMENT HELPERS
# ============================================================

def load_openworld_yaml_for_env(env):
    """Load the Apr 2026 openworld YAML matching the detected environment."""
    yaml_filename = os.path.join("phase2", "april2026", "openworld", f"{env}.yaml")
    if not os.path.exists(yaml_filename):
        logger.log(LogLevel.WARN, f"YAML file not found for environment {env}: {yaml_filename}")
        return None
    try:
        if VERBOSE:
            logger.log(LogLevel.INFO, f"Opening {yaml_filename}")
        with open(yaml_filename, "r", encoding="utf-8") as yf:
            return yaml.load(yf, Loader=yaml.CLoader)
    except Exception as e:
        logger.log(LogLevel.ERROR, f"Error loading open world yaml file. Ensure it's valid YAML and exists.\n\n{e}\n")
        return None


def get_ta1_calculations(scenario_id, probes):
    """Create a TA1 session, send probe choices, and fetch computed KDMAs."""
    if not CALC_KDMAS:
        return None, None
    if not probes:
        return None, None
    if not ADEPT_URL or ADEPT_URL == "/":
        logger.log(LogLevel.WARN, "ADEPT_URL not set; skipping KDMA computation.")
        return None, None
    try:
        session_id = requests.post(f"{ADEPT_URL}api/v1/new_session").text.replace('"', '').strip()
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
    except Exception:
        return None, None
    return session_id, kdmas


def _norm_casualty_name(name):
    """Normalize casualty naming differences between YAML and JSON."""
    if not name:
        return ""
    n = str(name).strip()
    if n.lower().startswith("us "):
        n = n[3:].lstrip()
    return n.split(" Root")[0].strip()


def compute_openworld_match_data(sim_json, metadata):
    """Recreate the Feb matcher OW probe matching flow and return match_data + human session id."""
    env = metadata.get("env", "")
    logger.log(LogLevel.INFO, f"Processing probe match for {'Desert' if 'desert' in env.lower() else 'Urban' if 'urban' in env.lower() else env}")

    ow_yaml = load_openworld_yaml_for_env(env)
    if not ow_yaml:
        return {"alignment": {}, "data": []}, None

    probe_map = {}
    for scene in ow_yaml.get("scenes", []):
        patient_name_map = {}
        response_map = {}
        for character in scene.get("state", {}).get("characters", []):
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

    engagement_actions = {"Pulse", "Treatment", "Tag", "DisarmPatientWeapon", "Question"}
    action_list = [
        action for action in sim_json.get("actionList", [])
        if action.get("actionType") in engagement_actions
    ]

    def first_engaged(characters):
        candidates = {_norm_casualty_name(ch) for ch in characters}
        for action in action_list:
            casualty = _norm_casualty_name(action.get("casualty", ""))
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

    logger.log(LogLevel.INFO, f"Found {len(probes)} out of {real_probe_count} probes.")

    ow_align = {}
    human_session_id = None
    if CALC_KDMAS:
        if not probes:
            logger.log(LogLevel.WARN, "No probes available for KDMA calculation.")
        else:
            logger.log(LogLevel.INFO, f"Calling TA1 server for KDMA calculation with {len(probes)} probes...")
            human_session_id, kdmas = get_ta1_calculations(ow_yaml.get("id", ""), probes)
            if human_session_id and kdmas is not None:
                logger.log(LogLevel.INFO, f"KDMA calculation complete (session_id={human_session_id})")
            else:
                logger.log(LogLevel.WARN, "TA1 server request failed; no KDMAs generated.")
            ow_align["sid"] = human_session_id
            ow_align["kdmas"] = kdmas
    else:
        logger.log(LogLevel.INFO, "KDMA calculation disabled (use -k to enable).")

    match_data = {"alignment": ow_align, "data": match_rows}
    if VERBOSE:
        print()
        logger.log(LogLevel.INFO, f"\nMatch data: {match_data}")

    return match_data, human_session_id


def find_text_session_for_alignment(metadata, alignment_type):
    """Find the matching text-session id for MF/AF alignment compare."""
    if text_scenario_collection is None:
        return None

    pid = metadata.get("pid")
    pid_candidates = [pid]
    if str(pid).isdigit():
        pid_candidates.append(int(pid))

    scenario_regex = alignment_type
    queries = [
        {
            "evalNumber": DEFAULT_EVAL_NUM,
            "participantID": pid_val,
            "scenario_id": {"$regex": scenario_regex, "$options": "i"},
        }
        for pid_val in pid_candidates
    ]
    queries.extend([
        {
            "participantID": pid_val,
            "scenario_id": {"$regex": scenario_regex, "$options": "i"},
        }
        for pid_val in pid_candidates
    ])

    apr_specific_fields = []
    if alignment_type == "MF":
        apr_specific_fields = ["MF-PS_sessionId"]
    elif alignment_type == "AF":
        apr_specific_fields = ["AF-PS_sessionId"]

    for query in queries:
        try:
            try:
                text_doc = text_scenario_collection.find_one(query, sort=[("timestamp", -1)])
            except TypeError:
                text_doc = text_scenario_collection.find_one(query)
        except Exception:
            text_doc = None

        if not text_doc:
            continue

        session_id = None
        for field_name in [
            "combinedSessionId",
            "combined_session_id",
            "session_id",
            "sessionId",
            "individualSessionId",
            *apr_specific_fields,
        ]:
            if text_doc.get(field_name):
                session_id = text_doc.get(field_name)
                break

        if session_id:
            return str(session_id)

        print(
            f"Warning: Found {alignment_type} text document for pid {pid}, but no session id field was present."
        )
        return None

    print(f"Warning: Could not find {alignment_type} text session for pid {pid}.")
    return None


def get_alignment_compare_score(human_session_id, metadata, alignment_type):
    """Compare the current human session against the matching text session."""
    if not CALC_KDMAS:
        return None
    if not human_session_id:
        print(f"Warning: No human session_id available for {alignment_type} alignment.")
        return None
    if not ADEPT_URL or ADEPT_URL == "/":
        print("Warning: ADEPT_URL not set; skipping alignment compare calculation.")
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
        return float(score) if score is not None else None
    except Exception as e:
        print(f"Warning: Alignment compare request failed for {alignment_type} / pid {metadata.get('pid')}: {e}")
        return None


def compute_alignment_scores(metadata, sim_json, human_session_id=None):
    """Return MF/AF alignment fields using the Feb matcher flow as a standalone section."""
    prefix = build_env_prefix(metadata.get("env", ""))
    env_name = prefix.strip()
    if not env_name:
        env_name = metadata.get("env", "")

    human_alignment_session_id = human_session_id
    if CALC_KDMAS and human_alignment_session_id is None:
        _match_data, human_alignment_session_id = compute_openworld_match_data(sim_json, metadata)

    mf_alignment_score = get_alignment_compare_score(human_alignment_session_id, metadata, "MF")
    af_alignment_score = get_alignment_compare_score(human_alignment_session_id, metadata, "AF")

    return {
        f"MF Alignment_{env_name}": mf_alignment_score,
        f"AF Alignment_{env_name}": af_alignment_score,
    }


# ============================================================
# TEXT KDMAS
# ============================================================

DEFAULT_EVAL_NUM = 16
DEFAULT_EVAL_NAME = "April 2026 Evaluation"


def _is_april2026_text_doc(doc):
    """Return True when a text scenario document appears to belong to Apr 2026."""
    scenario_id = str(doc.get("scenario_id", "") or "")
    eval_name = str(doc.get("evalName", "") or "")
    eval_number = doc.get("evalNumber")

    return (
        eval_number == DEFAULT_EVAL_NUM
        or "April 2026" in eval_name
        or scenario_id.startswith("April2026")
    )



def _extract_kdmas_from_doc(doc):
    """Return the best available KDMA array from an Apr 2026 text scenario doc."""
    # Preferred Apr 2026 source: one combined block containing AF/MF/PS/SS.
    if isinstance(doc.get("combinedKdmas"), list) and doc.get("combinedKdmas"):
        return doc.get("combinedKdmas"), "combinedKdmas"

    # Apr 2026 split assess docs.
    merged = []
    for field_name in ["AF-PS_kdmas", "MF-PS_kdmas"]:
        value = doc.get(field_name)
        if isinstance(value, list) and value:
            merged.extend(value)
    if merged:
        return merged, "merged_april2026_assess_kdmas"

    # Legacy Feb-style fallback.
    for field_name in ["kdmas", "individualKdmas"]:
        value = doc.get(field_name)
        if isinstance(value, list) and value:
            return value, field_name

    return [], None



def extract_text_kdmas(metadata):
    """Join Apr 2026 text scenario KDMAs, preferring combinedKdmas and Apr assess arrays."""
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

    text_docs = []
    seen_ids = set()
    queries = []
    for pid_val in pid_candidates:
        # Prefer the Apr 2026 evaluation docs first.
        queries.append({"participantID": pid_val, "evalNumber": DEFAULT_EVAL_NUM})
        queries.append({"participantID": pid_val, "evalName": DEFAULT_EVAL_NAME})
        queries.append({"participantID": pid_val, "scenario_id": {"$regex": r"^April2026", "$options": "i"}})
        # Legacy fallback when eval fields are inconsistent.
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
        print(f"Warning: No text scenario documents found for pid {pid}.")
        return text_kdma_results

    preferred_docs = [doc for doc in text_docs if _is_april2026_text_doc(doc)]
    docs_to_use = preferred_docs if preferred_docs else text_docs

    # Prefer a doc with combinedKdmas since that is the clean Apr 2026 source.
    docs_to_use.sort(
        key=lambda d: (
            0 if (isinstance(d.get("combinedKdmas"), list) and d.get("combinedKdmas")) else 1,
            0 if _is_april2026_text_doc(d) else 1,
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

            for param in kdma.get("parameters", []):
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

        # combinedKdmas already contains the full Apr 2026 block, so stop once found.
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
        "data": sim_json,
    }

    analysis_doc = {
        "_id": doc_id,
        "pid": pid,
        "env": env,
        "scenario_id": metadata["scenario_id"],
        "openWorld": metadata["openWorld"],
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



# ============================================================
# MONGO OUTPUT
# ============================================================

def initialize_mongo():
    """Initialize Mongo output collections using the configured dashboard database."""
    global mongo_collection_analysis, mongo_collection_raw, text_scenario_collection

    if MongoClient is None:
        raise RuntimeError("pymongo is not installed. Install it to use --send_to_mongo.")

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
    action_analysis = extract_action_analysis(csv_rows, sim_json, metadata["env"], pid=metadata["pid"])
    triage_times = compute_patient_interactions(csv_rows)
    tag_colors = compute_last_applied_tags(csv_rows)
    expected_tag_color = derive_expected_tag_color(csv_rows)
    correct_tag_breakdown = compute_correct_tag_breakdown(expected_tag_color, tag_colors)
    tag_distribution = compute_tag_distribution(csv_rows, expected_tag_color)
    _, required_proc_for_injury = derive_required_injuries_and_procs(csv_rows)
    hem_metrics = compute_hemorrhage_control(csv_rows, required_proc_for_injury)
    patient_hc_time = compute_patient_hc_time(
        csv_rows,
        triage_times["patient_interactions"],
        required_proc_for_injury,
    )
    missed_hemorrhage_control = hem_metrics["missed_hemorrhage_control"]
    text_kdmas = extract_text_kdmas(metadata)
    match_data, human_session_id = compute_openworld_match_data(sim_json, metadata)
    alignment_scores = compute_alignment_scores(metadata, sim_json, human_session_id=human_session_id)

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
        text_kdmas=text_kdmas,
        alignment_scores=alignment_scores,
        match_data=match_data,
    )

    save_output(output_dir, filename, analysis_doc)

    logger.log(LogLevel.INFO, f"{'' if SEND_TO_MONGO else 'NOT '}Saving to database.")
    if SEND_TO_MONGO:
        save_to_mongo(raw_doc, analysis_doc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="APR 2026 probe matcher")
    parser.add_argument(
        "-i",
        "--input_dir",
        required=True,
        help="Directory containing simulation JSON files",
    )
    parser.add_argument(
        "-o",
        "--output_dir",
        default="output_april2026_probe_matcher",
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
        initialize_mongo()

    for root, _, files in os.walk(args.input_dir):
        for file in files:
            if file.endswith(".json"):
                json_path = os.path.join(root, file)
                print()
                logger.log(LogLevel.INFO, f"Processing file {json_path}")
                process_file(json_path, args.output_dir)