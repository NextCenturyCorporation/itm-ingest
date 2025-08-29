from text_based_scenarios.convert_yaml_to_json_config_ph2 import main as gen_text_scenarios
from delegation_survey.september_handmade_adms import main as create_fake_adms
from delegation_survey.update_survey_config import version8_setup
def main(mongo_db):
    gen_text_scenarios(mongo_db)
    create_fake_adms(mongo_db)
    version8_setup(auto_confirm=True)