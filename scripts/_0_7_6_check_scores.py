import pandas as pd
import re

def main(mongo_db):
    comp_scores_df = pd.read_csv('compscores.csv')
    
    discrepancies = []
    
    # 1e-6 allows for differences up to 0.000001
    epsilon = 1e-6  
    
    for index, row in comp_scores_df.iterrows():
        pid = row['ID']
        target = row['Target']
        scenario = row['Attribute'] + row['Renamed_scenario'][-1]
        pattern = re.compile(re.escape(scenario))
        population_score = row['Alignment (pop)']
        distance_score = row['Alignment (dist)']

        matching_doc = mongo_db['humanToADMComparison'].find_one({
            'evalNumber': 5,
            'pid': str(pid),
            'adm_alignment_target': target,
            'adm_scenario': {'$regex': pattern},
            '$or': [
                {'dre_server': {'$ne': True}},
                {'dre_server': {'$exists': False}}
            ]
        })

        if matching_doc:
            dist_score_doc = matching_doc['distance_based_score']
            pop_score_doc = matching_doc['score']
            
            pop_score_diff = abs(population_score - pop_score_doc)
            dist_score_diff = abs(distance_score - dist_score_doc)
            
            if pop_score_diff > epsilon or dist_score_diff > epsilon:
                discrepancy = {
                    'pid': pid,
                    'target': target, 
                    'scenario': scenario,
                    'csv_pop_score': population_score,
                    'db_pop_score': pop_score_doc,
                    'pop_diff': pop_score_diff,
                    'csv_dist_score': distance_score,
                    'db_dist_score': dist_score_doc,
                    'dist_diff': dist_score_diff
                }
                discrepancies.append(discrepancy)
                
                print(f"DISCREPANCY for pid={pid}, target={target}, scenario={scenario}")
                print(f"  Population Score: CSV={population_score}, DB={pop_score_doc}, Diff={pop_score_diff}")
                print(f"  Distance Score: CSV={distance_score}, DB={dist_score_doc}, Diff={dist_score_diff}")
        else:
            print(f"No matching document found for pid={pid}, target={target}, scenario={scenario}")
    
    
    if discrepancies:
        print(f"\nFound {len(discrepancies)} discrepancies out of {len(comp_scores_df)} entries")
    else:
        print(f"\nAll scores match within epsilon={epsilon} for {len(comp_scores_df)} entries checked")
    
    return discrepancies