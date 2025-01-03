'''
We need the names of the adms to match what they were when the surveys were taken.

At some point, it appears the entire admMedics collection was deleted. So we need to run
convert_adms_for_delegation, then ph1_dre_adms_for_delegation with eval4.

Then we need to run ph1_dre_adms_for_delegation with eval5 without basing names on previous evals
'''

import os
from decouple import config 

if __name__ == "__main__":
    from pymongo import MongoClient
    MONGO_URL = config('MONGO_URL')
    client = MongoClient(MONGO_URL)
    db = client.dashboard
    medic_mongo_collection = db['admMedics']
    db['admMedics'].delete_many({})
    os.system('python3 convert_adms_for_delegation.py')
    os.system('python3 ph1_dre_adms_for_delegation.py -e 4')
    os.system('python3 ph1_dre_adms_for_delegation.py -e 5')