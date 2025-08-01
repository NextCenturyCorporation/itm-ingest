import sys
import importlib.util
import os
import traceback
import re
from pymongo import MongoClient
from decouple import config


def parse_arg(arg):
    """
    Determines what type the extra argument (if provided) should be
    int, float, bool, or string (fallback)
    """
    try:
        return int(arg)
    except ValueError:
        pass
    
    try:
        return float(arg)
    except ValueError:
        pass
    
    if arg.lower() in ('true', 'false'):
        return arg.lower() == 'true'
    
    # string fallback
    return arg

def run_script(version_number, extra_args):

    if not re.match(r'^\d{3}$', version_number):
        print(f"Error: '{version_number}' is invalid. Script number must be exactly 3 digits.")
        print("Example: 067 (not 67 or 0067)")
        return
    
    major = version_number[0]
    minor = version_number[1]
    patch = version_number[2]
    
    script_pattern = f"_{major}_{minor}_{patch}_"
    
    scripts_dir = 'scripts'
    script_file = None
    
    for filename in os.listdir(scripts_dir):
        if script_pattern in filename and filename.endswith('.py'):
            script_file = filename
            break
    
    if script_file is None:
        print(f"No script found matching version number {version_number}")
        return
    
    print(f"Found script: {script_file}")

    parsed_args = [parse_arg(arg) for arg in extra_args]

    if parsed_args:
        print(f"Additional arguments: {parsed_args}")
    
    script_path = os.path.join(scripts_dir, script_file)
    script_name = script_file[:-3] 
    
    spec = importlib.util.spec_from_file_location(script_name, script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    mongo_url = config('MONGO_URL')
    client = MongoClient(mongo_url)
    db = client['dashboard']
    
    try:
        print(f"Running script {script_file}...")
        if hasattr(module, 'main'):
            module.main(db, *parsed_args)
            print(f"Script {script_file} ran successfully.")
        else:
            print(f"Error: Script {script_file} does not have a main function.")
    except Exception as e:
        print(f"Error running script {script_file}: {e}")
        print("\nTraceback:")
        traceback.print_exc()
    finally:
        client.close()

def main():
    if len(sys.argv) < 2:
        print("Usage: python redo.py <script number> [additional arguments...]")
        print("Example: python redo.py 067")
        print("Example with args: python redo.py 067 arg1 arg2 arg3")
        return
    
    script_number = sys.argv[1]
    extra_args = sys.argv[2:] if len(sys.argv) > 2 else []
    
    run_script(script_number, extra_args)

if __name__ == "__main__":
    main()