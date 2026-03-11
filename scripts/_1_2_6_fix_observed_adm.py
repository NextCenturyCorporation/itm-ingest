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

def main(mongo_db):
    medic_collec = mongo_db['admMedics']

    medics = list(medic_collec.find({'evalNumber': 15}))
    print(f"Found {len(medics)} medic documents with evalNumber=15\n")

    updated = 0
    errors = 0
    error_docs = []

    for medic in medics:
        sid = medic.get('admSessionId')
        target = medic.get('target')
        stored_kdmas = medic.get('kdmas', [])
        adm_name = medic.get('admName', 'unknown')

        print(f"{'='*60}")
        print(f"ADM: {adm_name} | Target: {target} | Session: {sid}")

        if not sid or not target or not stored_kdmas:
            msg = "Missing admSessionId, target, or kdmas"
            print(f"  {msg}, skipping")
            errors += 1
            error_docs.append({"adm": adm_name, "target": target, "session_id": sid, "error": msg})
            continue

        updates = {}

        try:
            fetched_kdmas = get_kdma_profile(sid)
            if kdmas_differ(stored_kdmas, fetched_kdmas):
                print(f"  ✗ KDMAs differ — updating kdmas and alignmentScore")
                updates["kdmas"] = fetched_kdmas
                alignment = get_alignment_score(sid, target)
                updates["alignmentScore"] = alignment
            else:
                print(f"  ✓ KDMAs match")
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            errors += 1
            error_docs.append({"adm": adm_name, "target": target, "session_id": sid, "error": str(e)})
            continue

        if updates:
            medic_collec.update_one({"_id": medic["_id"]}, {"$set": updates})
            updated += 1

    print(f"\n{'='*60}")
    print(f"Summary: {len(medics)} docs | {updated} updated | {errors} errors")
    if error_docs:
        print("\nError Documents:")
        for e in error_docs:
            print(f"  ADM: {e['adm']} | Target: {e['target']} | Session ID: {e['session_id']} | Reason: {e['error']}")