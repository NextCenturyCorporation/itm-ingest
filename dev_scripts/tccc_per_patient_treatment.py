import os, csv, argparse, json

def load_json_data(file_loc):
        with open(file_loc, 'r', encoding='utf-8') as f:
            json_data = json.load(f)

        return json_data

def compute_treatment_count(input_directory):
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
                            f = open(to_analyze, 'r')
                            reader = csv.reader(f)
                            header = next(reader)

                            treatment_counts = {}
                            for line in reader:
                                if line[0] == 'TOOL_APPLIED' and 'Pulse Oximeter' not in line:
                                    p = line[header.index('PatientID')].split(' Root')[0]
                                    tool_type = line[header.index('ToolType')]
                                    if p not in treatment_counts:
                                        treatment_counts[p] = {}
                                    treatment_counts[p][tool_type] = treatment_counts[p].get(tool_type, 0) + 1
                            results.append([pid, treatment_counts])
                            f.close()

    return results

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Patient Treatment Counts')
    parser.add_argument('-i', '--input_directory', dest='input_directory', default='TCCC-Trainer', type=str)
    args = parser.parse_args()
    for pid, treatment_counts in compute_treatment_count(args.input_directory):
        print(pid, treatment_counts)

    