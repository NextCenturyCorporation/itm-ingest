import os
from decouple import config 
from pymongo import MongoClient
from scripts._0_2_8_human_to_adm_comparison import compare_probes
from scripts._0_3_0_percent_matching_probes import find_matching_probe_percentage


if __name__ == '__main__':
    # set up mongo
    client = MongoClient(config('MONGO_URL'))
    db = client.dashboard

    # run 'weekly' version of probe matcher
    os.system('python3 ph1_probe_matcher.py -i ph1_sim_files -w')

    # run script that compares humans to adms (RQ1/3/4 column Alignment score (Del|ADM))
    # RQ 5 Alignment score (Participant|ADM (most, least))
    compare_probes(db, 5)

    # run matching script (RQ5 columns Match_MostAligned and Match_LeastAligned)
    find_matching_probe_percentage(db, 5)
