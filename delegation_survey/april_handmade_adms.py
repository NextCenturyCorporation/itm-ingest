import os, yaml, json
from delegation_survey.phase2_covert_adm_to_del_materials import get_unique_medic_name 
from delegation_survey.phase2_covert_adm_to_del_materials import find_scene_by_probe_id
def main(mongo_db):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(script_dir, 'templates', 'phase2_april_template.json')
    f = open(template_path, 'r', encoding='utf-8')
    template = json.load(f)
    medic_collection = mongo_db['admMedics']
    medic_collection.delete_many({'evalNumber': 16})