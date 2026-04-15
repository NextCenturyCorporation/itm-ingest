import os
import json
import csv
import argparse
import re
from datetime import datetime

# ============================================================
# CONFIGURATION / FLAGS
# ============================================================

SEND_TO_MONGO = False  # wire up later if needed

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
    },
}

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
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_bool_from_csv(value) -> bool:
    """
    Convert CSV string-ish booleans to actual bool.
    """
    if value is None:
        return False
    s = str(value).strip().lower()
    return s in ("true", "1", "yes", "y", "t")


def clean_patient_name(value):
    """
    Match probe matcher behavior:
    strip trailing ' Root' and trim whitespace.
    """
    if value is None:
        return ""
    return str(value).split(" Root")[0].strip()


def is_valid_patient(patient_name):
    """
    Match the probe matcher filtering for obvious non-patient entities.
    """
    if not patient_name:
        return False
    invalid_tokens = ["Level Core", "Simulation", "Player"]
    return not any(token in patient_name for token in invalid_tokens)


def timestamp_to_seconds(ts_value):
    """
    Parse CSV Timestamp strings like:
      2/23/2026 3:23:50 PM
    """
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


def load_csv_rows(csv_path):
    """
    Load the sim CSV as a list of dictionaries.
    Returns [] if the file is missing.
    """
    if not csv_path or not os.path.exists(csv_path):
        return []

    with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


def get_env_prefix(env):
    env_lower = str(env).lower()
    if "desert" in env_lower:
        return "Desert "
    if "urban" in env_lower:
        return "Urban "
    return ""


def get_env_key(env):
    env_lower = str(env).lower()
    if "desert" in env_lower:
        return "desert"
    if "urban" in env_lower:
        return "urban"
    return ""


def extract_pid_from_filename(filename):
    """
    For filenames like:
      uuid_202602118
    return:
      202602118
    """
    parts = filename.split("_")
    if len(parts) >= 2 and parts[1]:
        return parts[1]
    return parts[0] if parts else filename


def build_probe_matcher_style_id(pid, env):
    return f"{pid}_ow_{env if env else 'unknown'}"


# ============================================================
# METADATA EXTRACTION
# ============================================================

def extract_month_year_label(*texts):
    """
    Look for strings like:
      - February 2026
      - Feb 2026
      - June 2025
    Return:
      - short_label: feb2026 / jun2025 / etc.
      - pretty_label: Feb2026 / Jun2025 / etc.
    """
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


def extract_run_metadata(sim_json, filename):
    """
    Extract:
      - pid
      - env
      - scenario_id
      - openWorld
    """
    pid = extract_pid_from_filename(filename)

    config = sim_json.get("configData", {})
    narrative = config.get("narrative", {})
    scenario_data = config.get("scenarioData", {})

    scene = str(config.get("scene", ""))
    narrative_desc = str(narrative.get("narrativeDescription", ""))
    scenario_name = str(scenario_data.get("name", ""))
    bucket = str(config.get("CACIUploadToS3Bucket", ""))

    text_blob = " ".join([scene, narrative_desc, scenario_name, bucket]).lower()

    open_world = ("ow" in text_blob or "open world" in text_blob)

    terrain = "unknown"
    if "desert" in text_blob:
        terrain = "desert"
    elif "urban" in text_blob:
        terrain = "urban"

    short_label, pretty_label = extract_month_year_label(
        narrative_desc, bucket, scenario_name
    )

    if open_world and terrain != "unknown":
        if short_label:
            env = f"{short_label}-{terrain}-openworld"
        else:
            env = f"{terrain}-openworld"
    elif terrain != "unknown":
        env = terrain
    else:
        env = "unknown"

    if open_world and terrain != "unknown":
        if pretty_label:
            scenario_id = f"{pretty_label}-OW_{terrain}"
        else:
            scenario_id = f"OW_{terrain}"
    else:
        scenario_id = "unknown"

    return {
        "pid": pid,
        "env": env,
        "scenario_id": scenario_id,
        "openWorld": open_world
    }


# ============================================================
# EVENT TOTALS (MATCH PROBE MATCHER)
# ============================================================

def get_triage_time_seconds(csv_rows):
    """
    Match Feb probe matcher:
    use first row ElapsedTime and near-last row ElapsedTime.
    """
    if len(csv_rows) > 1:
        try:
            start = safe_float(csv_rows[0].get("ElapsedTime", 0))
            end = safe_float(csv_rows[-2].get("ElapsedTime", 0))
            return max(0.0, (end - start) / 1000.0)
        except Exception:
            return 0.0
    return 0.0


def count_assessment_actions(csv_rows):
    """
    Match Feb probe matcher:
    dedupe same assessment event type if within 5 seconds.
    """
    count = 0
    last_done = {}
    per_patient = {}

    for row in csv_rows:
        ev = row.get("EventName")
        if ev in ASSESSMENT_EVENTS:
            ts = row.get("Timestamp")
            ts_sec = timestamp_to_seconds(ts)
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
    """
    Match Feb probe matcher:
    count TOOL_APPLIED except Pulse Oximeter.
    """
    count = 0
    per_patient = {}

    for row in csv_rows:
        ev = row.get("EventName")
        if ev == "TOOL_APPLIED":
            tool = str(row.get("ToolType", "") or "")
            if "Pulse Oximeter" in tool:
                continue

            count += 1
            patient = clean_patient_name(row.get("PatientID", ""))
            if is_valid_patient(patient):
                per_patient[patient] = per_patient.get(patient, 0) + 1

    return {"count": count, "per_patient": per_patient}


def extract_event_totals(csv_rows, env):
    prefix = get_env_prefix(env)

    triage_time = get_triage_time_seconds(csv_rows)
    assessments = count_assessment_actions(csv_rows)
    treatments = count_treatment_actions(csv_rows)

    return {
        f"{prefix}Triage_time": triage_time,
        f"{prefix}Assess_total": assessments["count"],
        f"{prefix}Treat_total": treatments["count"]
    }


# ============================================================
# PER-PATIENT INTERACTION METRICS
# ============================================================

def find_patients_engaged(csv_rows):
    """
    Match Feb probe matcher.
    """
    engagement_order = []
    treated = []

    for row in csv_rows:
        ev = row.get("EventName")
        if ev in ENGAGEMENT_EVENTS:
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

    engaged_unique = len(set(engagement_order))
    treated_unique = len(set(treated))

    return {
        "engaged": engaged_unique,
        "treated": treated_unique,
        "order": simple_order,
    }


def find_time_per_patient(csv_rows):
    """
    Match the legacy new_14/new_16 patient interaction logic as closely as possible
    while working on the newer event-log CSV format.

    Returns:
      - interactions: {patient: total_seconds}
      - total: total seconds across all patient interaction segments
      - patient_interactions: rich interaction structure
      - interaction_time: flattened {patient: total_seconds}
      - interaction_visits: flattened {patient: visit_count}
      - patient_order: unique patient visit order, matching the interaction pass
    """
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
            end_ms = float(end)
            if end_ms < start_ms:
                end_ms = start_ms
            clean_segments.append([start_ms, end_ms])
            patient_ms += max(0.0, end_ms - start_ms)

        total_time_ms += patient_ms
        total_seconds = round(patient_ms / 1000.0, 3)

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
    """
    Match probe matcher breakout order.
    """
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
# PER-PATIENT TRUTH / ACTION FIELDS
# ============================================================

def derive_expected_tag_color(csv_rows):
    expected_tag_color = {}

    for row in csv_rows:
        if row.get("EventName") == "PATIENT_RECORD":
            patient = clean_patient_name(row.get("PatientID", ""))
            triage_level = str(row.get("PatientTriageLevel", "")).strip().upper()

            if patient and triage_level in TRIAGE_LEVEL_TO_TAG_COLOR:
                expected_tag_color[patient] = TRIAGE_LEVEL_TO_TAG_COLOR[triage_level]

    return expected_tag_color


def derive_required_injuries_and_procs(csv_rows):
    required_injuries = {}
    required_proc_for_injury = {}

    for row in csv_rows:
        if row.get("EventName") == "INJURY_RECORD":
            patient = clean_patient_name(row.get("PatientID", ""))
            injury = str(row.get("InjuryName", "")).strip()
            proc = str(row.get("InjuryRequiredProcedure", "")).strip()

            if patient and injury:
                required_injuries.setdefault(patient, []).append(injury)
                required_proc_for_injury[(patient, injury)] = proc

    return required_injuries, required_proc_for_injury


def get_last_applied_tags(csv_rows):
    tags_applied = {}

    for row in csv_rows:
        if row.get("EventName") == "TAG_APPLIED":
            patient = clean_patient_name(row.get("PatientID", ""))
            tag = str(row.get("TagType", "")).strip().lower()

            if patient:
                tags_applied[patient] = tag

    return tags_applied


def normalize_tag_color(tag):
    tag = str(tag or "").strip().lower()
    if tag == "yellow_orange":
        return "yellow"
    if tag == "green_blue":
        return "green"
    return tag


def compute_tag_distribution(csv_rows, expected_tag_color):
    """
    Match the legacy tag_distribution.csv concept:
      - count every TAG_APPLIED color per patient
      - compute percent correct per patient from full tag history

    The legacy analyzers also had a special-case 'kim_yellow' bump for one
    metro-chaotic patient. That legacy exception is not applied here because
    open-world runs use the standard patient IDs and CSV-derived truth labels.
    """
    tag_distribution_red = {}
    tag_distribution_yellow = {}
    tag_distribution_green = {}
    tag_distribution_gray = {}
    tag_distribution_black = {}
    percent_correct_per_patient = {}

    counts_by_patient = {}

    for row in csv_rows:
        if row.get("EventName") != "TAG_APPLIED":
            continue

        patient = clean_patient_name(row.get("PatientID", ""))
        if not is_valid_patient(patient):
            continue

        raw_tag = str(row.get("TagType", "")).strip().lower()
        tag = normalize_tag_color(raw_tag)

        if tag not in {"red", "yellow", "green", "gray", "black"}:
            continue

        if patient not in counts_by_patient:
            counts_by_patient[patient] = {
                "red": 0,
                "yellow": 0,
                "green": 0,
                "gray": 0,
                "black": 0,
            }
        counts_by_patient[patient][tag] += 1

    for patient, counts in counts_by_patient.items():
        total_tags = (
            counts["red"]
            + counts["yellow"]
            + counts["green"]
            + counts["gray"]
            + counts["black"]
        )

        expected = normalize_tag_color(expected_tag_color.get(patient))
        correct_tags = counts.get(expected, 0) if expected else 0
        percent_correct = round(correct_tags / max(1, total_tags), 4)

        tag_distribution_red[patient] = counts["red"]
        tag_distribution_yellow[patient] = counts["yellow"]
        tag_distribution_green[patient] = counts["green"]
        tag_distribution_gray[patient] = counts["gray"]
        tag_distribution_black[patient] = counts["black"]
        percent_correct_per_patient[patient] = percent_correct

    return {
        "tag_distribution_red": tag_distribution_red,
        "tag_distribution_yellow": tag_distribution_yellow,
        "tag_distribution_green": tag_distribution_green,
        "tag_distribution_gray": tag_distribution_gray,
        "tag_distribution_black": tag_distribution_black,
        "percent_correct_per_patient": percent_correct_per_patient,
    }


def compute_correct_tag_breakdown(expected_tag_color, tags_applied):
    """
    Legacy-style correct tag breakdown adapted to CSV-derived triage truth.

    Returns flattened fields:
      - correct_tags_total
      - correct_tags_correct
      - correct_tags_over
      - correct_tags_under
      - correct_tags_critical
    """
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
            truth = expected
            guess = applied

            if truth == "black":
                over_triage += 1
            elif guess == "black":
                critical_triage += 1
            elif truth == "gray":
                over_triage += 1
            elif guess == "gray":
                critical_triage += 1
            elif truth == "red":
                under_triage += 1
            elif guess == "red":
                over_triage += 1
            elif truth == "yellow":
                under_triage += 1
            elif guess == "yellow":
                over_triage += 1

        total += 1

    return {
        "correct_tags_total": total,
        "correct_tags_correct": correct,
        "correct_tags_over": over_triage,
        "correct_tags_under": under_triage,
        "correct_tags_critical": critical_triage,
    }


def get_evaced_patient_names(sim_json, env):
    env_key = get_env_key(env)
    answer_map = EVAC_ANSWER_TO_PATIENT.get(env_key, {})

    evaced_answers = []

    for action in sim_json.get("actionList", []):
        if action.get("actionType") == "Question":
            question = str(action.get("question", "")).lower()
            if "evacuate" in question:
                answer = action.get("answer")
                if answer:
                    evaced_answers.append(str(answer).strip())

    return {answer_map[a] for a in evaced_answers if a in answer_map}


# ============================================================
# AGGREGATE SCORED OUTPUTS
# ============================================================

def compute_tag_metrics(expected_tag_color, tags_applied):
    """
    Compute:
      - Tag_ACC
      - Tag_Expectant
    """
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
        any_gray = any(tags_applied.get(p) == "gray" for p in expectant_patients)
        tag_expectant = "Yes" if any_gray else "No"

    return {
        "tag_acc": tag_acc,
        "tag_expectant": tag_expectant,
    }


def compute_hemorrhage_control(csv_rows, required_proc_for_injury):
    """
    Match Feb probe matcher:
    all injuries whose required procedure is hemorrhage control
    must be completed.
    """
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

                if len(to_complete[patient]) == 0:
                    del to_complete[patient]

    completed = 1 if len(to_complete) == 0 else 0
    time_to = None
    if completed == 1 and start_time_sec is not None and end_time_sec is not None:
        time_to = end_time_sec - start_time_sec

    # Match legacy missed_hemorrhage_control semantics:
    # count remaining hemorrhage-control-required injuries, not patients.
    missed_hemorrhage_control = sum(len(v) for v in to_complete.values())

    return {
        "hemorrhage_control": completed,
        "hemorrhage_control_time": time_to,
        "missed_hemorrhage_control": missed_hemorrhage_control,
    }


def compute_patient_hc_time(csv_rows, patient_interactions, required_proc_for_injury):
    """
    Match legacy new_14/new_16 per-patient hemorrhage-control timing pattern.

    For each completed hemorrhage-control treatment that matches a required
    hemorrhage procedure, find the interaction visit segment that contains that
    treatment event and record the time from the start of that visit segment
    until the treatment completion.
    """
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

        # CSV ElapsedTime is already in milliseconds for these OW event logs.
        # patient_interactions[...]["all_data"] is also stored in milliseconds,
        # so do NOT multiply by 1000 here or the times will never match a visit segment.
        try:
            tx = safe_float(row.get("ElapsedTime"), 0.0)
        except Exception:
            tx = 0.0

        req = [patient, req_proc, injury]
        times_controlled.setdefault(patient, []).append({
            "procedure": req,
            "time": tx,
        })

    control_times = {}

    for patient, controlled_list in times_controlled.items():
        interaction_times = patient_interactions.get(patient, {}).get("all_data", [])
        last_t2 = 0.0
        last_t1 = 0.0

        for controlled in controlled_list:
            tx = float(controlled["time"])
            for (t1, t2) in interaction_times:
                if t1 == last_t2:
                    # Match the defensive logic in the legacy analyzers.
                    t1 = last_t1
                last_t1 = t1
                last_t2 = t2

                if tx >= t1 and tx <= t2:
                    time_to_control = (tx - t1) / 1000.0
                    control_times.setdefault(patient, []).append({
                        "procedure": controlled["procedure"],
                        "time": round(time_to_control, 3),
                    })
                    break

    return control_times


def compute_triage_performance(csv_rows, required_injuries):
    """
    Match Feb probe matcher:
      score = correct_completed / (total_tools_applied + misses) * 100
    """
    remaining = {p: set(inj_list) for p, inj_list in required_injuries.items()}
    correct_completed = 0
    total_tools_applied = 0

    for row in csv_rows:
        ev = row.get("EventName")

        if ev == "INJURY_TREATED":
            patient = clean_patient_name(row.get("PatientID", ""))
            injury = str(row.get("InjuryName", "")).strip()
            completed = safe_bool_from_csv(row.get("InjuryTreatmentComplete"))

            if completed and patient in remaining and injury in remaining[patient]:
                remaining[patient].remove(injury)
                correct_completed += 1
                if len(remaining[patient]) == 0:
                    del remaining[patient]

        if ev == "TOOL_APPLIED":
            tool = str(row.get("ToolType", "") or "")
            if "Pulse Oximeter" in tool:
                continue
            total_tools_applied += 1

    misses = sum(len(s) for s in remaining.values())
    denom = max(1, total_tools_applied + misses)
    return (correct_completed / denom) * 100.0


def compute_patient_averages(csv_rows, assessments, treatments, triage_times):
    """
    Compute:
      - Assess_patient
      - Treat_patient
      - Triage_time_patient
      - Engage_patient
    """
    engaged_counts = find_patients_engaged(csv_rows)
    patients_engaged = engaged_counts["engaged"]
    patients_treated = engaged_counts["treated"]
    patient_order_engaged = engaged_counts["order"]

    engagement_times = list(
        {p: patient_order_engaged.count(p) for p in set(patient_order_engaged)}.values()
    )

    engage_patient = sum(engagement_times) / max(1, len(engagement_times))
    assess_patient = assessments["count"] / max(1, patients_engaged)
    treat_patient = treatments["count"] / max(1, patients_treated)
    triage_time_patient = triage_times["total"] / max(1, patients_engaged)

    return {
        "engage_patient": engage_patient,
        "assess_patient": assess_patient,
        "treat_patient": treat_patient,
        "triage_time_patient": triage_time_patient,
        "patients_engaged": patients_engaged,
        "patient_order_engaged": patient_order_engaged,
    }


# ============================================================
# ACTION ANALYSIS BUILDER
# ============================================================

def extract_action_analysis(csv_rows, sim_json, env):
    """
    Build actionAnalysis fields matching Feb probe matcher style.
    """
    prefix = get_env_prefix(env)
    action_analysis = {}

    assessments = count_assessment_actions(csv_rows)
    treatments = count_treatment_actions(csv_rows)
    triage_times = find_time_per_patient(csv_rows)

    expected_tag_color = derive_expected_tag_color(csv_rows)
    required_injuries, required_proc_for_injury = derive_required_injuries_and_procs(csv_rows)
    tags_applied = get_last_applied_tags(csv_rows)
    evaced_patient_names = get_evaced_patient_names(sim_json, env)

    aggregate_patient_metrics = compute_patient_averages(
        csv_rows, assessments, treatments, triage_times
    )
    patient_order_engaged = aggregate_patient_metrics["patient_order_engaged"]

    tag_metrics = compute_tag_metrics(expected_tag_color, tags_applied)
    hem_metrics = compute_hemorrhage_control(csv_rows, required_proc_for_injury)
    triage_performance = compute_triage_performance(csv_rows, required_injuries)

    action_analysis[f"{prefix}Assess_patient"] = aggregate_patient_metrics["assess_patient"]
    action_analysis[f"{prefix}Treat_patient"] = aggregate_patient_metrics["treat_patient"]
    action_analysis[f"{prefix}Triage_time_patient"] = aggregate_patient_metrics["triage_time_patient"]
    action_analysis[f"{prefix}Engage_patient"] = aggregate_patient_metrics["engage_patient"]

    action_analysis[f"{prefix}Tag_ACC"] = tag_metrics["tag_acc"]
    action_analysis[f"{prefix}Tag_Expectant"] = tag_metrics["tag_expectant"]

    action_analysis[f"{prefix}Hemorrhage control"] = hem_metrics["hemorrhage_control"]
    action_analysis[f"{prefix}Hemorrhage control_time"] = hem_metrics["hemorrhage_control_time"]

    action_analysis[f"{prefix}Triage Performance"] = triage_performance

    patients_in_order = get_patients_in_order(csv_rows, patient_order_engaged)

    clean_patient_order_engaged = []
    for patient in patient_order_engaged:
        if patient not in clean_patient_order_engaged:
            clean_patient_order_engaged.append(patient)

    for i, sim_name in enumerate(patients_in_order):
        name = f"{prefix}Patient{i + 1}"

        action_analysis[f"{name}_time"] = round(
            triage_times["interactions"].get(sim_name, 0), 3
        )

        try:
            action_analysis[f"{name}_order"] = clean_patient_order_engaged.index(sim_name) + 1
        except Exception:
            action_analysis[f"{name}_order"] = "N/A"

        action_analysis[f"{name}_evac"] = "Yes" if sim_name in evaced_patient_names else "No"
        action_analysis[f"{name}_assess"] = assessments["per_patient"].get(sim_name, 0)
        action_analysis[f"{name}_treat"] = treatments["per_patient"].get(sim_name, 0)
        action_analysis[f"{name}_tag"] = tags_applied.get(sim_name, "None")
        action_analysis[f"{name}_triage_truth"] = expected_tag_color.get(sim_name, None)
        action_analysis[f"{name}_required_injuries"] = required_injuries.get(sim_name, [])

    return action_analysis


# ============================================================
# OUTPUT DOCUMENT BUILDERS
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
    pid = metadata["pid"]
    env = metadata["env"]
    doc_id = build_probe_matcher_style_id(pid, env)

    raw_doc = {
        "_id": doc_id,
        "pid": pid,
        "env": env,
        "scenario_id": metadata["scenario_id"],
        "openWorld": metadata["openWorld"],
        "data": sim_json
    }

    analysis_doc = {
        "_id": doc_id,
        "pid": pid,
        "env": env,
        "scenario_id": metadata["scenario_id"],
        "openWorld": metadata["openWorld"],
        "timestamp": int(datetime.utcnow().timestamp() * 1000),
        "eventTotals": event_totals,
        "actionAnalysis": action_analysis
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
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{filename}_analysis.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(analysis_doc, f, indent=2)

    print(f"Saved: {out_path}")


# ============================================================
# MAIN PROCESSING PIPELINE
# ============================================================

def process_file(json_path, output_dir):
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
    required_injuries, required_proc_for_injury = derive_required_injuries_and_procs(csv_rows)
    hem_metrics = compute_hemorrhage_control(csv_rows, required_proc_for_injury)
    patient_hc_time = compute_patient_hc_time(
        csv_rows,
        triage_times["patient_interactions"],
        required_proc_for_injury,
    )
    missed_hemorrhage_control = hem_metrics["missed_hemorrhage_control"]

    print("\n=== METADATA ===")
    print(json.dumps(metadata, indent=2))
    print("=== EVENT TOTALS ===")
    print(json.dumps(event_totals, indent=2))
    print("=== ACTION ANALYSIS ===")
    print(json.dumps(action_analysis, indent=2))
    print("=== PATIENT INTERACTIONS ===")
    print(json.dumps(triage_times["patient_interactions"], indent=2))
    print("=== INTERACTION TIME ===")
    print(json.dumps(triage_times["interaction_time"], indent=2))
    print("=== INTERACTION VISITS ===")
    print(json.dumps(triage_times["interaction_visits"], indent=2))
    print("=== PATIENT ORDER ===")
    print(json.dumps(triage_times["patient_order"], indent=2))
    print("=== TAG COLORS ===")
    print(json.dumps(tag_colors, indent=2))
    print("=== CORRECT TAG BREAKDOWN ===")
    print(json.dumps(correct_tag_breakdown, indent=2))
    print("=== TAG DISTRIBUTION ===")
    print(json.dumps(tag_distribution, indent=2))
    print("=== PATIENT HC TIME ===")
    print(json.dumps(patient_hc_time, indent=2))
    print("=== MISSED HEMORRHAGE CONTROL ===")
    print(json.dumps(missed_hemorrhage_control, indent=2))

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
        # TODO: insert raw_doc into humanSimulatorRaw
        # TODO: insert analysis_doc into humanSimulator
        pass


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sim Analysis Starter Script")

    parser.add_argument(
        "-i", "--input_dir",
        required=True,
        help="Directory containing sim JSON files"
    )

    parser.add_argument(
        "-o", "--output_dir",
        default="output_sim_analysis",
        help="Directory for output JSON files"
    )

    args = parser.parse_args()

    for root, dirs, files in os.walk(args.input_dir):
        for file in files:
            if file.endswith(".json"):
                json_path = os.path.join(root, file)
                process_file(json_path, args.output_dir)