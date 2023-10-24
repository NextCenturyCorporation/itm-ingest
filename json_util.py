import json

def read_json_file(file_path):
    """
    Read JSON data from a file.

    Args:
        file_path: Path to the JSON file.

    Returns:
        Parsed JSON data.
    """
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data

def is_json_file(file_path):
    """
    Check if a file has a JSON file extension.

    Args:
        file_path: Path to the file.

    Returns:
        True if the file has a ".json" extension, otherwise False.
    """
    return file_path.lower().endswith('.json')

def get_json_session_id(json_data):
    """
    Extract the session_id from JSON data.

    Args:
        json_data: JSON data with a "session_id" key.

    Returns:
        The value of the "session_id" key.
    """
    try:
        session_id = json_data.get("session_id")
        if session_id is not None:
            return session_id
        else:
            raise KeyError("Key 'session_id' not found in the JSON data.")
    except KeyError as e:
        raise e
