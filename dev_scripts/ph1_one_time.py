import os
from decouple import config 
from pymongo import MongoClient
from scripts._0_2_8_human_to_adm_comparison import main as compare_probes
from scripts._0_3_0_percent_matching_probes import main as find_matching_probe_percentage
from adept_repop_ph1 import main as repop
from scripts._0_4_4_adept_human_adm_compare_DRE_PH1_Server import main as ad_compare
from scripts._0_4_5_correct_plog_for_incorrect_load import main as correct_plog
from scripts._0_4_6_rerun_369 import main as rerun_369
from scripts._0_4_7_ph1_group_targets import main as group_targets

if __name__ == '__main__':
    # set up mongo
    client = MongoClient(config('MONGO_URL'))
    db = client.dashboard

    repop(db)

    # run 'weekly' version of probe matcher
    os.system('python3 ph1_probe_matcher.py -i ph1_sim_files -w')

    # run script that compares humans to adms (RQ1/3/4 column Alignment score (Del|ADM))
    # RQ 5 Alignment score (Participant|ADM (most, least))
    
    compare_probes(db, 5, False)

    ad_compare(db)
    correct_plog(db)
    rerun_369(db)
    group_targets(db)

    compare_probes(db, 4, True)
    compare_probes(db, 5, True)

    # run matching script (RQ5 columns Match_MostAligned and Match_LeastAligned)
    find_matching_probe_percentage(db, 5)