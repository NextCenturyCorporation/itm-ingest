import os, yaml, json, csv, copy
from delegation_survey.phase2_covert_adm_to_del_materials import get_unique_medic_name
from delegation_survey.phase2_covert_adm_to_del_materials import find_scene_by_probe_id
from delegation_survey.phase2_covert_adm_to_del_materials import convert_adm

# only grab the files once, pass to create_adm
def load_scenario_yamls(yaml_dir):
    scenarios = {}
    for filename in os.listdir(yaml_dir):
        if not filename.endswith(".yaml"):
            continue
        yaml_path = os.path.join(yaml_dir, filename)
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                scenarios[data["id"]] = data
        except Exception as e:
            print(f"Error reading {filename}: {e}")
    return scenarios


def create_adm(template, medic_collec, scenario_id, target_id, subpop_id, probe_responses, yaml_data):
    doc = copy.deepcopy(template)
    medic_name = get_unique_medic_name(medic_collec, 16)

    doc.update(
        {
            "name": medic_name,
            "title": " ",
            "target": target_id,
            "scenarioIndex": scenario_id,
            "admAuthor": "kitware",
            "evalNumber": 16,
            "admName": "Oracle",
            "subpop": subpop_id,
        }
    )

    doc["elements"][0]["rows"] = []
    doc["elements"][0]["title"] = " "

    doc["elements"][0]["name"] = medic_name

    # get rid of boiler plate
    for i, element in enumerate(doc["elements"]):
        if "name" in element and "Test medic 1" in element["name"]:
            doc["elements"][i]["name"] = element["name"].replace("Test medic 1", medic_name)
        if "title" in element and "Test medic 1" in element["title"]:
            doc["elements"][i]["title"] = element["title"].replace("Test medic 1", medic_name)

    choices = [action["unstructured"] for action in yaml_data["scenes"][0]["action_mapping"]]
    doc["elements"][0]["options"] = choices

    doc["elements"][0]["scenarioDescription"] = yaml_data["scenes"][0]["state"]["threat_state"]["unstructured"]

    for probe in probe_responses:
        scene = find_scene_by_probe_id(yaml_data, probe["probe_id"])

        if not scene:
            print(f"Error: did not find matching probe in yaml file for {probe['probe_id']}")
            continue

        choice_text = None
        for action in scene["action_mapping"]:
            if action["choice"] == probe["response"]:
                choice_text = action["unstructured"]
                break

        action_options = [action["unstructured"] for action in scene["action_mapping"]]

        row_data = {
            "choice": choice_text,
            "probe_unstructured": scene["state"]["unstructured"],
            "options": action_options,
            "probe_id": probe["probe_id"],
            "choice_id": probe["response"],
            "scenario_id": scenario_id,
        }

        doc["elements"][0]["rows"].append(row_data)

    print(f"Creating medic document with name: {medic_name}")
    medic_collec.insert_one(doc)


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
        yaml_dir = os.path.join("phase2", "april2026", "observe")
        scenario_map = load_scenario_yamls(yaml_dir)
        for row in reader:
            # creates array of probe id and probe response pairs (skips over blank values)
            probe_responses = [
                {"probe_id": col, "response": value.strip()}
                for col, value in row.items()
                if col.startswith("Probe ") and value.strip()
            ]
            yaml_data = scenario_map[row["scenario_id"]]
            create_adm(
                template,
                medic_collection,
                row["scenario_id"],
                row["target_id"],
                row["subpop_id"],
                probe_responses,
                yaml_data,
            )


    mf_ps_runs = list(mongo_db["admTargetRuns"].find({"scenario": "Feb2026-MF-PS2-observe"}))
    for adm in mf_ps_runs:
        convert_adm(
            adm,
            adm["scenario"],
            adm["alignment_target"],
            adm["adm_name"],
            template,
            medic_collection,
            16,
            os.path.join("april2026", "observe")
        )

    # reuse feb af-ps2
    af_ps_runs = list(medic_collection.find({"evalNumber": 15, "scenarioIndex": "Feb2026-AF-PS2-observe", "admName": {"$regex": "Mistral"}}))
    for doc in af_ps_runs:
        new_doc = copy.deepcopy(doc)
        del new_doc["_id"]  # need to gen new _id or else mongo error
        new_doc["evalNumber"] = 16
        medic_collection.insert_one(new_doc)


