# ITM Ingest Tool
Sends processed data to the database

## Getting Started

### Creating a Virtual Environment
```
python3.8 -m venv ingest
```
Note: You may have to install venv tools on your system. For linux, the command is
```
sudo apt install python3.8-venv
```

To activate the virtual environment:

**Windows:**
```
ingest\Scripts\activate
```

**MacOS/Linux:**
```
source ingest/bin/activate
```

You are now in a virtual environment where you can install the requirements and run the main script.

To deactivate the environment, run
```
deactivate
```

### Installing from Requirements
```
pip install -r requirements.txt
```

## Running the Probe Matcher
The probe matcher takes in a path leading to a directory of Unity Simulator data. For each json file found, the script attempts to find matches within the actionList for each of the adept and soartech yaml files. 
d
To run the probe matcher, execute the following command:
```
python3 probe_matcher.py -i [path_to_directory]
```
Ensure that the path leads to the Unity Simulator data. The format should be: top-level -> id -> id -> json, with csvs directly under top-level. As the Unity file output organization format changes, the way of accessing this data may also change. For the metrics evaluation data, use the folder in this repo 'metrics-data'.

### Output
The probe matcher will output two json files for each input json found: one for soartech and one for adept. If SEND_TO_MONGO is true, these json files (and the raw jsons found) will be sent to the mongo database

## Data in Repository
| Directory | Explanation |
| - | - |
| `metrics-data` | Contains all of the valid simulator outputs in the same organizational structure unity outputs. |
| `adept-evals` | The yaml files for each adept evaluation scenario |
| `soartech-evals` | The yaml files for each soartech evaluation scenario |

# Deplolyment Script Usage

To utilize this function, you will need to manually run the deployment script.
We will eventually have a Jenkins job that will run the script whenever ingest is updated.
Also if you would like to run a new script you will need to modify the script that is being called in deployment script and bump the version.

The script will only run if the version is a newer version of the db, the script also create the collection for the version if it doesn't exist yet. Set your .env file to point to the instances of the TA1 servers you have running locally. 
