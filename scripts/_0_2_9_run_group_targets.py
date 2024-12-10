import requests
from decouple import config 

ADEPT_URL = config("ADEPT_DRE_URL")
ST_URL = config("ST_DRE_URL")

GROUP_TARGETS = {
    '20249204': ['ADEPT-DryRun-Ingroup Bias-Group-Low', 'ADEPT-DryRun-Moral judgement-Group-Low', 'qol-group-target-dre-2', 'vol-group-target-dre-2'],
    '20249207': ['ADEPT-DryRun-Ingroup Bias-Group-Low', 'ADEPT-DryRun-Moral judgement-Group-High', 'qol-group-target-dre-1'],
    '20249213': ['ADEPT-DryRun-Ingroup Bias-Group-Low', 'ADEPT-DryRun-Moral judgement-Group-Low', 'qol-group-target-dre-1'],
    '20249203': ['ADEPT-DryRun-Ingroup Bias-Group-Low', 'ADEPT-DryRun-Moral judgement-Group-High', 'qol-group-target-dre-1'],
    '202409106': ['ADEPT-DryRun-Ingroup Bias-Group-Low', 'ADEPT-DryRun-Moral judgement-Group-Low', 'qol-group-target-dre-2'],
    '202409105': ['ADEPT-DryRun-Ingroup Bias-Group-Low', 'ADEPT-DryRun-Moral judgement-Group-Low', 'vol-group-target-dre-2'],
    '202409104': ['ADEPT-DryRun-Ingroup Bias-Group-Low', 'ADEPT-DryRun-Moral judgement-Group-Low', 'vol-group-target-dre-1'],
    '202409101': ['ADEPT-DryRun-Ingroup Bias-Group-Low', 'ADEPT-DryRun-Moral judgement-Group-Low', 'qol-group-target-dre-2'],
    '20249208': ['ADEPT-DryRun-Ingroup Bias-Group-High'],
    '202409108': ['ADEPT-DryRun-Ingroup Bias-Group-High', 'ADEPT-DryRun-Moral judgement-Group-High'],
    '20249209': ['ADEPT-DryRun-Ingroup Bias-Group-High', 'ADEPT-DryRun-Moral judgement-Group-High'],
    '20249205': ['ADEPT-DryRun-Ingroup Bias-Group-High', 'vol-group-target-dre-1'],
    '20249206': ['ADEPT-DryRun-Ingroup Bias-Group-High', 'ADEPT-DryRun-Moral judgement-Group-High'],
    '20249211': ['ADEPT-DryRun-Ingroup Bias-Group-High', 'ADEPT-DryRun-Moral judgement-Group-High', 'vol-group-target-dre-2'],
    '20249212': ['ADEPT-DryRun-Ingroup Bias-Group-High', 'ADEPT-DryRun-Moral judgement-Group-High', 'qol-group-target-dre-1', 'vol-group-target-dre-2'],
    '202409111': ['ADEPT-DryRun-Moral judgement-Group-Low'],
    '202409117': ['ADEPT-DryRun-Moral judgement-Group-Low', 'qol-group-target-dre-1'],
    '20249210': ['ADEPT-DryRun-Moral judgement-Group-Low'],
    '20249201': ['ADEPT-DryRun-Moral judgement-Group-High'],
    '202409119': ['ADEPT-DryRun-Moral judgement-Group-High', 'vol-group-target-dre-1'],
    '202409109': ['qol-group-target-dre-1', 'vol-group-target-dre-1'],
    '202409120': ['qol-group-target-dre-1'],
    '202409102': ['qol-group-target-dre-2', 'vol-group-target-dre-2'],
    '202409114': ['vol-group-target-dre-2']
}

def main(mongoDB):
    text_scenario_collection = mongoDB['userScenarioResults']

    data_to_update = text_scenario_collection.find(
        {"evalNumber": 4}
    )
    sessions_by_pid = {}
    for entry in data_to_update:
        scenario_id = entry.get('scenario_id')
        session_id = entry.get('combinedSessionId', entry.get('serverSessionId'))
        data_id = entry.get('_id')
        pid = entry.get('participantID')
        group_targets = {}
        new_id = None
        if 'qol' in scenario_id or 'vol' in scenario_id:
            for x in GROUP_TARGETS.get(pid, []):
                if ('qol' in x and 'qol' in scenario_id) or ('vol' in x and 'vol' in scenario_id):
                    alignment = requests.get(f'{ST_URL}api/v1/alignment/session?session_id={session_id}&target_id={x}').json().get('score')
                    group_targets[x] = alignment
        else:   
            for x in GROUP_TARGETS.get(pid, []):
                if 'ADEPT' in x:     
                    alignment = requests.get(f'{ADEPT_URL}api/v1/alignment/session?session_id={session_id}&target_id={x}&population=false').json()
                    if (alignment.get('status', 400) == 500):
                        # ADEPT's server loses our data sometimes, so we might have to re-send probes
                        if pid in sessions_by_pid:
                            new_id = sessions_by_pid[pid]['sid']
                            sessions_by_pid[pid]['_ids'].append(data_id)
                        else:
                            adept_sid = requests.post(f'{ADEPT_URL}api/v1/new_session').text.replace('"', '').strip()
                            sessions_by_pid[pid] = {'sid': adept_sid, '_ids': [data_id]}
                            new_id = adept_sid
                        # collect probes
                        probes = []
                        for k in entry:
                            if isinstance(entry[k], dict) and 'questions' in entry[k]:
                                if 'probe ' + k in entry[k]['questions'] and 'response' in entry[k]['questions']['probe ' + k] and 'question_mapping' in entry[k]['questions']['probe ' + k]:
                                    response = entry[k]['questions']['probe ' + k]['response'].replace('.', '')
                                    mapping = entry[k]['questions']['probe ' + k]['question_mapping']
                                    if response in mapping:
                                        probes.append({'probe': {'choice': mapping[response]['choice'], 'probe_id': mapping[response]['probe_id']}})
                                    else:
                                        print('could not find response in mapping!', response, list(mapping.keys()))
                        send_probes(f'{ADEPT_URL}api/v1/response', probes, new_id, scenario_id)
                        # after probes are sent, get kdmas
                        alignment = requests.get(f'{ADEPT_URL}api/v1/alignment/session?session_id={new_id}&target_id={x}&population=false').json()
                    group_targets[x] = alignment.get('score')

        # create object to add/update in database
        if (len(list(group_targets.keys())) > 0):
            updates = {'group_targets': group_targets}
            if new_id is not None:
                # only applies to ADEPT, ST did not lose data
                updates['combinedSessionId'] = new_id
                # if new_id exists, we need to update the group targets for all adept that this participant completed (we never know when it will be the last one)
                for data_id in sessions_by_pid[pid]['_ids']:
                    text_scenario_collection.update_one({'_id': data_id}, {'$set': updates})
            else:
                text_scenario_collection.update_one({'_id': data_id}, {'$set': updates})

    print("Group Target Alignments added to text scenario database.")


def send_probes(probe_url, probes, sid, scenario):
    '''
    Sends the probes to the server
    '''
    for x in probes:
        if 'probe' in x and 'choice' in x['probe']:
            requests.post(probe_url, json={
                "response": {
                    "choice": x['probe']['choice'],
                    "justification": "justification",
                    "probe_id": x['probe']['probe_id'],
                    "scenario_id": scenario,
                },
                "session_id": sid
            })
