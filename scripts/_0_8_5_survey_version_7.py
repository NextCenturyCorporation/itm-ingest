from delegation_survey.phase2_covert_adm_to_del_materials import main as convert_adms
from delegation_survey.update_survey_config import version7_setup
def main(mongo_db):
    adm_runs_to_keep = [
        'ALIGN-ADM-Ph2-ComparativeRegression-Mistral-7B-Instruct-v0.3__479d4f7a-f2e5-4f1a-a975-686af0f6be70',
        'ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3__a954f40b-db28-44d9-8cf3-c7c7d99ace27',
        'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-Mistral-7B-Instruct-v0.3__9e640ff8-02fb-44a7-9573-54798541cd89',
        'ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3__b408cb1e-6735-4c60-8272-40a81d5e135f'
    ]
    # eval number got saved as a string for some reason, convert to number
    adm_runs_collection = mongo_db['admTargetRuns']
    adm_runs_collection.update_many(
        {'evalNumber': '9'},
        {"$set": {"evalNumber": 9}}  
    )

    print("Updated eval number from string to int")

    # delete extra adm runs
    delete_result = adm_runs_collection.delete_many({
        'evalNumber': 9,
        'adm_name': {'$nin': adm_runs_to_keep}
    })
    print(f"Deleted {delete_result.deleted_count} documents that were not included in approved list of adm names")
    
    #remove long string of numbers/letters after __ to clean adm names
    adm_runs_collection.update_many(
        {'evalNumber': 9, 'adm_name': {'$regex': '__'}},
        [{'$set': {'adm_name': {'$arrayElemAt': [{'$split': ['$adm_name', '__']}, 0]}}}]
    )
    
    # survey setup
    convert_adms(mongo_db, 9)

    version7_setup(auto_confirm=True)