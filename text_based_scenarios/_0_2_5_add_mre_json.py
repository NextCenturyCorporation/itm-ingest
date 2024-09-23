import json
import os

def add_mre_json(mongo_db):
    text_based_config = mongo_db['textBasedConfig']
    
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    json_folder = os.path.join(current_script_dir, 'mre-json-files')
    
    # Get all JSON files in the folder
    json_files = [f for f in os.listdir(json_folder) if f.endswith('.json')]
    
    for file in json_files:
        file_path = os.path.join(json_folder, file)
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        data['eval'] = 'mre-eval'
        data['scenario_id'] = data['title']
        # Insert the data into the collection
        result = text_based_config.insert_one(data)
        print(f"Inserted document: {file}")
    