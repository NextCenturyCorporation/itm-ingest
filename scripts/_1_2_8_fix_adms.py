import requests
from decouple import config
'''
This will check if the KDMA stored in the DB is different than what we get back from prod. 
If it is, we will replace the KDMA and alignment score to the target they are aligned to. 
We check all of the observed ADMs and the synthetic evaluation ADMs, because non-synthetic evaluation
ADMs don't have kdmas/alignment (it wasn't requested). We also only check MF targets, because only
MF needs to be rescored.
'''
ADEPT_URL = config("ADEPT_URL")
EVAL_NUM = 15

def get_kdma_profile(req_session, session_id):
    resp = req_session.get(f"{ADEPT_URL}api/v1/computed_kdma_profile?session_id={session_id}")
    resp.raise_for_status()
    return resp.json()

def get_alignment_score(req_session, session_id, target_id):
    resp = req_session.get(f"{ADEPT_URL}api/v1/alignment/session?session_id={session_id}&target_id={target_id}")
    resp.raise_for_status()
    return resp.json()

def kdmas_differ(stored, fetched):
    def to_dict(kdma_list):
        return {kdma['kdma']: {param['name']: param['value'] for param in kdma['parameters']} for kdma in kdma_list}

    stored_d, fetched_d = to_dict(stored), to_dict(fetched)
    if set(stored_d) != set(fetched_d):
        return True
    for kdma in stored_d:
        for param in stored_d[kdma]:
            if abs(stored_d[kdma].get(param, 0) - fetched_d[kdma].get(param, 0)) > 1e-6:
                return True
    return False

def update_adm_target_runs(adm_collec, adm_name, target, scenario, fetched_kdmas, fetched_alignment):
    result = adm_collec.update_one(
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
    adm_collec = mongo_db['admTargetRuns']
    docs = list(adm_collec.find({'evalNumber': EVAL_NUM,
                                 '$or': [
                                     {'synthetic': True},
                                     {'scenario': {'$regex': '-observe'}}
                                     ],
                                'alignment_target': {'$regex': 'MF'}}))
    total_docs = len(docs)
    print(f"Found {total_docs} evaluation MF adm documents with evalNumber={EVAL_NUM}\n")

    updated = 0
    errors = 0
    error_docs = []
    doc_num = 0
    req_session = requests.Session()

    for doc in docs:
        doc_num += 1
        sid = doc.get('results', {}).get('ta1_session_id'),
        target = doc.get('alignment_target')
        scenario = doc.get('scenario')
        adm_name = doc.get('adm_name', 'unknown')
        stored_kdmas = doc.get('results', {}).get('kdmas', [])

        print(f"{'='*60}")
        print(f"({doc_num}/{total_docs}): ADM: {adm_name} | Target: {target} | Scenario: {scenario}")

        if not sid or not target or not scenario or not stored_kdmas:
            msg = "Missing ta1_session_id, alignment_target, scenario, or kdmas"
            print(f"   {msg}, skipping")
            errors += 1
            error_docs.append({"adm": adm_name, "target": target, "scenario": scenario, "session_id": sid, "error": msg})
            continue

        # Remove prior to merging
        if doc.get('synthetic') is not None:
            msg = "Skipping synthetic ADMs for now until they have TA1 data"
            print(f"   {msg}, skipping")
            errors += 1
            error_docs.append({"adm": adm_name, "target": target, "scenario": scenario, "session_id": sid, "error": msg})
            continue

        try:
            fetched_kdmas = get_kdma_profile(req_session, sid)
            if kdmas_differ(stored_kdmas, fetched_kdmas):
                print(f"  ✗ KDMAs differ — updating admTargetRuns")
                fetched_alignment = get_alignment_score(req_session, id, target)

                matched, modified = update_adm_target_runs(
                    adm_collec, adm_name, target, scenario, fetched_kdmas, fetched_alignment
                )
                print(f"    admTargetRuns: matched={matched}, modified={modified}")
                updated += 1
            else:
                print(f"  ✓ KDMAs match")
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            errors += 1
            error_docs.append({"adm": adm_name, "target": target, "scenario": scenario, "session_id": sid, "error": str(e)})
            continue

    req_session.close()
    print(f"\n{'='*60}")
    print(f"Summary: {len(docs)} docs | {updated} updated | {errors} errors")
    if error_docs:
        print("\nError Documents:")
        for e in error_docs:
            print(f"  ADM: {e['adm']} | Target: {e['target']} | Scenario: {e['scenario']} | Session: {e['session_id']} | Reason: {e['error']}")
