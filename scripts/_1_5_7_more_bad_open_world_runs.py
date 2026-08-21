BAD_ADMS = [
    "ALIGN-ADM-Ph2-ComparativeRegression-Mistral-7B-Instruct-v0.3__ef63fb05-905e-430c-8fad-3b253479979a",
    "ALIGN-ADM-Ph2-ComparativeRegression-Mistral-7B-Instruct-v0.3__9a3be76d-a6b9-4d1d-ab3a-00b959b18331",
    "ALIGN-ADM-Ph2-ComparativeRegression-Mistral-7B-Instruct-v0.3__c1f7bde7-5b14-48f4-bb5b-6a477b3dd868",
    "testrun",
    "testrun-ALIGN-ADM-Ph2-ComparativeRegression-Mistral-7B-Instruct-v0.3__fbfe41ae-6991-4f55-b5ea-5a2dfc11b9cb"
]

def main(mongo_db):
    result = mongo_db['admTargetRuns'].delete_many({'adm_name': {'$in': BAD_ADMS}})

    print(f'Deleted {result.deleted_count} bad adms')