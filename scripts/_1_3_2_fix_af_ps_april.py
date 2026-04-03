import json
def main(mongo_db):
    with open("delegation_survey/templates/phase2_april_template.json", "r", encoding="utf-8") as f:
        template = json.load(f) 

    af_ps_medics = list(mongo_db["admMedics"].find({"evalNumber": 16, "scenarioIndex": 'Feb2026-AF-PS2-observe'}))
    config = mongo_db["delegationConfig"].find_one({"_id": "delegation_v11.0"})
    page_index_by_name = {page.get("name"): i for i, page in enumerate(config["survey"]["pages"])}

    for medic in af_ps_medics:
        del medic["elements"][1:5]
        medic["elements"][1:1] = template["elements"][1:5]
        medic_name = medic["name"]

        for el in medic["elements"][1:5]:
            if "name" in el and "Test medic 1" in el["name"]:
                el["name"] = el["name"].replace("Test medic 1", medic_name)
            if "title" in el and "Test medic 1" in el["title"]:
                el["title"] = el["title"].replace("Test medic 1", medic_name)

        mongo_db["admMedics"].update_one(
            {"_id": medic["_id"]},
            {"$set": {"elements": medic["elements"]}}
        )

        idx = page_index_by_name.get(medic_name)
        if idx is not None:
            config["survey"]["pages"][idx] = medic
        else:
            print("Didn't find the page to replace, this shouldn't happen!")

    mongo_db["delegationConfig"].update_one(
        {"_id": "delegation_v11.0"},
        {"$set": {"survey.pages": config["survey"]["pages"]}}
    )
