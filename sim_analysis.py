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
    Match Feb probe matcher logic.
    """
    interactions = {}
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

        interactions.setdefault(patient, [])

        if cur_p is None:
            cur_p = patient
            start_time = last_time if last_time != 0 else t
            last_time = t
            continue

        if cur_p != patient:
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
        for start, end in segs:
            patient_ms += max(0.0, end - start)
        total_time_ms += patient_ms
        per_patient_seconds[patient] = patient_ms / 1000.0

    return {
        "interactions": per_patient_seconds,
        "total": total_time_ms / 1000.0,
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

    return {
        "hemorrhage_control": completed,
        "hemorrhage_control_time": time_to,
    }


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

def build_output_documents(metadata, event_totals, action_analysis, sim_json):
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

    print("\n=== METADATA ===")
    print(json.dumps(metadata, indent=2))
    print("=== EVENT TOTALS ===")
    print(json.dumps(event_totals, indent=2))
    print("=== ACTION ANALYSIS ===")
    print(json.dumps(action_analysis, indent=2))

    raw_doc, analysis_doc = build_output_documents(
        metadata, event_totals, action_analysis, sim_json
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