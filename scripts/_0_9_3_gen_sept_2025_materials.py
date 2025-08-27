from text_based_scenarios.convert_yaml_to_json_config_ph2 import main as gen_text_scenarios
from delegation_survey.september_handmade_adms import main as create_fake_adms
def main(mongo_db):
    #gen_text_scenarios(mongo_db)
    create_fake_adms(mongo_db)
