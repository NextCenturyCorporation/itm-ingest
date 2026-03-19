import json
import csv
import sys
import os
from datetime import datetime


def load_config_data(config_file_path):
    """Load configuration data from external JSON file"""
    try:
        with open(config_file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Config file '{config_file_path}' not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in config file '{config_file_path}'.")
        sys.exit(1)


def convert_timestamp(timestamp_str):
    """Convert timestamp from 'M/D/YYYY h:mm:ss AM/PM' to ISO format 'YYYY-MM-DDTHH:MM:SS.fffZ'"""
    try:
        # Parse the timestamp
        dt = datetime.strptime(timestamp_str, '%m/%d/%Y %I:%M:%S %p')
        # Convert to ISO format with milliseconds and Z suffix
        return dt.strftime('%Y-%m-%dT%H:%M:%S.%fZ')[:-3] + 'Z'
    except Exception as e:
        print(f"Warning: Could not parse timestamp '{timestamp_str}': {e}")
        return timestamp_str  # Return original if parsing fails


def parse_csv(csv_file_path, ctx):
    """Parse CSV file and return list of dictionaries"""
    try:
        data = []
        with open(csv_file_path, 'r', newline='', encoding='utf-8') as csvfile:
            # Use csv.DictReader to properly handle comma-separated values
            reader = csv.DictReader(csvfile)

            header = reader.fieldnames

            # Count total rows
            total_rows = 0

            # Parse data rows
            for row in reader:
                total_rows += 1
                timestamp = row.get('ElapsedTime', '').strip()
                eventname = row.get('EventName', '').strip()

                # Session Duration Start
                if int(timestamp) > 0 and eventname != "Participant ID":
                    ctx["elapsed_time"] = timestamp

                if eventname == "PATIENT_RECORD":
                    patient_name = row.get('PatientID', '')
                    print("DEBUG: Found Patient - ", patient_name)
                    img_entry = {
                        "name": patient_name,
                        "filename": f"{ctx['session_id']}_{ctx['participant_id']}_{patient_name}.jpg"
                    }

                    ctx["img_data"].append(img_entry)

                data.append(row)

        return data
    except FileNotFoundError:
        print(f"Error: CSV file '{csv_file_path}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error parsing CSV file: {e}")
        sys.exit(1)


def string_to_bool(value):
    """Convert string to boolean (True/False)"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 'on')
    return False


def parse_injury_name(injury_name):
    if not injury_name:
        return "", ""

    parts = injury_name.split()
    if len(parts) < 2:
        return injury_name, ""

    abbreviation_mapping = {
        'R': 'Right',
        'L': 'Left',
        'C': 'Center'
    }

    # Process each word in the treatment location (all except last)
    treatment_location_parts = []
    for part in parts[:-1]:
        if part in abbreviation_mapping:
            treatment_location_parts.append(abbreviation_mapping[part])
        else:
            treatment_location_parts.append(part)

    # Join the processed parts to form the expanded treatment location
    treatment_location = ' '.join(treatment_location_parts)
    injury_type = parts[-1]

    return treatment_location, injury_type


def Treatment_To_Type(treatment):
    treatment_mapping = {
        'tourniquet': 'Tourniquet',
        'chestSeal': 'Chest Seal Projector',
        'decompressionNeedle': 'Decompression Needle',
        'Gauze Wrap': 'Gauze Dressing'
    }

    if treatment in treatment_mapping:
        return treatment_mapping[treatment]
    return treatment


def Tag_To_Type(tag_color):
    tag_mapping = {
        'green': 'MINIMAL',
        'yellow': 'DELAYED',
        'red': 'IMMEDIATE',
        'black': 'EXPECTANT',
        'grey': 'EXPECTANT'
    }
    return tag_mapping[tag_color]


def create_action_list(csv_data):
    """Create action list from pulse and treatment data"""
    action_list = []

    pulse_events_found = 0
    treatment_events_found = 0
    tag_events_found = 0
    actions_created = 0

    for i, row in enumerate(csv_data):
        event_name = row.get('EventName', '').strip()
        next_row = csv_data[i + 1] if i + 1 < len(csv_data) else None

        # Handle PULSE_TAKEN events
        if event_name == 'PULSE_TAKEN':
            pulse_events_found += 1
            print(f"DEBUG: Found PULSE_TAKEN event")

            pulse_type = row.get('PatientPulse', '').strip()
            patient_id = row.get('PatientID', '')
            timestamp = row.get('Timestamp', '')

            print(f"DEBUG:   PatientPulse: '{pulse_type}'")
            print(f"DEBUG:   PatientID: '{patient_id}'")
            print(f"DEBUG:   Timestamp: '{timestamp}'")

            # Convert timestamp
            converted_timestamp = convert_timestamp(timestamp)
            print(f"DEBUG:   Converted timestamp: '{converted_timestamp}'")

            if pulse_type:
                actions_created += 1
                print(f"DEBUG: Creating pulse action with data: '{pulse_type}'")
                pulse_action = {
                    "actionType": "Pulse",
                    "casualty": patient_id,
                    "treatment": "",
                    "treatmentLocation": "",
                    "injuryType": "",
                    "successfulTreatment": False,
                    "tagColor": "",
                    "tagType": "",
                    "pulse": pulse_type.split('_')[-1] if '_' in pulse_type else pulse_type,
                    "breathing": "",
                    "SpO2": "",
                    "question": "",
                    "answerChoices": [],
                    "answer": "",
                    "movedBeforeClearedByCommand": False,
                    "timestamp": converted_timestamp
                }
                action_list.append(pulse_action)
                print(f"DEBUG: Added pulse action to list")

        # Handle INJURY_TREATED events
        elif event_name == 'INJURY_TREATED':
            treatment_events_found += 1
            print(f"DEBUG: Found INJURY_TREATED event")

            # Extract treatment information from the row
            treatment = row.get('InjuryRequiredProcedure', '').strip()
            gauze_treatment = next_row.get('ToolType', '').strip()
            if treatment == 'woundpack':
                treatment = gauze_treatment
            treatment = Treatment_To_Type(treatment)
            treatment_location = row.get('InjuryBodyRegion', '').strip()
            injury_name = row.get('InjuryName', '').strip()
            treatment_location, injury_type = parse_injury_name(injury_name)
            injury_treated = row.get('InjuryTreatmentComplete', '').strip()

            patient_id = row.get('PatientID', '')
            timestamp = row.get('Timestamp', '')

            print(f"DEBUG:   Treatment: '{treatment}'")
            print(f"DEBUG:   TreatmentLocation: '{treatment_location}'")
            print(f"DEBUG:   InjuryType: '{injury_type}'")
            print(f"DEBUG:   InjuryTreatmentComplete: '{injury_treated}'")
            print(f"DEBUG:   PatientID: '{patient_id}'")
            print(f"DEBUG:   Timestamp: '{timestamp}'")

            converted_timestamp = convert_timestamp(timestamp)
            print(f"DEBUG:   Converted timestamp: '{converted_timestamp}'")

            # Create treatment action
            if treatment != 'none':
                actions_created += 1
                print(f"DEBUG: Creating treatment action with data: '{treatment}'")
                # Convert injury treatment complete to boolean
                successful_treatment = string_to_bool(injury_treated)
                treatment_action = {
                    "actionType": "Treatment",
                    "casualty": patient_id,
                    "treatment": treatment,
                    "treatmentLocation": treatment_location,
                    "injuryType": injury_type,
                    "successfulTreatment": successful_treatment,
                    "tagColor": "",
                    "tagType": "",
                    "pulse": "",
                    "breathing": "",
                    "SpO2": "",
                    "question": "",
                    "answerChoices": [],
                    "answer": "",
                    "movedBeforeClearedByCommand": False,
                    "timestamp": converted_timestamp
                }
                action_list.append(treatment_action)
                print(f"DEBUG: Added treatment action to list")

        # Handle Tag Events
        elif event_name == 'TAG_APPLIED':
            tag_events_found += 1
            print(f"DEBUG: Found TAG_APPLIED event")

            # Extract tag information from the row
            tag_type = row.get('TagType', '').strip()
            patient_id = row.get('PatientID', '')
            timestamp = row.get('Timestamp', '')

            print(f"DEBUG:   PatientID: '{patient_id}'")
            print(f"DEBUG:   TagType: '{tag_type}'")
            print(f"DEBUG:   Timestamp: '{timestamp}'")

            converted_timestamp = convert_timestamp(timestamp)
            print(f"DEBUG:   Converted timestamp: '{converted_timestamp}'")

            # Create tag action
            if tag_type:
                actions_created += 1
                print(f"DEBUG: Creating Tag action with data: '{tag_type}'")
                tag_action = {
                    "actionType": "Tag",
                    "casualty": patient_id,
                    "treatment": "",
                    "treatmentLocation": "",
                    "injuryType": "",
                    "successfulTreatment": False,
                    "tagColor": tag_type,
                    "tagType": Tag_To_Type(tag_type),
                    "pulse": "",
                    "breathing": "",
                    "SpO2": "",
                    "question": "",
                    "answerChoices": [],
                    "answer": "",
                    "movedBeforeClearedByCommand": False,
                    "timestamp": converted_timestamp
                }
                action_list.append(tag_action)
                print(f"DEBUG: Added tag action to list")

        # Handle TOOL_APPLIED events
        elif event_name == 'TOOL_APPLIED':
            treatment_events_found += 1
            print(f"DEBUG: Found TOOL_APPLIED event")

            # Extract tool information from the row
            Tool = row.get('ToolType', '').strip()
            patient_id = row.get('PatientID', '')
            timestamp = row.get('Timestamp', '')

            print(f"DEBUG:   Treatment: '{Tool}'")
            print(f"DEBUG:   PatientID: '{patient_id}'")
            print(f"DEBUG:   Timestamp: '{timestamp}'")

            converted_timestamp = convert_timestamp(timestamp)
            print(f"DEBUG:   Converted timestamp: '{converted_timestamp}'")

            # Create tool action
            if Tool == "Nasal Airway":
                actions_created += 1
                print(f"DEBUG: Creating tool action with data: '{Tool}'")
                tool_action = {
                    "actionType": "Treatment",
                    "casualty": patient_id,
                    "treatment": "Nasal Trumpet",
                    "treatmentLocation": "Nostril",
                    "injuryType": "None",
                    "successfulTreatment": False,
                    "tagColor": "",
                    "tagType": "",
                    "pulse": "",
                    "breathing": "",
                    "SpO2": "",
                    "question": "",
                    "answerChoices": [],
                    "answer": "",
                    "movedBeforeClearedByCommand": False,
                    "timestamp": converted_timestamp
                }
                action_list.append(tool_action)
                print(f"DEBUG: Added tool action to list")
            if Tool == "Blanket":
                actions_created += 1
                print(f"DEBUG: Creating tool action with data: '{Tool}'")
                tool_action = {
                    "actionType": "Treatment",
                    "casualty": patient_id,
                    "treatment": "Blanket",
                    "treatmentLocation": "None",
                    "injuryType": "None",
                    "successfulTreatment": False,
                    "tagColor": "",
                    "tagType": "",
                    "pulse": "",
                    "breathing": "",
                    "SpO2": "",
                    "question": "",
                    "answerChoices": [],
                    "answer": "",
                    "movedBeforeClearedByCommand": False,
                    "timestamp": converted_timestamp
                }
                action_list.append(tool_action)
                print(f"DEBUG: Added tool action to list")

        elif event_name == "DISARM_PATIENT_WEAPON":
            patient_id = row.get('PatientID', '')
            timestamp = row.get('Timestamp', '')

            print(f"DEBUG:   PatientID: '{patient_id}'")
            print(f"DEBUG:   Timestamp: '{timestamp}'")

            converted_timestamp = convert_timestamp(timestamp)
            print(f"DEBUG:   Converted timestamp: '{converted_timestamp}'")

            disarm_action = {
                "actionType": "DisarmPatientWeapon",
                "casualty": patient_id,
                "treatment": "",
                "treatmentLocation": "",
                "injuryType": "",
                "successfulTreatment": False,
                "tagColor": "",
                "tagType": "",
                "pulse": "",
                "breathing": "",
                "SpO2": "",
                "question": "",
                "answerChoices": [],
                "answer": "",
                "movedBeforeClearedByCommand": False,
                "timestamp": converted_timestamp
            }
            action_list.append(disarm_action)
            print(f"DEBUG: Added disarm action to list")

    print(f"DEBUG: Processed {len(csv_data)} rows")
    print(f"DEBUG: Found {pulse_events_found} PULSE_TAKEN events")
    print(f"DEBUG: Found {treatment_events_found} INJURY_TREATED events")
    print(f"DEBUG: Found {tag_events_found} TAG_APPLIED events")
    print(f"DEBUG: Created {len(action_list)} actions total")
    return action_list


def create_output_json(config_data, action_list, ctx, output_file_path):
    """Create output JSON file with config data and parsed CSV data"""

    h, rem = divmod(int(ctx["elapsed_time"]) // 1000, 3600)
    m, s = divmod(rem, 60)

    scenarioDuration = f"{h:02d}h:{m:02d}m:{s:02d}s"

    output_data = {
        "configData": config_data,
        "actionList": action_list,
        "images": ctx["img_data"],
        "sessionId": ctx["session_id"],
        "participantId": ctx["participant_id"],
        "scenarioDuration": scenarioDuration
    }

    try:
        with open(output_file_path, 'w') as f:
            json.dump(output_data, f, indent='    ')
        print(f"Output JSON file created: {output_file_path}")
        print(f"Action list contains {len(action_list)} items")
    except Exception as e:
        print(f"Error writing output file: {e}")
        sys.exit(1)


def main(config_file_path=None, csv_file_path=None):
    # Use provided arguments or fall back to command line args
    if config_file_path is None or csv_file_path is None:
        if len(sys.argv) != 3:
            print("Usage: python csv_to_json.py <config_json_file> <csv_file>")
            print("Example: python csvToJson.py February2026 OW Urban.json aeff758c-b241-4a9d-afea-35f5367b68da_202602120.csv")
            sys.exit(1)

        config_file_path = sys.argv[1]
        csv_file_path = sys.argv[2]

    filename = os.path.basename(csv_file_path)
    name_without_ext = os.path.splitext(filename)[0]
    session_id, participant_id = name_without_ext.split("_")

    ctx = {
        "participant_id": participant_id,
        "session_id": session_id,
        "elapsed_time": "",
        "img_data": []
    }

    print("Session ID:", ctx["session_id"])
    print("Participant ID:", ctx["participant_id"])

    # Get output file name (same as CSV but with .json extension)
    output_file_path = os.path.splitext(csv_file_path)[0] + '.json'

    # Load config data
    config_data = load_config_data(config_file_path)

    # Parse CSV data
    csv_data = parse_csv(csv_file_path, ctx)

    # Create action list
    action_list = create_action_list(csv_data)

    # Create output JSON file
    create_output_json(config_data, action_list, ctx, output_file_path)


if __name__ == "__main__":
    main()