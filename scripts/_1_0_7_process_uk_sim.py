import os, csv, json
from pymongo import MongoClient
from datetime import datetime
import shutil
from decouple import config

def main(mongo_db):
    os.makedirs('tmp_uk_sim/phase1', exist_ok=True)
    os.makedirs('tmp_uk_sim/openworld', exist_ok=True)

    # Instantiate mongo client
    participant_log_collection = mongo_db['participantLog']

    # Go through the input directory and find all sub directories
    input_dir = 'uk_sim_files'
    sub_dirs = [name for name in os.listdir(input_dir) if os.path.isdir(os.path.join(input_dir, name))]
    # For each subdirectory, see if a json file exists
    for dir in sub_dirs:
        parent = os.path.join(input_dir, dir)
        # Get date of sim
        csv_path = os.path.join(parent, dir + '.csv')
        csv_file = open(csv_path, 'r', encoding='utf-8')
        reader = csv.reader(csv_file)
        next(reader)
        line2 = next(reader)
        sim_date = datetime.strptime(line2[2], "%m/%d/%Y %I:%M:%S %p")
        ph2_date = datetime(2025, 6, 2)
        # If date is after 6/2/2025, we are good! This is part of phase 2
        valid_date = sim_date > ph2_date
        # Remove files that have invalid pids
        pid = dir.split('_')[-1]
        try:
            pid = int(pid)
        except:
            print(f"Remove invalidly formatted pid {pid}, parent file {os.path.join(parent)}.")
            continue
        pid_in_log = participant_log_collection.count_documents({"ParticipantID": int(pid)}) > 0

        if not pid_in_log or not valid_date:
            print(f"Remove pid {pid}, parent directory {parent}, because it is not in the participant log or has an invalid date.")
            continue
        if os.path.isdir(parent):
            for f in os.listdir(parent):
                if '.json' in f:
                    # separate into different directories for quick, easy analysis
                    with open(os.path.join(parent, f), 'r', encoding='utf-8') as json_file:
                        json_data = json.load(json_file)
                        narrative = json_data["configData"]["narrative"]["narrativeDescription"]

                        dest_name = os.path.basename(parent)
                        # send to june probe matcher, but make sure it is in separate september set
                        if 'Desert' in narrative or 'Urban' in narrative:
                            dest_dir = os.path.join('tmp_uk_sim', 'openworld', dest_name)
                            if not os.path.exists(dest_dir):
                                shutil.copytree(parent, dest_dir)
                        elif 'Alpha' in narrative:
                            print('Skipping Alpha Squad TCCC analysis')
                            continue
                        elif 'DryRunEval' in narrative:
                            dest_dir = os.path.join('tmp_uk_sim', 'phase1', dest_name)
                            if not os.path.exists(dest_dir):
                                shutil.copytree(parent, dest_dir)
                        else:
                            print('Skipping unknown environment:', narrative)
                            continue

                elif '.html' in f or '.jpg' in f:
                    os.remove(os.path.join(parent, f))

    # run the other probe matchers
    print('Running open world probe matcher')
    os.system('python june2025_probe_matcher.py -i tmp_uk_sim/openworld')
    # move ph1 probe matcher to the right location for file access
    src_ph1 = os.path.join('PAST_EVALS', 'ph1_probe_matcher.py')
    tmp_ph1 = 'ph1_probe_matcher.py'
    if os.path.exists(src_ph1):
        shutil.move(src_ph1, tmp_ph1)
    else:
        print(f"Warning: {src_ph1} not found")
    print('Running phase 1 probe matcher')
    os.system('python ph1_probe_matcher.py -i tmp_uk_sim/phase1 -e 12')
    if os.path.exists(tmp_ph1):
        shutil.move(tmp_ph1, src_ph1)
    shutil.rmtree('tmp_uk_sim', ignore_errors=True)