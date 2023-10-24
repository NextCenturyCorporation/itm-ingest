import json

def read_json_file(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data

def is_json_file(file_path):
    # file extension is ".json"
    return file_path.lower().endswith('.json')

# json files will have unique session id. return value of key "session_id"
def get_json_session_id(json_data):
    try:
        session_id = json_data.get("session_id")
        if session_id is not None:
            return session_id
        else:
            raise KeyError("Key 'session_id' not found in the JSON data.")
    except KeyError as e:
        raise e

