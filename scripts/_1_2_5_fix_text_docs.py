import requests
from decouple import config

ADEPT_URL = config("ADEPT_URL")

def get_kdma_profile(session_id):
    resp = requests.get(f"{ADEPT_URL}api/v1/computed_kdma_profile?session_id={session_id}")
    resp.raise_for_status()
    return resp.json()

def kdmas_differ(stored, fetched):
    def to_dict(kdma_list):
        return {e['kdma']: {p['name']: p['value'] for p in e['parameters']} for e in kdma_list}
    
    stored_d, fetched_d = to_dict(stored), to_dict(fetched)
    if set(stored_d) != set(fetched_d):
        return True
    for kdma in stored_d:
        for param in stored_d[kdma]:
            if abs(stored_d[kdma].get(param, 0) - fetched_d[kdma].get(param, 0)) > 1e-6:
                return True
    return False

def main(mongo_db):
    collection = mongo_db['userScenarioResults']
    docs = list(collection.find({"evalNumber": 15}))
    print(f"Found {len(docs)} documents with evalNumber=15\n")

    updated = 0
    errors = 0
    for doc in docs:
        pid = doc.get("participantID", "unknown")
        scenario_id = doc.get("scenario_id", "unknown")
        individual = "MF" in scenario_id
        updates = {}

        print(f"{'='*60}")
        print(f"Participant: {pid} | Scenario: {scenario_id}")

        combined_session_id = doc.get("combinedSessionId")
        stored_kdmas = doc.get("kdmas", [])
        if combined_session_id and stored_kdmas:
            try:
                fetched_kdmas = get_kdma_profile(combined_session_id)
                if kdmas_differ(stored_kdmas, fetched_kdmas):
                    print(f"  ✗ Combined KDMAs differ — updating")
                    updates["kdmas"] = fetched_kdmas
                else:
                    print(f"  ✓ Combined KDMAs match")
            except Exception as e:
                print(f"  ✗ Failed to fetch combined KDMA profile: {e}")
                errors += 1
        else:
            print(f"  ⚠ Missing combinedSessionId or kdmas, skipping combined check")
            errors += 1

        # MF only. 
        if individual:
            individual_session_id = doc.get("individualSessionId")
            stored_individual_kdmas = doc.get("individualKdmas", [])
            if individual_session_id and stored_individual_kdmas:
                try:
                    fetched_individual_kdmas = get_kdma_profile(individual_session_id)
                    if kdmas_differ(stored_individual_kdmas, fetched_individual_kdmas):
                        print(f"✗ Individual KDMAs differ — updating")
                        updates["individualKdmas"] = fetched_individual_kdmas
                    else:
                        print(f"  ✓ Individual KDMAs match")
                except Exception as e:
                    print(f"  ✗ Failed to fetch individual KDMA profile: {e}")
                    errors += 1
            else:
                print(f"Missing individualSessionId or individualKdmas, skipping individual check")
                errors += 1

        if updates:
            collection.update_one({"_id": doc["_id"]}, {"$set": updates})
            updated += 1
    
    print(f"\n{'='*60}")
    print(f"Summary: {len(docs)} docs | {updated} updated | {errors} errors")