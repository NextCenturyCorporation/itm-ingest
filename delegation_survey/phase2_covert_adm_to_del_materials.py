import os, json, copy
names = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']
names_used = []


def convert_adm(adm, scenario, target, name, template, medic_collec):
    # start building document to be uploaded
    doc = copy.deepcopy(template)
    
    doc.update({
        'target': target,
        'admName': name,
        'scenarioIndex': scenario,
        'admSessionId': adm['results']['ta1_session_id'],
        'alignmentScore': adm['results']['alignment_score'],
        'kdmas': adm['results']['kdmas'],
        'admAuthor': 'kitware',
        'evalNumber': 8,
    })

    print(doc)

    for el in adm['history']:
        # grab scenario name
        if el['command'] == 'Start Scenario':
            doc['scenarioName'] = el['response']['name']
        
        # every probe response 
        if el['command'] == 'Respond to TA1 Probe':
            pass
    #medic_collec.insert_one(doc)

def main(mongo_db):
    f = open(os.path.join('templates', 'phase2_single_medic_template.json'), 'r', encoding='utf-8')
    template = json.load(f)
    adm_runs = mongo_db['admTargetRuns'].find({"evalNumber": 8})
    medic_collec = mongo_db['admMedics']


    for adm in adm_runs:
        scenario = adm['scenario']
        target = adm['alignment_target']
        name = adm['adm_name']
        
        # don't process tests
        if name != 'prodtest':
            convert_adm(adm, scenario, target, name, template, medic_collec)
