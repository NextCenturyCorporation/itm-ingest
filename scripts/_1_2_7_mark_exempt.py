import re
'''
Now that we have corrected the mostLeastAligned array of targets for participants, 
we need to go back and determine which survey blocks did not actually load in the most aligned target. 
If there is a mismatch, I mark the exemption, and this will be reflected in both the participant progress table and the RQ1 table.
'''

def get_scenario_types(scenario_index):
    known_types = ["AF", "PS", "MF", "SS"]
    return [t for t in known_types if t in scenario_index]


def is_individual_scenario(scenario_index):
    return bool(re.search(r'MF\d', scenario_index))


def get_text_doc(text_collec, pid, scenario_types, individual):
    #For individual scenarios, only match the first type. For combined, try all types.
    types_to_try = [scenario_types[0]] if individual else scenario_types
    for scenario_type in types_to_try:
        doc = text_collec.find_one({
            "participantID": pid,
            "scenario_id": re.compile(f"Feb2026-{scenario_type}\\d+-assess")
        })
        if doc:
            return doc
    return None


def get_expected_target(text_doc, scenario_types, choice_process, individual):
    if individual:
        most_least_aligned = text_doc.get('individualMostLeastAligned', [])
    else:
        most_least_aligned = text_doc.get('mostLeastAligned', [])

    if not most_least_aligned:
        return None

    response = most_least_aligned[0].get("response", [])

    all_types = ["AF", "PS", "MF", "SS"]
    excluded_types = [t for t in all_types if t not in scenario_types]

    def matches(target_key):
        has_required = all(t in target_key for t in scenario_types)
        has_excluded = any(t in target_key for t in excluded_types)
        return has_required and not has_excluded

    # the point of this filter is to make sure we are grabbing the appropriate first target
    # we need to ignore any 4D targets, and ignore any 1D for the 2D delegation blocks
    # for MF3, we should ONLY be looking at the 1D targets
    filtered = [
        list(entry.keys())[0]
        for entry in response
        if matches(list(entry.keys())[0])
    ]

    if not filtered:
        return None

    if choice_process == "most aligned":
        return filtered[0]
    elif choice_process == "least aligned":
        return filtered[-1]

    return None


def fix_aligned_format(text_collec):
    # I messed up the format of mostLeastAligned on the repaired documents in #125
    # this fixes that array to be in the format the dashboard expects
    docs = list(text_collec.find({'evalNumber': 15}))

    for doc in docs:
        updates = {}

        for field_name in ['mostLeastAligned', 'individualMostLeastAligned']:
            field = doc.get(field_name)
            if not field or not isinstance(field, list) or len(field) == 0:
                continue

            first_entry = field[0]
            if isinstance(first_entry, dict) and 'response' in first_entry:
                continue  # already correct

            updates[field_name] = [{"target": None, "response": field}]

        if updates:
            text_collec.update_one({'_id': doc['_id']}, {'$set': updates})


def main(mongo_db):
    survey_collec = mongo_db['surveyResults']
    text_collec = mongo_db['userScenarioResults']

    fix_aligned_format(text_collec)

    surveys = list(survey_collec.find({'results.evalNumber': 15}))
    print(f"Found {len(surveys)} surveys with evalNumber=15\n")

    mismatches = []

    for survey in surveys:
        results = survey.get('results', {})
        pid = results.get('pid')
        if not pid:
            continue

        for key, page in results.items():
            if not isinstance(page, dict):
                continue
            if page.get('pageType') != 'singleMedic':
                continue

            adm_alignment = page.get('admAlignment')
            if adm_alignment == 'baseline':
                continue

            adm_target = page.get('admTarget')
            adm_choice_process = page.get('admChoiceProcess')
            scenario_index = page.get('scenarioIndex')

            if not all([adm_target, adm_choice_process, scenario_index]):
                print(f"  PID {pid} | {key}: missing fields, skipping")
                continue

            scenario_types = get_scenario_types(scenario_index)
            individual = is_individual_scenario(scenario_index)
            text_doc = get_text_doc(text_collec, pid, scenario_types, individual)

            if not text_doc:
                print(f"  PID {pid} | {key}: no text doc found for {scenario_types}")
                continue

            expected_target = get_expected_target(text_doc, scenario_types, adm_choice_process, individual)

            if expected_target is None:
                print(f"  PID {pid} | {key}: could not determine expected target")
                continue

            if adm_target != expected_target:
                print(f"  ✗ PID {pid} | {key}: admTarget={adm_target} expected={expected_target} — marking exempt")
                survey_collec.update_one(
                    {'_id': survey['_id']},
                    {'$set': {f'results.{key}.admChoiceProcess': 'exempt'}}
                )
                mismatches.append({
                    "pid": pid,
                    "page": key,
                    "scenario_index": scenario_index,
                    "adm_alignment": adm_alignment,
                    "adm_choice_process": adm_choice_process,
                    "stored_target": adm_target,
                    "expected_target": expected_target,
                })
            else:
                print(f"  ✓ PID {pid} | {key}: admTarget={adm_target} correct")

    print(f"\n{'='*60}")
    print(f"Summary: {len(mismatches)} mismatches found and marked exempt")
    if mismatches:
        print("\nMismatched Documents:")
        for m in mismatches:
            print(f"  PID: {m['pid']} | Page: {m['page']} | Stored: {m['stored_target']} | Expected: {m['expected_target']}")