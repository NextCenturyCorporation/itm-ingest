import os
from pathlib import Path

import pandas as pd
import requests
from bson import ObjectId
from decouple import config

import utils.db_utils as db_utils
from scripts._0_8_3_June_Collab_Comparison_Generation import main as gen_comp

ADEPT_URL = config('ADEPT_URL')

EVAL_NUMBER = 17
HUMAN_TEXT_COLLECTION = 'userScenarioResults'
# threshold
SCORE_TOLERANCE = 1e-6


def score_difference(a, b):
    return a is None or b is None or abs(a - b) > SCORE_TOLERANCE


def get_session_id(adm):
    results = adm.get('results') or {}
    if results.get('ta1_session_id'):
        return results['ta1_session_id']
    print("Error - Missing TA1 Session ID")
    return None


def get_probes(medic):
    elements = medic.get('elements') or []
    rows = elements[0].get('rows', []) if elements else []
    probes = [
        {'probe': {'choice': row.get('choice_id'), 'probe_id': row.get('probe_id')}}
        for row in rows
    ]
    scenario = rows[0].get('scenario_id') if rows else medic.get('scenarioName')
    return probes, scenario


def build_set_dict(adm, new_sid, new_score):
    # Build dict for $set changed. Changes all occurences of ta1 session id or score
    old_sid = get_session_id(adm)
    set_ops = {}

    if isinstance(adm.get('results'), dict):
        set_ops['results.ta1_session_id'] = new_sid
        set_ops['results.alignment_score'] = new_score

    evaluation = adm.get('evaluation')
    if isinstance(evaluation, dict) and isinstance(evaluation.get('results'), dict):
        set_ops['evaluation.results.ta1_session_id'] = new_sid
        set_ops['evaluation.results.alignment_score'] = new_score

    for i, item in enumerate(adm.get('history', []) or []):
        command = item.get('command')
        params = item.get('parameters') or {}

        if command == 'TA1 Session ID':
            set_ops[f'history.{i}.response'] = new_sid
        elif command == 'TA1 Session Alignment':
            if params.get('session_id') == old_sid:
                set_ops[f'history.{i}.parameters.session_id'] = new_sid
            if isinstance(item.get('response'), dict) and 'score' in item['response']:
                set_ops[f'history.{i}.response.score'] = new_score
        elif command == 'Alignment Target':
            # parameters.session_id here is the TA1 session id
            if params.get('session_id') == old_sid:
                set_ops[f'history.{i}.parameters.session_id'] = new_sid

    return set_ops


def rescore_medics(mongo_db):
    '''
    For each eval 17 admMedics run, resend its probes to a fresh ADEPT session,
    re-score against the run's target, locate the matching admTargetRuns
    document, and return a per-run record. Does not modify the database.
    '''
    medic_collection = mongo_db['admMedics']
    adm_run_collection = mongo_db['admTargetRuns']

    medics = list(medic_collection.find({'evalNumber': EVAL_NUMBER}))
    total = len(medics)
    print(f"Found {total} admMedics document(s) for eval {EVAL_NUMBER}.\n")

    records = []
    for idx, medic in enumerate(medics, start=1):
        medic_name = medic.get('name')
        adm_name = medic.get('admName')
        target = medic.get('target')
        old_sid = medic.get('admSessionId')
        medic_existing = medic.get('alignmentScore')

        probes, scenario = get_probes(medic)

        print(f"[{idx}/{total}] {medic_name} | {adm_name} | {scenario} | target={target}")

        notes = []

        if not probes:
            print('  No probe responses on medic, skipping')
            records.append(make_medic_row(medic, None, scenario, target, old_sid, None,
                                              medic_existing, None, None, ['no probe responses on medic']))
            continue
        if not target:
            print('  No target on medic, skipping')
            records.append(make_medic_row(medic, None, scenario, target, old_sid, None,
                                              medic_existing, None, None, ['no target on medic']))
            continue

        # Fresh session: the original session ids no longer resolve after the
        # ADEPT memory wipe, so we rebuild the session from the stored probes.
        new_sid = requests.post(f'{ADEPT_URL}api/v1/new_session').text.replace('"', '').strip()
        db_utils.send_probes(f'{ADEPT_URL}api/v1/response', probes, new_sid, scenario)

        alignment_params = {'session_id': new_sid, 'target_id': target}
        if medic.get('subpop'):
            alignment_params['enable_subpop'] = medic['subpop']
        alignment = requests.get(
            f'{ADEPT_URL}api/v1/alignment/session', params=alignment_params
        ).json()
        new_score = alignment.get('score') if isinstance(alignment, dict) else None
        if new_score is None:
            notes.append('ADEPT returned no score')

        # Join to the admTargetRuns counterpart on the (pre-update) session id.
        adm_run = adm_run_collection.find_one({'results.ta1_session_id': old_sid}) if old_sid else None
        run_existing = None
        if adm_run is None:
            notes.append('no matching admTargetRuns document')
        else:
            run_existing = (adm_run.get('results') or {}).get('alignment_score')

        print(f"  existing(medic)={medic_existing} existing(run)={run_existing} new={new_score}")
        if notes:
            print(f"  notes: {'; '.join(notes)}")

        records.append(make_medic_row(medic, adm_run, scenario, target, old_sid, new_sid,
                                          medic_existing, run_existing, new_score, notes))

    return records


def make_medic_row(medic, adm_run, scenario, target, old_sid, new_sid,
                       medic_existing, run_existing, new_score, notes):
    score_discrepancy = (
        new_score is None
        or score_difference(new_score, medic_existing)
        or (adm_run is not None and score_difference(new_score, run_existing))
    )
    is_discrepancy = score_discrepancy or bool(notes)
    difference = (
        abs(new_score - medic_existing)
        if new_score is not None and medic_existing is not None
        else None
    )
    return {
        'medic': medic,
        'adm_run': adm_run,
        'medic_id': medic.get('_id'),
        'adm_run_id': adm_run.get('_id') if adm_run else None,
        'medic_name': medic.get('name'),
        'adm_name': medic.get('admName'),
        'scenario': scenario,
        'target': target,
        'old_session_id': old_sid,
        'new_session_id': new_sid,
        'medic_existing_score': medic_existing,
        'run_existing_score': run_existing,
        'new_score': new_score,
        'difference': difference,
        'note': '; '.join(notes),
        'is_discrepancy': is_discrepancy,
    }


def apply_medic_updates(mongo_db, records):
    '''
    Refresh the ta1 session id and alignment score on both documents for each
    rescored run: the admMedics doc (admSessionId / alignmentScore) and its
    matched admTargetRuns doc (every place those fields appear). Runs where ADEPT
    returned no score are skipped so we never write a null over a real value.
    '''
    medic_collection = mongo_db['admMedics']
    run_collection = mongo_db['admTargetRuns']
    medics_updated = runs_updated = skipped = 0

    for rec in records:
        if rec['new_score'] is None or not rec['new_session_id']:
            print(f"  Skipping {rec['medic_name']}: no new score/session from ADEPT")
            skipped += 1
            continue

        # admMedics: session id + alignment score live at the top level
        medic_result = medic_collection.update_one(
            {'_id': rec['medic_id']},
            {'$set': {'admSessionId': rec['new_session_id'], 'alignmentScore': rec['new_score']}},
        )
        medics_updated += medic_result.modified_count

        # admTargetRuns: refresh every location the fields appear in
        if rec['adm_run'] is not None:
            set_ops = build_set_dict(rec['adm_run'], rec['new_session_id'], rec['new_score'])
            if set_ops:
                run_result = run_collection.update_one({'_id': rec['adm_run_id']}, {'$set': set_ops})
                runs_updated += run_result.modified_count
        else:
            print(f"  {rec['medic_name']}: medic updated, but no admTargetRuns counterpart to update")

    print(f"\nApplied ADM updates: {medics_updated} admMedics, {runs_updated} admTargetRuns, {skipped} skipped.")


# ---------------------------------------------------------------------------
# Human side (userScenarioResults)
# ---------------------------------------------------------------------------

# The human ADEPT sessions are still live on the server, so we do NOT resend
# probes -- we just re-query each stored session id and compare. Each pairing is
# (session id field, mostLeastAligned field, allow_multiattribute_targets?) and
# matches how the dashboard originally scored eval 17:
#   * combinedSessionId -> combinedMostLeastAligned (no multiattribute)
#   * AF-SS_sessionId    -> AF-SS_mostLeastAligned   (multiattribute=true)
# A doc only carries AF-SS_sessionId if it is an AF or SS (non-trinary) doc, so
# driving off the stored fields reproduces the dashboard grouping automatically.
HUMAN_ALIGNMENT_CHECKS = [
    ('combinedSessionId', 'combinedMostLeastAligned', False),
    ('AF-SS_sessionId', 'AF-SS_mostLeastAligned', True),
]


def get_ordered_alignment(session_id, allow_multiattribute=False):
    # calls get_ordered_alignment the same way the dashboard woul
    params = {'session_id': session_id}
    if allow_multiattribute:
        params['allow_multiattribute_targets'] = 'true'
    data = requests.get(f'{ADEPT_URL}api/v1/get_ordered_alignment', params=params).json()
    if not isinstance(data, list):
        data = []
    filtered = [
        obj for obj in data
        if isinstance(obj, dict) and not any('-group-' in str(key).lower() for key in obj.keys())
    ]
    return [{'target': None, 'response': filtered}]

ATTRIBUTE_TOKENS = ('AF', 'PS', 'SS', 'MF')


def t_type(target_id):
    present = [attr for attr in ATTRIBUTE_TOKENS if attr in target_id]
    if 'AF' in present and 'SS' in present:
        return 'AF-SS'
    return present[0] if len(present) == 1 else None


def scenario_attr(scenario_id):
    #June2026-PS-assess-trinary -> PS. 
    parts = (scenario_id or '').split('-')
    return parts[1] if len(parts) > 1 else None


def order_targets(mla):
    # ensure order
    if not isinstance(mla, list) or not mla:
        return None
    block = mla[0]
    if not isinstance(block, dict):
        return None
    response = block.get('response')
    if not isinstance(response, list):
        return None

    targets = []
    for obj in response:
        if isinstance(obj, dict):
            targets.extend(obj.items())
    return targets


def ml_by_type(mla):
    # each type present to {'most': (target, score), 'least': (target, score)}
    targets = order_targets(mla)
    if targets is None:
        return None

    by_type = {}
    for target_id, score in targets:
        attr = t_type(target_id)
        if attr is None:
            continue
        if attr not in by_type:
            by_type[attr] = {'most': (target_id, score), 'least': (target_id, score)}
        else:
            by_type[attr]['least'] = (target_id, score)  # keep pushing least back
    return by_type


def break_down_alignment(mla, attribute):
    # most_target, most_score, least_target, least_score
    by_type = ml_by_type(mla)
    if not by_type or attribute not in by_type:
        return (None, None, None, None)
    entry = by_type[attribute]
    most_target, most_score = entry['most']
    least_target, least_score = entry['least']
    return (most_target, most_score, least_target, least_score)


def rescore_humans(mongo_db):
    # rescore the session ids already existing on the adept server and compare to scores stored in db
    collection = mongo_db[HUMAN_TEXT_COLLECTION]
    docs = list(collection.find({'evalNumber': EVAL_NUMBER}))
    print(f"\nFound {len(docs)} {HUMAN_TEXT_COLLECTION} doc(s) for eval {EVAL_NUMBER}.")

    # the alignment cache will stop us from making the same exact server calls
    alignment_cache = {}
    rows = []
    for doc in docs:
        attribute = scenario_attr(doc.get('scenario_id'))
        rows.append(make_human_row(doc, 'combinedSessionId', 'combinedMostLeastAligned',
                                    attribute, False, alignment_cache))
        if doc.get('AF-SS_sessionId'):
            rows.append(make_human_row(doc, 'AF-SS_sessionId', 'AF-SS_mostLeastAligned',
                                        'AF-SS', True, alignment_cache))

    return rows


def make_human_row(doc, session_field, mla_field, attribute, multiattr, alignment_cache):
    session_id = doc.get(session_field)

    new_alignment = None
    if session_id:
        cache_key = (session_id, multiattr)
        if cache_key not in alignment_cache:
            alignment_cache[cache_key] = get_ordered_alignment(session_id, allow_multiattribute=multiattr)
        new_alignment = alignment_cache[cache_key]

    stored_alignment = doc.get(mla_field)
    old_most_t, old_most_s, old_least_t, old_least_s = break_down_alignment(stored_alignment, attribute)
    new_most_t, new_most_s, new_least_t, new_least_s = break_down_alignment(new_alignment, attribute)

    note = '' if session_id else f'no {session_field} on doc'
    # discrepancy = the most- or least-aligned target of this type changed identity
    changed = (old_most_t != new_most_t) or (old_least_t != new_least_t)

    flag = 'DISCREPANCY' if changed else 'OK'
    print(f"  {doc.get('participantID')} | {doc.get('scenario_id')} | {attribute} -> {flag}")

    return {
        'doc_id': doc.get('_id'),
        'participantID': doc.get('participantID'),
        'scenario_id': doc.get('scenario_id'),
        'attribute': attribute,
        'mla_field': mla_field,
        'session_id': session_id,
        'old_most_target': old_most_t,
        'old_most_score': old_most_s,
        'old_least_target': old_least_t,
        'old_least_score': old_least_s,
        'new_most_target': new_most_t,
        'new_most_score': new_most_s,
        'new_least_target': new_least_t,
        'new_least_score': new_least_s,
        'changed': changed,
        'note': note,
        # full fetched array kept so write mode can overwrite the stored field
        'new_alignment': new_alignment,
    }


def apply_human_updates(mongo_db, rows):
    # overwrites the db with the accurate scores if necessary for the row
    # Note: each human has 8 corresponding rows
    collection = mongo_db[HUMAN_TEXT_COLLECTION]
    updated = 0
    for row in rows:
        if not row['changed'] or row['new_alignment'] is None:
            continue
        result = collection.update_one(
            {'_id': row['doc_id']},
            {'$set': {row['mla_field']: row['new_alignment']}},
        )
        updated += result.modified_count

    print(f"\nApplied human updates: {updated} mostLeastAligned field(s) overwritten where the most/least aligned target changed.")

def write_discrepancies(adm_records, human_rows):
   # will be two sheets, compares old scores/alignment to new
    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    root_dir = script_dir.parent
    excel_path = os.path.join(root_dir, 'eval17_rescore_discrepancies.xlsx')

    adm_columns = ['medic_name', 'adm_name', 'scenario', 'target',
                   'old_session_id', 'new_session_id',
                   'medic_existing_score', 'new_score', 'difference', 'note']
    adm_out = [
        {key: rec[key] for key in adm_columns}
        for rec in adm_records if rec['is_discrepancy']
    ]

    human_columns = ['participantID', 'scenario_id', 'attribute', 'session_id',
                     'old_most_target', 'old_most_score', 'old_least_target', 'old_least_score',
                     'new_most_target', 'new_most_score', 'new_least_target', 'new_least_score',
                     'changed', 'note']
    human_out = [{key: row[key] for key in human_columns} for row in human_rows]

    with pd.ExcelWriter(excel_path) as writer:
        pd.DataFrame(adm_out, columns=adm_columns).to_excel(writer, sheet_name='adm', index=False)
        pd.DataFrame(human_out, columns=human_columns).to_excel(writer, sheet_name='human', index=False)

    changed_count = sum(1 for row in human_rows if row['changed'])
    print(f"\nWrote report to {excel_path}")
    print(f"  adm sheet:   {len(adm_out)} discrepancy row(s)")
    print(f"  human sheet: {len(human_out)} row(s) ({changed_count} changed)")

def main(mongo_db, write_to_db=False):
    text_collec = mongo_db[HUMAN_TEXT_COLLECTION]
    # pid to remove bad second run: 137, 148, 152, 160
    bad_text_docs = {
        '202606137': ['6a344ae462f0ee5e0f35ea25', '6a344ae462f0ee04af35ea27', '6a344ae462f0eeb9e435ea29', '6a344ae462f0ee7f9735ea2b'],
        '202606148': ['6a3dbb3162f0ee4f6f35fb4b', '6a3dbb3162f0eea81835fb49', '6a3dbb3162f0eed38d35fb47', '6a3dbb3162f0ee2ffd35fb45', '6a3dbb0e62f0ee186d35fb41', '6a3dbb0e62f0ee68da35fb3f'],
        '202606152': ['6a3d90b662f0eedd5f35fade', '6a3d90b662f0ee56da35fae1'],
        '202606160': ['6a3e6b5062f0ee046635fbda', '6a3e6b4f62f0eeb4dc35fbd7']
    }

    # remove bad text docs before we make any comparison scores
    for pid, oid_strings in bad_text_docs.items():
        object_ids = [ObjectId(oid) for oid in oid_strings]
        text_collec.delete_many({'_id': {'$in': object_ids}})

    # re-score the observed adm runs (admMedics + admTargetRuns) and the human runs
    adm_records = rescore_medics(mongo_db)
    human_rows = rescore_humans(mongo_db)

    # dump to excel
    write_discrepancies(adm_records, human_rows)

    if write_to_db:
        apply_medic_updates(mongo_db, adm_records)
        apply_human_updates(mongo_db, human_rows)
    #gen_comp(mongo_db, EVAL_NUMBER=17)