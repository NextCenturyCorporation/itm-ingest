import os, yaml

    
SCENARIOS_FOLDER = 'phase2/june2026/admrun'


def main(mongo_db):
    files = sorted(os.listdir(SCENARIOS_FOLDER))

    for file in files:
        path = os.path.join(SCENARIOS_FOLDER, file)
        with open(path) as f:
            yaml_obj = yaml.safe_load(f)
            yaml_obj["evalNumber"] = 17
            yaml_obj["evalName"] = "Phase 2 June 2026 Collaboration"

            scenarios = mongo_db["scenarios"]
            scenario_id = yaml_obj.get("id")

            if scenario_id:
                result = scenarios.replace_one(
                    {"id": scenario_id},
                    yaml_obj,
                    upsert=True
                )
                if result.matched_count:
                    print(f"Replaced: {file}")
                else:
                    print(f"Uploaded: {file}")
