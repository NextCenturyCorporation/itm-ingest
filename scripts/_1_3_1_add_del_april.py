from delegation_survey.april_handmade_adms import main as april_medics
from delegation_survey.update_survey_config import version11_setup
from scripts._1_2_2_post_scenario_measures import main as post_scenario
def main(mongo_db):
    april_medics(mongo_db)
    version11_setup(auto_confirm=True)
    post_scenario(mongo_db)