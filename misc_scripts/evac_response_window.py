import os, csv, copy, argparse, json
from datetime import datetime, timedelta

CSV_TIME_FMT = "%m/%d/%Y %I:%M:%S %p"
JSON_TIME_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"
HERE = os.path.dirname(os.path.abspath(__file__))


def load_json_data(file_loc):
        with open(file_loc, 'r', encoding='utf-8') as f:
            json_data = json.load(f)

        return json_data

def parse_json(json_data):
    timestamps = ''
    answer = []
    if json_data:
            for action in json_data['actionList']:
                if action.get('actionType') == 'Question' and 'evacuate' in action.get('question', '').lower():
                    timestamps = action['timestamp']
                    answer.append(action['answer'])
    return timestamps, answer

def listify_data(file_loc):
    f = open(file_loc, 'r')
    reader = csv.reader(f)
    data = []
    header = next(reader)
    voice_capture = header.index('VoiceCaptureMessage')
    timestamp = header.index('Timestamp')

    for line in reader:
        if line[0][0] == '#':
            continue # skip "comments"
        if line[0] == 'VOICE_CAPTURE':
            data.append([line[voice_capture], line[timestamp]])
    f.close()
    return data

def parse_session_start(file_loc):
    f = open(file_loc, 'r')
    reader = csv.reader(f)
    header = next(reader)
    ts_idx = header.index('Timestamp')

    for line in reader:
        if line[0] == 'SESSION_START':
            time = datetime.strptime(line[ts_idx], CSV_TIME_FMT)

    f.close()
    return time


def voice_capture_window(json_timestamp, csv_data):
    window_timestamps = []
    json_anchor = datetime.strptime(json_timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
    window_start = json_anchor - timedelta(seconds=90)

    for voice_data in csv_data:
        parsed_time = datetime.strptime(voice_data[1], "%m/%d/%Y %I:%M:%S %p")
        if window_start <= parsed_time <= json_anchor:
            window_timestamps.append(voice_data)

    return window_timestamps

def heuristic_scorer(time_window, question_answer):
    score = {}
    segments = {}
    heuristic_terms = {'evac': 2, 'casualty': 2, 'patient': 1, 'this one': 1, 'that one': 1, 'i think': 1, 'probably': 1, 'not sure': 1, 'first one': 2, 'second one': 2, 'chest wound': 1, 'stomach': 1, 'abdominal': 1, 'bleeding': 1, 'take this': 2, 'take her': 2, 'take him': 2, 'everyone': 2, 'treated': 3, "i'm done": 3, 'finished': 3, 'this guy': 2, 'that guy': 2, 'this girl': 2, 'that girl': 2, 'evacuation': 2, 'chest': 1, 'needle': 1}
    for message in time_window:
        segments[message[0]] = message
        text = message[0].lower()
        if any(q.lower() in text for q in question_answer):
                if message[0] not in score:
                    score[message[0]] = 0
                score[message[0]] += 2
        for term in heuristic_terms:
            if term in text:
                if message[0] not in score:
                    score[message[0]] = 0
                score[message[0]] += heuristic_terms[term]
    if not score:
        return None

    qualifying = [i for i in score if score[i] >= 2]
    if not qualifying:
        return None
    
    min_message = min(qualifying, key=lambda m: datetime.strptime(segments[m][1], "%m/%d/%Y %I:%M:%S %p"))
    
    return segments[min_message]

def get_confidence(scored_time, llm_time, action_time):
    signals = [t for t in [scored_time, llm_time, action_time] if t is not None]

    if len(signals) < 2:
        return "Low"

    spread = (max(signals) - min(signals)).total_seconds()

    if spread <= 5:
        confidence = 'High'
    elif spread <= 30:
        confidence = 'Medium'
    else:
        confidence = 'Low'

    return confidence

def start_time(scored_time, llm_time, action_time):
    voice = [t for t in [scored_time, llm_time] if t is not None]

    if not voice:
        return action_time

    voice_done = min(voice)

    if action_time is not None and action_time > voice_done:
        return action_time

    return voice_done


def parse_last_action(json_data, anchor):
    SUPPLEMENTAL = {"Nasal Trumpet", "Blanket", "IV - Blood", "Antibiotics", "Fentanyl Lollipop"}
    latest = None
    latest_str = None
    for action in json_data['actionList']:
        if action.get('actionType') not in ('Treatment', 'Tag'):
            continue

        if action.get('treatment') in SUPPLEMENTAL:
            continue

        current = datetime.strptime(action["timestamp"], JSON_TIME_FMT)
        anchor_dt = datetime.strptime(anchor, JSON_TIME_FMT)

        if current < anchor_dt and (latest is None or current > latest):
            latest = current
            latest_str = action["timestamp"]
    
    return latest_str



def compute_evac_windows(input_directory):
    CUTOFF = 645
    TOLERANCE = 15
    llm_data = load_json_data(os.path.join(HERE, 'llm_picks.json'))
    results = []
    for dir in os.listdir(input_directory):
        if dir != '.DS_Store':
            parent = os.path.join(input_directory, dir)
            for file in os.listdir(parent):
                if '.csv' in file:
                    to_analyze = os.path.join(parent, file)
                    json_path = to_analyze.replace('.csv', '.json')
                    if os.path.exists(json_path):
                            json_object = load_json_data(json_path)
                            pid = json_object['participantId'] 
                            timestamps , question_answer = parse_json(json_object)
                            if not timestamps:
                                continue

                            anchor = datetime.strptime(timestamps, JSON_TIME_FMT)
                            action_time = parse_last_action(json_object, timestamps)
                            voice_data = listify_data(to_analyze)
                            window = voice_capture_window(timestamps, voice_data)
                            scored = heuristic_scorer(window, question_answer)
                            llm_pick = llm_data.get(pid)
                            scored_time = None
                            llm_time = None

                            if scored is not None:
                                scored_time = datetime.strptime(scored[1], CSV_TIME_FMT)
                            if llm_pick is not None:
                                llm_time = datetime.strptime(llm_pick["timestamp"], CSV_TIME_FMT)
                            if action_time is not None:
                                action_time = datetime.strptime(action_time, JSON_TIME_FMT)

                            session_start = parse_session_start(to_analyze)
                            cutoff_dt = session_start + timedelta(seconds=CUTOFF)
                            gap = (cutoff_dt - action_time).total_seconds() if action_time is not None else None
                            if gap is not None and gap <= TOLERANCE and anchor >= cutoff_dt:
                                start = cutoff_dt
                                confidence = "High"
                            else:
                                confidence = get_confidence(scored_time, llm_time, action_time)
                                start = start_time(scored_time, llm_time, action_time)

                            window_seconds = None
                            if start is not None:
                                window_seconds = (anchor - start).total_seconds()
                            results.append([pid, window_seconds, confidence])
    
    return results

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Estimate TCCC evac decision windows')
    parser.add_argument('-i', '--input_directory', dest='input_directory', default='input_tccc', type=str)
    args = parser.parse_args()
    for pid, window_seconds, confidence in compute_evac_windows(args.input_directory):
        print(pid, window_seconds, confidence)

    