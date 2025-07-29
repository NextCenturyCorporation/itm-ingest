from delegation_survey.phase2_covert_adm_to_del_materials import main as convert_adms
from delegation_survey.update_survey_config import version7_setup
from text_based_scenarios.convert_yaml_to_json_config_ph2 import main as text_scenarios
def main(mongo_db):
    adm_runs_collection = mongo_db['admTargetRuns']

    delete_result = adm_runs_collection.delete_many({
        'evalNumber': 9,
        'scenario': 'July2025-AF3-eval'
    })
    print(f"deleted {delete_result.deleted_count} incorrect AF3 runs")
    
    # eval number got saved as a string for some reason, convert to number
    adm_runs_collection.update_many(
        {'evalNumber': '9'},
        {"$set": {"evalNumber": 9}}  
    )

    # remove long string of numbers/letters after __ to clean adm names
    adm_runs_collection.update_many(
        {'evalNumber': 9, 'adm_name': {'$regex': '__'}},
        [{'$set': {'adm_name': {'$arrayElemAt': [{'$split': ['$adm_name', '__']}, 0]}}}]
    )

    # re generate text scenarios
    text_scenarios(mongo_db)

    adm_medic_collection = mongo_db['admMedics']

    # delete adm medics
    adm_medic_collection.delete_many({
        'evalNumber': 9
    })

    # regen adm medics
    convert_adms(mongo_db, 9)

    # regen survey v7
    version7_setup(auto_confirm=True)

