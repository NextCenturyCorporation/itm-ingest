from datetime import datetime
VERBOSE = True

"""
Cleans up old MF ADM runs and medics, since we had to re-run all 1d and 2d MF runs.
It also renames the new MF runs.
"""

KEEP_BASELINE_MF_ADMS = {
    # 1d
    'ALIGN-ADM-OutlinesBaseline-DeepSeek-R1-Distill-Llama-8B__8fa44127-1634-4df9-8277-1c5c7acc135e',
    'ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3__c8f7b5ca-7bdd-4aab-ab61-d7e0ba30ddb3',
    'ALIGN-ADM-OutlinesBaseline-spectrum-Llama-3.1-8B-v1__7ed978f5-d4f2-4fa8-8105-f093ae76ad2a',
    'ALIGN-ADM-OutlinesBaseline-spectrum-Qwen3-14B-v1__37a08535-ec52-4032-ac05-a20fc664a99f'
    # 2d
    'ALIGN-ADM-OutlinesBaseline-DeepSeek-R1-Distill-Llama-8B__61e1e9eb-beee-4fa8-9023-1718d49204a6',
    'ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3__27de48d3-38b6-4795-ad83-596a244916db',
    'ALIGN-ADM-OutlinesBaseline-spectrum-Llama-3.1-8B-v1__79325c85-6701-469e-8603-d06924cdc223',
    'ALIGN-ADM-OutlinesBaseline-spectrum-Qwen3-14B-v1__d9b5fa56-ea55-487a-a194-ecd63ff43446'
}

KEEP_ALIGNED_MF_ADMS = {
    # 1d
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-DeepSeek-R1-Distill-Llama-8B__44ea406f-e7a9-4b62-9fda-d0089da4d5b4',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-Mistral-7B-Instruct-v0.3__8a2b6e49-b659-433a-8807-3ba9108cfa02',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-spectrum-Llama-3.1-8B-v1__e6c412ea-1ac5-4542-87e6-4c26e944ae16',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-spectrum-Qwen3-14B-v1__e1456f5b-5a32-4837-9cd6-91da8996a65f',
    'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-DeepSeek-R1-Distill-Llama-8B__4f0a7ed0-f357-4f82-ba91-e63245e50d8d',
    'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-Mistral-7B-Instruct-v0.3__c21dba0e-a32e-4bee-8985-3b4c417d73a3',
    'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-spectrum-Llama-3.1-8B-v1__391ab8cd-0836-41fe-a95d-b9713201ef7e',
    'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-spectrum-Qwen3-14B-v1__c9676099-5c5b-458c-9511-5928415f6cb3'
    # 2d
    'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-DeepSeek-R1-Distill-Llama-8B__50cea8ce-4152-4fdc-b66e-740c55be6f34',
    'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-Mistral-7B-Instruct-v0.3__3770d6de-e311-4cc8-84f6-93bd089959af',
    'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-spectrum-Llama-3.1-8B-v1__f6b9fece-9620-4608-8218-306d93283022',
    'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-spectrum-Qwen3-14B-v1__16d07798-0b84-4304-9e6f-c7065814b947',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-DeepSeek-R1-Distill-Llama-8B__80349ac0-9831-40aa-81c6-7b2662fce872',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-Mistral-7B-Instruct-v0.3__cc058122-4628-45f4-83fe-23d69d339c27',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-spectrum-Llama-3.1-8B-v1__e6cc651b-6fe3-4efb-ad39-e7dd80df7b51',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-spectrum-Qwen3-14B-v1__40d7ea63-d437-4d05-b125-693ce7405fcd'
}

# AF-PS
KEEP_BASELINE_NON_MF_ADMS = {
    'ALIGN-ADM-OutlinesBaseline-DeepSeek-R1-Distill-Llama-8B_01_12',
    'ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3_01_12',
    'ALIGN-ADM-OutlinesBaseline-spectrum-Llama-3.1-8B-v1_01_12',
    'ALIGN-ADM-OutlinesBaseline-spectrum-Qwen3-14B-v1_01_12'
}

KEEP_ALIGNED_NON_MF_ADMS = {
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-DeepSeek-R1-Distill-Llama-8B_01_13',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-Mistral-7B-Instruct-v0.3_01_12',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-spectrum-Llama-3.1-8B-v1_01_12',
    'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-spectrum-Qwen3-14B-v1_01_12',
    'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-Mistral-7B-Instruct-v0.3_01_12'
}

def delete_bad_adms(mongo_db, collection_name: str, target_field: str, adm_field: str, adms: list) -> list:
    adms_to_keep = []
    deleted_baseline = 0
    deleted_regression = 0

    for adm in adms:
        is_MF = '-MF' in adm[target_field]
        original_adm_name = adm.get(adm_field, '')
        should_delete = False

        if 'Baseline' in original_adm_name:
            if original_adm_name not in KEEP_BASELINE_MF_ADMS if is_MF else KEEP_BASELINE_NON_MF_ADMS:
                #if VERBOSE:
                #    print(f"Deleting ADM: {original_adm_name} because it's not in {KEEP_BASELINE_MF_ADMS if is_MF else KEEP_BASELINE_NON_MF_ADMS}")
                should_delete = True
                deleted_baseline += 1

        elif 'Regression' in original_adm_name:
            if original_adm_name not in KEEP_ALIGNED_MF_ADMS if is_MF else KEEP_ALIGNED_NON_MF_ADMS:
                #if VERBOSE:
                #    print(f"Deleting ADM: {original_adm_name} because it's not in {KEEP_ALIGNED_MF_ADMS if is_MF else KEEP_ALIGNED_NON_MF_ADMS}")
                should_delete = True
                deleted_regression += 1

        if should_delete:
            mongo_db[collection_name].delete_one({'_id': adm['_id']})
            if VERBOSE:
                print(f"Deleted ADM: {original_adm_name}")
            continue

        adms_to_keep.append(adm)

    print(f"Total Baseline ADMs deleted: {deleted_baseline}")
    print(f"Total Regression ADMs deleted: {deleted_regression}")

    return adms_to_keep


def rename_adms(mongo_db, adms_to_keep: list) -> dict:
    # Find earliest date for each ADM base name + scenario combination
    earliest_dates = {}
    for adm in adms_to_keep:
        original_adm_name = adm.get('adm_name', '')
        if '__' not in original_adm_name:
            continue # already renamed
        base = original_adm_name.split('__')[0]
        scenario = adm.get('scenario', '')
        evaluation = adm.get('evaluation', {})
        start_time = evaluation.get('start_time')

        group_key = (base, scenario)

        if start_time:
            dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S.%f")
            if group_key not in earliest_dates or dt < earliest_dates[group_key]:
                earliest_dates[group_key] = dt

    # Rename, and save association
    adm_name_map = {}
    for adm in adms_to_keep:
        original_adm_name = adm.get('adm_name', '')
        if '__' not in original_adm_name:
            continue # already renamed
        base = original_adm_name.split('__')[0]
        scenario = adm.get('scenario', '')
        group_key = (base, scenario)
        if group_key in earliest_dates:
            dt = earliest_dates[group_key]
            suffix = f"{dt.month:02d}_{dt.day:02d}"
            new_name = f"{base}_{suffix}"

            if new_name != original_adm_name:
                mongo_db['admTargetRuns'].update_one(
                    {'_id': adm['_id']},
                    {'$set': {
                        'adm_name': new_name,
                        'evaluation.adm_name': new_name
                    }}
                )
                adm_name_map[original_adm_name] = new_name
                if VERBOSE:
                    print(f"Renamed ADM: {original_adm_name} -> {new_name}")

    return adm_name_map


def main(mongo_db):
    collection_name = 'admTargetRuns'
    # Delete bad admTargetRuns adm runs and rename them
    adms = list(mongo_db[collection_name].find({'evalNumber': 15}))
    adms_to_keep = delete_bad_adms(mongo_db, collection_name, 'alignment_target', 'adm_name', adms)
    print(f"Finished deleting unwanted {collection_name} ADMs.")
    adm_name_map = rename_adms(mongo_db, adms_to_keep)
    print(f"Finished renaming {collection_name} ADMs.")

    # Delete bad admMedics adm runs
    collection_name = 'admMedics'
    adms = list(mongo_db[collection_name].find({'evalNumber': 15}))
    adms_to_keep = delete_bad_adms(mongo_db, collection_name, 'target', 'admName', adms)
    print(f"Finished deleting unwanted {collection_name} ADMs.")

    # Rename admMedics adms
    total_modified = 0
    for old_name in adm_name_map:
        new_name = adm_name_map[old_name]
        result = mongo_db[collection_name].update_many(
            {'admName': old_name},
            {'$set': {
                'admName': new_name
            }}
        )
        total_modified += result.modified_count

    print(f"Finished renaming {collection_name} ADMs; updated {total_modified}.")

    print("\nFinished ADM clean-up.")
