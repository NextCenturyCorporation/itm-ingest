from dev_scripts.tccc_per_patient_treatment import compute_treatment_count


def main(mongo_db):
    counter = 0
    tcccResults = mongo_db['tcccResults']
    for pid, treatment_counts in compute_treatment_count('TCCC-Trainer'):
        treat_dict = {}
        for patients, treatments in treatment_counts.items():
            for treatment, count in treatments.items():
                key = f"tccc_analysis.{patients} {treatment} Count"
                treat_dict[key] = count

        result = tcccResults.update_one({"_id": str(pid)},
            {"$set": 
                treat_dict
            }
        )
        counter += result.matched_count

    print(f"Finished updating {counter} documents")
