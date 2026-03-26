import os, yaml, json, csv
from delegation_survey.phase2_covert_adm_to_del_materials import get_unique_medic_name
from delegation_survey.phase2_covert_adm_to_del_materials import find_scene_by_probe_id


def create_adm(template, scenario_id, target_id, subpop_id, probe_responses):
    pass


def main(mongo_db):
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # delete existing medics so this can be re run if need be
    medic_collection = mongo_db["admMedics"]
    medic_collection.delete_many({"evalNumber": 16})

    template_path = os.path.join(script_dir, "templates", "phase2_april_template.json")
    with open(template_path, "r", encoding="utf-8") as f:
        template = json.load(f)

    csv_path = os.path.join(script_dir, "oracle_table_example.csv")
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        adms = []
        for row in reader:
            # creates array of probe id and probe response pairs (skips over blank values)
            probe_responses = [
                {"probe_id": col, "response": value.strip()}
                for col, value in row.items()
                if col.startswith("Probe ") and value.strip()
            ]
            adm = create_adm(
                template,
                row["scenario_id"],
                row["target_id"],
                row["subpop_id"],
                probe_responses,
            )
            adms.append(adm)

    medic_collection.insert_many(adms)
