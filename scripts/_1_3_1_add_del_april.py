from delegation_survey.april_handmade_adms import main as april_medics
from delegation_survey.update_survey_config import version11_setup
from scripts._1_2_2_post_scenario_measures import main as post_scenario
from scripts._1_3_0_april_text import main as rerun_april_text
def main(mongo_db):
    # convert adms to del materials
    april_medics(mongo_db)
    # compile materials
    version11_setup(auto_confirm=True)
    # post scenario measures questions
    post_scenario(mongo_db)
    # re ingest text scenarios because of ADEPT requests
    rerun_april_text(mongo_db)