'''
ITM-1196

I am leveraging code I already wrote (w/ slight modifications) when we were analyzing phase 1 results to add individual scoring on each of
the three scenarios seen by participants to accompany the combined scores we already have.
'''
from scripts._0_5_7_add_Narr_nonNarr_kdmas import main as add_individual_scores

def main(mongo_db):
    add_individual_scores(mongo_db, 12)