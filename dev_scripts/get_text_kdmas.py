import csv
from pymongo import MongoClient
from decouple import config 

AF = 'affiliation'
MF = 'merit'
PS = 'personal_safety'
SS = 'search'
FILENAME = 'text_kdmas.csv'

def get_text_kdmas(mongo_db, output=FILENAME):
    '''
    Create a csv that contains all kdmas from all participants (July, aka eval 9).
    '''
    f = open(output, 'w', encoding='utf-8')
    writer = csv.writer(f)
    header = ['PID', 'Type', 'AF', 'MF', 'PS', 'SS']
    writer.writerow(header)
    text_scenarios = mongo_db['userScenarioResults']
    p_log = mongo_db['participantLog']

    valid_text = text_scenarios.find({'evalNumber': 9})
    kdma_map = {}
    found_pids = []
    num_rows = 0

    for entry in valid_text:
        pid = entry['participantID']
        if pid in found_pids:
            continue # Already got kdma data for this pid
        pid_found = 0
        try:
            pid_found = p_log.count_documents({'ParticipantID': int((pid))})
        except:
            # not a valid pid to be number-fied
            continue
        if not pid_found:
            continue
        found_pids.append(pid)
        if pid not in kdma_map:
            kdma_map[pid] = {'af': -1, 'mf': -1, 'ps': -1, 'ss': -1}

        kdmas = entry['kdmas']
        kdma_map[pid]['af'] = get_kdma_att(kdmas, AF)
        kdma_map[pid]['mf'] = get_kdma_att(kdmas, MF)
        kdma_map[pid]['ps'] = get_kdma_att(kdmas, PS)
        kdma_map[pid]['ss'] = get_kdma_att(kdmas, SS)

        if is_map_complete(kdma_map[pid]):
            num_rows += 1
            writer.writerow([pid, entry['evalNumber'],
                             kdma_map[pid]['af'], kdma_map[pid]['mf'],
                             kdma_map[pid]['ps'], kdma_map[pid]['ss']
                             ])

    print(f"Wrote {num_rows} rows to {FILENAME}")
    f.close()


def is_map_complete(map):
    '''
    Takes in a kdma_map and returns if all values have been filled in
    '''
    return map['af'] != -1 and map['mf'] != -1 and map['ps'] != -1 and map['ss'] != -1


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
