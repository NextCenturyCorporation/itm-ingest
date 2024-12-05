from pymongo import MongoClient
from decouple import config
import importlib
import os
import re
from packaging import version

class ScriptManager:
    def __init__(self, mongo_url, db_name, scripts_dir = 'scripts'):
        self.client = MongoClient(mongo_url)
        self.db = self.client[db_name]
        self.scripts_dir = scripts_dir
        self.version_collection = "itm_version"

    def get_current_db_version(self):
        collection = self.db[self.version_collection]
        version_obj = collection.find_one()
        return version_obj['version'] if version_obj else "0.0.0"

    def update_db_version(self, new_version: str):
        collection = self.db[self.version_collection]
        version_obj = collection.find_one()
        if version_obj is None:
            collection.insert_one({"version": new_version})
        else:
            version_obj['version'] = new_version
            collection.replace_one({"_id": version_obj["_id"]}, version_obj)

    def discover_update_scripts(self):
        # pulls in all scripts from scripts dir
        updates = []
        
        # regex to match naming convention
        pattern = r'^_(\d+)_(\d+)_(\d+)_.*\.py$'
        
        for filename in os.listdir(self.scripts_dir):
            match = re.match(pattern, filename)
            if match and not filename.startswith('__'):
                major, minor, patch = match.groups()
                version_str = f"{major}.{minor}.{patch}"
                
                # convert filename for import
                module_name = f"{self.scripts_dir}.{filename[:-3]}"
                
                '''
                    Note: Your script MUST have 'def main', this function
                    should take mongo_db as a parameter
                '''
                try:
                    module = importlib.import_module(module_name)
                    main_function = getattr(module, 'main')
                    if main_function: 
                        updates.append((version_str, module_name, main_function))
                except ImportError as e:
                    print(f"Warning: Could not import {module_name}: {e}")
                
        return sorted(updates, key=lambda x: version.parse(x[0]))

    def get_pending_scripts(self):
        # determine which scripts need to be run 
        current_version = version.parse(self.get_current_db_version())
        return [
            update for update in self.discover_update_scripts()
            if version.parse(update[0]) > current_version
        ]

    def run_updates(self):
        # run scripts in order
        pending_scripts = self.get_pending_scripts()
        
        if not pending_scripts:
            print("Database is up to date.")
            return

        print(f"Found {len(pending_scripts)} pending updates")
        
        for version_str, module_name, function_name in pending_scripts:
            print(f"Running update {version_str} from {module_name}.{function_name}")
            try:
                module = importlib.import_module(module_name)
                update_function = getattr(module, function_name)
                # mongo instance passed
                update_function(self.db)
                self.update_db_version(version_str)
                print(f"Successfully completed script {version_str}")
            except Exception as e:
                print(f"Error running script {version_str}: {e}")
                raise  # stops the update process on err
        final_version = self.get_current_db_version()
        print(f"\nDatabase has been updated to version {final_version}")

def main():
    mongo_url = config('MONGO_URL')
    script_manager = ScriptManager(mongo_url, 'dashboard')
    script_manager.run_updates()

if __name__ == "__main__":
    main()