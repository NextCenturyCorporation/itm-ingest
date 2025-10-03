from delegation_survey.uk_convert_adms_for_delegation import main as adm_conversion
from text_based_scenarios.convert_yaml_to_json_config_ph1 import main as text_based
def main(mongo_db):
    text_based()
    adm_conversion(mongo_db)