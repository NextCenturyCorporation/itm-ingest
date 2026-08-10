import os, yaml
SCENARIOS_FOLDER = 'phase2/april2026/observe'
def main(mongo_db):
    path = os.path.join(SCENARIOS_FOLDER, 'feb2026-adept-observe-MF-PS2.yaml')
    with open(path) as f:
        yaml_obj = yaml.safe_load(f)
        yaml_obj["evalNumber"] = 15
        yaml_obj["evalName"] = "Phase 2 Feb 2026 Collaboration"

    scenarios = mongo_db["scenarios"]
    scenario_id = yaml_obj.get("id")

    result = scenarios.replace_one(
        {"id": scenario_id},
        yaml_obj,
        upsert=True
    )