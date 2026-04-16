import argparse
import csv
import json
import os
import re
from datetime import datetime

SEND_TO_MONGO = False

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
    "june": "jun",
    "july": "jul",
    "august": "aug",
    "september": "sept",
    "october": "oct",
    "november": "nov",
    "december": "dec",
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


def get_env_prefix(env):
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

def get_triage_time_seconds(csv_rows):
    """Compute overall triage time from elapsed time values."""
    if len(csv_rows) <= 1:
        return 0.0

    try:
        start = safe_float(csv_rows[0].get("ElapsedTime", 0))
        end = safe_float(csv_rows[-2].get("ElapsedTime", 0))
        return max(0.0, (end - start) / 1000.0)
    except Exception:
        return 0.0


def count_assessment_actions(csv_rows):
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


def count_treatment_actions(csv_rows):
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


def extract_event_totals(csv_rows, env):
    """Build the eventTotals block."""
    prefix = get_env_prefix(env)
    assessments = count_assessment_actions(csv_rows)
    treatments = count_treatment_actions(csv_rows)

    return {
        f"{prefix}Triage_time": get_triage_time_seconds(csv_rows),
        f"{prefix}Assess_total": assessments["count"],
        f"{prefix}Treat_total": treatments["count"],
    }


# ============================================================
# PATIENT INTERACTION LOGIC
# ============================================================

def find_patients_engaged(csv_rows):
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


def find_time_per_patient(csv_rows):
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


def get_patients_in_order(csv_rows, engagement_order):
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


def get_last_applied_tags(csv_rows):
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
    engaged_counts = find_patients_engaged(csv_rows)
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


def get_dragged_patients(csv_rows, min_drag_distance=1.0):
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

def extract_action_analysis(csv_rows, sim_json, env):
    """Build the actionAnalysis block."""
    del sim_json  # currently unused

    prefix = get_env_prefix(env)
    action_analysis = {}

    assessments = count_assessment_actions(csv_rows)
    treatments = count_treatment_actions(csv_rows)
    triage_times = find_time_per_patient(csv_rows)
    expected_tag_color = derive_expected_tag_color(csv_rows)
    required_injuries, required_proc_for_injury = derive_required_injuries_and_procs(csv_rows)
    treatment_submetrics_required = compute_treatment_submetrics_required(csv_rows, required_injuries)
    tags_applied = get_last_applied_tags(csv_rows)
    dragged_patients = get_dragged_patients(csv_rows, min_drag_distance=1.0)

    aggregate_patient_metrics = compute_patient_averages(
        csv_rows, assessments, treatments, triage_times
    )
    patient_order_engaged = aggregate_patient_metrics["patient_order_engaged"]

    tag_metrics = compute_tag_metrics(expected_tag_color, tags_applied)
    hem_metrics = compute_hemorrhage_control(csv_rows, required_proc_for_injury)

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

    patients_in_order = get_patients_in_order(csv_rows, patient_order_engaged)

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

    return raw_doc, analysis_doc


def save_output(output_dir, filename, analysis_doc):
    """Write the analysis document to disk."""
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{filename}_analysis.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(analysis_doc, f, indent=2)

    print(f"Saved analysis: {out_path}")


# ============================================================
# PIPELINE EXECUTION
# ============================================================

def process_file(json_path, output_dir):
    """Process a single run and write its analysis output."""
    filename = os.path.basename(json_path).replace(".json", "")

    with open(json_path, "r", encoding="utf-8") as f:
        sim_json = json.load(f)

    csv_path = json_path.replace(".json", ".csv")
    csv_rows = load_csv_rows(csv_path)

    metadata = extract_run_metadata(sim_json, filename)
    event_totals = extract_event_totals(csv_rows, metadata["env"])
    action_analysis = extract_action_analysis(csv_rows, sim_json, metadata["env"])
    triage_times = find_time_per_patient(csv_rows)
    tag_colors = get_last_applied_tags(csv_rows)
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
    )

    save_output(output_dir, filename, analysis_doc)

    if SEND_TO_MONGO:
        # Insert raw_doc and analysis_doc here when Mongo support is enabled.
        _ = raw_doc


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulation analysis script")
    parser.add_argument(
        "-i",
        "--input_dir",
        required=True,
        help="Directory containing simulation JSON files",
    )
    parser.add_argument(
        "-o",
        "--output_dir",
        default="output_sim_analysis",
        help="Directory for analysis JSON files",
    )
    args = parser.parse_args()

    for root, _, files in os.walk(args.input_dir):
        for file in files:
            if file.endswith(".json"):
                process_file(os.path.join(root, file), args.output_dir)
