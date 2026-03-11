import requests
from decouple import config

ADEPT_URL = config("ADEPT_URL")

def get_kdma_profile(session_id):
    resp = requests.get(f"{ADEPT_URL}api/v1/computed_kdma_profile?session_id={session_id}")
    resp.raise_for_status()
    return resp.json()

def get_ordered_alignment(session_id):
    resp = requests.get(f"{ADEPT_URL}api/v1/get_ordered_alignment?session_id={session_id}")
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
    error_docs = []

    for doc in docs:
        pid = doc.get("participantID", "unknown")
        scenario_id = doc.get("scenario_id", "unknown")
        individual = "MF" in scenario_id
        updates = {}

        print(f"{'='*60}")
        print(f"Participant: {pid} | Scenario: {scenario_id}")

        # Combined (all docs)
        combined_session_id = doc.get("combinedSessionId")
        stored_kdmas = doc.get("kdmas", [])
        if combined_session_id and stored_kdmas:
            try:
                fetched_kdmas = get_kdma_profile(combined_session_id)
                if kdmas_differ(stored_kdmas, fetched_kdmas):
                    print(f"  ✗ Combined KDMAs differ — updating kdmas and mostLeastAligned")
                    updates["kdmas"] = fetched_kdmas
                    updates["mostLeastAligned"] = get_ordered_alignment(combined_session_id)
                else:
                    print(f"  ✓ Combined KDMAs match")
            except Exception as e:
                print(f"  ✗ Failed to fetch combined profile: {e}")
                errors += 1
                error_docs.append({"pid": pid, "scenario_id": scenario_id, "session_id": combined_session_id, "error": str(e)})
        else:
            print(f"    Missing combinedSessionId or kdmas, skipping combined check")
            errors += 1
            error_docs.append({"pid": pid, "scenario_id": scenario_id, "session_id": combined_session_id, "error": "Missing combinedSessionId or kdmas"})

        # Individual (MF docs only)
        if individual:
            individual_session_id = doc.get("individualSessionId")
            stored_individual_kdmas = doc.get("individualKdmas", [])
            if individual_session_id and stored_individual_kdmas:
                try:
                    fetched_individual_kdmas = get_kdma_profile(individual_session_id)
                    if kdmas_differ(stored_individual_kdmas, fetched_individual_kdmas):
                        print(f"  ✗ Individual KDMAs differ — updating individualKdmas and individualMostLeastAligned")
                        updates["individualKdmas"] = fetched_individual_kdmas
                        updates["individualMostLeastAligned"] = get_ordered_alignment(individual_session_id)
                    else:
                        print(f"  ✓ Individual KDMAs match")
                except Exception as e:
                    print(f"  ✗ Failed to fetch individual profile: {e}")
                    errors += 1
                    error_docs.append({"pid": pid, "scenario_id": scenario_id, "session_id": individual_session_id, "error": str(e)})
            else:
                print(f"    Missing individualSessionId or individualKdmas, skipping individual check")
                errors += 1
                error_docs.append({"pid": pid, "scenario_id": scenario_id, "session_id": individual_session_id, "error": "Missing individualSessionId or individualKdmas"})

        if updates:
            collection.update_one({"_id": doc["_id"]}, {"$set": updates})
            updated += 1

    print(f"\n{'='*60}")
    print(f"Summary: {len(docs)} docs | {updated} updated | {errors} errors")
    if error_docs:
        print("\nError Documents:")
        for e in error_docs:
            print(f"  PID: {e['pid']} | Scenario: {e['scenario_id']} | Session ID: {e['session_id']} | Reason: {e['error']}")