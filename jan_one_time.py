import os
from decouple import config 
from pymongo import MongoClient
from scripts._0_2_8_human_to_adm_comparison import main as compare_probes
from scripts._0_3_0_percent_matching_probes import main as find_matching_probe_percentage

if __name__ == '__main__':
    # set up mongo
    client = MongoClient(config('MONGO_URL'))
    db = client.dashboard

    # run 'weekly' version of probe matcher
    os.system('python3 ph1_probe_matcher.py -i jan_sim_files -w -e 6')

    # run script that compares humans to adms (RQ1/3/4 column Alignment score (Del|ADM))
    # RQ 5 Alignment score (Participant|ADM (most, least))
    
    compare_probes(db, 6, False)

    # run matching script (RQ5 columns Match_MostAligned and Match_LeastAligned)
    find_matching_probe_percentage(db, 6)