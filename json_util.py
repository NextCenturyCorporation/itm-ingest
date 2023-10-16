import json

def read_json_file(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data

def is_json_file(file_path):
    # file extension is ".json"
    return file_path.lower().endswith('.json')