import csv
from pymongo import MongoClient
from decouple import config 

IO = 'Ingroup Bias'
MJ = 'Moral judgement'

def get_text_kdmas(mongo_db, output='text_kdmas.csv'):
    '''
    Create a csv that contains all mj and io kdmas from all participants (evals 4/5/6), 
    including overall, narrative, and non-narrative values.
    '''
    f = open(output, 'w', encoding='utf-8')
    writer = csv.writer(f)
    header = ['PID', 'Eval', 'Type', 'MJ', 'IO']
    writer.writerow(header)
    text_scenarios = mongo_db['userScenarioResults']
    p_log = mongo_db['participantLog']

    valid_text = text_scenarios.find({
        'evalNumber': {'$in': [4, 5, 6]}, 
        '$or': [
            {'scenario_id': {'$regex': 'DryRun'}}, 
            {'scenario_id': {'$regex': 'adept'}}
            ]
        })
    
    kdma_map = {}

    for entry in valid_text:
        pid = entry['participantID']
        pid_found = 0
        try:
            pid_found = p_log.count_documents({'ParticipantID': int((pid))})
        except:
            # not a valid pid to be number-fied
            continue
        if pid_found == 0:
            continue
        if pid not in kdma_map:
            kdma_map[pid] = {'overall': {'mj': -1, 'io': -1}, 'train': {'mj': -1, 'io': -1}, 'narr': {'mj': -1, 'io': -1}}
        scenario = entry['scenario_id']

        overall_kdmas = entry['kdmas']
        kdma_map[pid]['overall']['mj'] = get_kdma_att(overall_kdmas, MJ)
        kdma_map[pid]['overall']['io'] = get_kdma_att(overall_kdmas, IO)


        indi_kdmas = entry.get('individual_kdma', [])
        if (len(indi_kdmas) == 0):
            print(f'Individual KDMA missing for {pid}')
        if 'IO1' in scenario:
            kdma_map[pid]['train']['io'] = get_kdma_att(indi_kdmas, IO)
        elif 'MJ1' in scenario:
            kdma_map[pid]['train']['mj'] = get_kdma_att(indi_kdmas, MJ)
        else:
            kdma_map[pid]['narr']['mj'] = get_kdma_att(indi_kdmas, MJ)
            kdma_map[pid]['narr']['io'] = get_kdma_att(indi_kdmas, IO)
        
        if is_map_complete(kdma_map[pid]):
            writer.writerow([pid, entry['evalNumber'], 'overall', kdma_map[pid]['overall']['mj'], kdma_map[pid]['overall']['io']])
            writer.writerow([pid, entry['evalNumber'], 'train', kdma_map[pid]['train']['mj'], kdma_map[pid]['train']['io']])
            writer.writerow([pid, entry['evalNumber'], 'narr', kdma_map[pid]['narr']['mj'], kdma_map[pid]['narr']['io']])


    f.close()


def is_map_complete(map):
    '''
    Takes in a kdma_map and returns if all values have been filled in
    '''
    return map['overall']['mj'] != -1 and map['overall']['io'] != -1 and map['train']['mj'] != -1 and map['train']['io'] != -1 and map['narr']['mj'] != -1 and map['narr']['io'] != -1


def get_kdma_att(kdmas, att):
    '''
    Returns the kdma value for the requested attribute
    '''
    for kdma_obj in kdmas:
        if kdma_obj['kdma'] == att:
            return kdma_obj['value']
    return -1


if __name__ == '__main__':
    client = MongoClient(config('MONGO_URL'))
    db = client.dashboard
    get_text_kdmas(db)
