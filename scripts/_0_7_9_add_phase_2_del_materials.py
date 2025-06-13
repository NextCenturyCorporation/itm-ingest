from delegation_survey.phase2_covert_adm_to_del_materials import main as add_del
from scripts._0_7_6_add_phase_2_text_scenarios import main as rerun_text
def main(mongo_db):
    add_del(mongo_db)
    rerun_text(mongo_db)