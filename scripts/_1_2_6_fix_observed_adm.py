import requests
from decouple import config

ADEPT_URL = config("ADEPT_URL")

def get_kdma_profile(session_id):
    resp = requests.get(f"{ADEPT_URL}api/v1/computed_kdma_profile?session_id={session_id}")
    resp.raise_for_status()
    return resp.json()

def get_alignment_score(session_id, target_id):
    resp = requests.get(f"{ADEPT_URL}api/v1/alignment/session?session_id={session_id}&target_id={target_id}")
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

def update_adm_target_runs(mongo_db, adm_name, target, scenario, fetched_kdmas, fetched_alignment):
    collection = mongo_db['admTargetRuns']
    result = collection.update_one(
        {
            "evaluation.adm_name": adm_name,
            "evaluation.alignment_target_id": target,
            "evaluation.scenario_id": scenario,
        },
        {"$set": {
            "results.kdmas": fetched_kdmas,
            "results.alignment_score": fetched_alignment["score"],
        }}
    )
    return result.matched_count, result.modified_count

def main(mongo_db):
    medic_collec = mongo_db['admMedics']
    docs = list(medic_collec.find({'evalNumber': 15}))
    print(f"Found {len(docs)} admMedics documents with evalNumber=15\n")

    updated = 0
    errors = 0
    error_docs = []

    for doc in docs:
        sid = doc.get('admSessionId')
        target = doc.get('target')
        scenario = doc.get('scenarioName')
        adm_name = doc.get('admName', 'unknown')
        stored_kdmas = doc.get('kdmas', [])

        print(f"{'='*60}")
        print(f"ADM: {adm_name} | Target: {target} | Scenario: {scenario}")

        if not sid or not target or not scenario or not stored_kdmas:
            msg = "Missing admSessionId, target, scenarioName, or kdmas"
            print(f"   {msg}, skipping")
            errors += 1
            error_docs.append({"adm": adm_name, "target": target, "scenario": scenario, "session_id": sid, "error": msg})
            continue

        updates = {}

        try:
            fetched_kdmas = get_kdma_profile(sid)
            if kdmas_differ(stored_kdmas, fetched_kdmas):
                print(f"  ✗ KDMAs differ — updating admMedics and admTargetRuns")
                updates["kdmas"] = fetched_kdmas

                fetched_alignment = get_alignment_score(sid, target)
                updates["alignmentScore"] = fetched_alignment["score"]

                matched, modified = update_adm_target_runs(
                    mongo_db, adm_name, target, scenario, fetched_kdmas, fetched_alignment
                )
                print(f"    admTargetRuns: matched={matched}, modified={modified}")
            else:
                print(f"  ✓ KDMAs match")
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            errors += 1
            error_docs.append({"adm": adm_name, "target": target, "scenario": scenario, "session_id": sid, "error": str(e)})
            continue

        if updates:
            medic_collec.update_one({"_id": doc["_id"]}, {"$set": updates})
            updated += 1

    print(f"\n{'='*60}")
    print(f"Summary: {len(docs)} docs | {updated} updated | {errors} errors")
    if error_docs:
        print("\nError Documents:")
        for e in error_docs:
            print(f"  ADM: {e['adm']} | Target: {e['target']} | Scenario: {e['scenario']} | Session: {e['session_id']} | Reason: {e['error']}")