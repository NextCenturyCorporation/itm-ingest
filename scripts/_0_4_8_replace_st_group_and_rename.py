to_remove = [
    "qol-group-target-1-final-eval",
    "qol-group-target-2-final-eval",
    "vol-group-target-1-final-eval",
    "vol-group-target-2-final-eval"
]

def main(mongo_db):
    adm_collection = mongo_db['admTargetRuns']
    eval_5_adms = adm_collection.find({"evalNumber": 5})
    
    delete_count = 0
    rename_count = 0
    
    for adm in eval_5_adms:
        history = adm['history']
        start_index = -1
        align_index = -1
        
        for i, el in enumerate(history):
            if el['command'] == 'Start Scenario':
                start_index = i
            if el['command'] == 'Alignment Target':
                align_index = i
                break

        if align_index >= 0 and start_index >= 0:
            start = history[start_index]
            align = history[align_index]
            if start['parameters']['adm_name'] == 'ALIGN-ADM-ComparativeRegression-ICL-Template':
                # remove old group run
                if align['response']['id'] in to_remove:
                    adm_collection.delete_one({"_id": adm["_id"]})
                    delete_count += 1

            if history[start_index]['parameters']['adm_name'] == 'ALIGN-ADM-ComparativeRegression-Llama-3.2-3B-Instruct-SoarTech-MatchingChars__67b51a1b-f06e-4667-a2ce-a52c84a85a70':
                # sometime start scenario is index 0 and sometimes index 1.. accounted for
                updates = {}
                for i in range(0, start_index + 1):
                    if ('parameters' in history[i] and 
                        'adm_name' in history[i]['parameters']):
                        updates[f"history.{i}.parameters.adm_name"] = "ALIGN-ADM-ComparativeRegression-ICL-Template"
                
                if updates:
                    adm_collection.update_one(
                        {"_id": adm["_id"]},
                        {
                            "$set": updates
                        }
                    )
                    rename_count += 1
    
    print(f'Processed documents: {delete_count} deleted, {rename_count} renamed')