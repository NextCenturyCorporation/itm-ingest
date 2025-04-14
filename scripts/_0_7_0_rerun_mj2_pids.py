from scripts._0_5_7_add_Narr_nonNarr_kdmas import submit_responses
from scripts._0_5_7_add_Narr_nonNarr_kdmas import get_kdma_value
from scripts._0_6_8_adept_p1e_old_endpoints import main as rerun0_6_8
import requests
from decouple import config

adept_scenario_map = {
        'phase1-adept-eval-MJ2': 'DryRunEval-MJ2-eval',
        'phase1-adept-eval-MJ4': 'DryRunEval-MJ4-eval',
        'phase1-adept-eval-MJ5': 'DryRunEval-MJ5-eval',
        'phase1-adept-train-MJ1': 'DryRunEval.MJ1',
        'phase1-adept-train-IO1': 'DryRunEval.IO1'
}

ADEPT_URL = config("ADEPT_URL")
def main(mongo_db):
    text_collec = mongo_db['userScenarioResults']

    query = {
        "evalNumber": {"$gte": 4},
        "scenario_id": {"$regex": "DryRun|adept"}
    }

    adept_res = text_collec.find(query)
    
    # Extract unique participant IDs
    participant_ids = set()
    for result in adept_res:
        pid = result['participantID']
        participant_ids.add(pid)
    
    # Create a dictionary to group documents by participant ID
    participant_documents = {}
    
    # For each participant ID, find all their documents
    for pid in participant_ids:
        # Find all documents for this participant
        participant_docs = text_collec.find({"participantID": pid})
        # Store the documents in our dictionary
        participant_documents[pid] = list(participant_docs)
    
    for pid, documents in participant_documents.items():
        has_mj2 = any('MJ2' in doc.get('scenario_id', '') for doc in documents)
        if not has_mj2:
            # skip if no mj2
            continue
        
        session = requests.post(f"{ADEPT_URL}/api/v1/new_session")
        combined_sess = session.text
        for doc in documents:
            scenario_id = doc.get('scenario_id', 'N/A')
            scenario_id = adept_scenario_map.get(scenario_id, scenario_id)

            submit_responses(doc, scenario_id, combined_sess, ADEPT_URL)

            if "MJ2" in scenario_id:
                # mj2 needs narr scores and session replaced as well
                narr_sess = requests.post(f"{ADEPT_URL}/api/v1/new_session")
                narr_sess_id = narr_sess.text
                submit_responses(doc, scenario_id, narr_sess_id, ADEPT_URL)
                kdmas = get_kdma_value(narr_sess_id, ADEPT_URL)

                text_collec.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {
                        "ph1NarrId": narr_sess_id,
                        "individual_kdmas": kdmas
                    }}
                )
        
        combined_kdmas = get_kdma_value(combined_sess, ADEPT_URL)
        most_least_aligned = most_least(combined_sess)
        # replace combined kdmas of IO and Mj2 docs
        for doc in documents:
            text_collec.update_one(
                {"_id": doc["_id"]},
                {"$set": {"kdmas": combined_kdmas, "combinedSessionId": combined_sess, "mostLeastAligned": most_least_aligned}}
            )
            

    #rerun0_6_8(mongo_db)

def most_least(session_id):
    targets = ['Moral judgement', 'Ingroup Bias'] 
    responses = []
    for target in targets:
        endpoint = '/api/v1/get_ordered_alignment'
        response = requests.get(
            f"{ADEPT_URL}{endpoint}",
            params={
                'session_id': session_id,
                'kdma_id': target
            }
        )

        print(response.json())
        responses.append({'target': target, 'response': response.json()})
    return responses