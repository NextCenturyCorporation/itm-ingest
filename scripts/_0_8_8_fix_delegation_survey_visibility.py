def main(mongo_db):
    delegation_collection = mongo_db["delegationConfig"]
    target_ids = ["delegation_v7.0", "delegation_v6.0"]

    POST_SCENARIO_PAGE_INDEX = 293
    ROLE_QUESTION_INDEX = 9
    QUESTION7_INDEX = 10

    ROLE_ANYOF = '{What is your current role} anyof ["Medical student","Resident","Physician","Physician\\\'s Assistant","Nurse","EMT","Paramedic","Military Medicine"]'
    MEDICAL_ROLE = '({Served in Military} anyof ["Currently serving (Active)", "Currently serving (Reserves/Guard)", "Veteran (Retired/Separated)"]) and ({Did you serve in a military medical role} = "Yes")'
    TCCC_FOLLOWUP = (
        '({Served in Military} anyof ["Currently serving (Active)", "Currently serving (Reserves/Guard)", '
        '"Veteran (Retired/Separated)"]) and ({Did you serve in a military medical role} = "Yes") and '
        '({When did you last complete TCCC training or recertification} anyof ["Within the last 6 months", '
        '"6-12 months ago", "1-2 years ago", "More than 2 years ago"])'
    )

    for doc in delegation_collection.find({"_id": {"$in": target_ids}}):
        survey = doc.get("survey", {})
        if not survey:
            print(f"{doc.get('_id')} document missing 'survey' field. Modifications to this document skipped.")
            continue

        pages = survey.get("pages", [])
        if not pages:
            print(f"{doc.get('_id')} document missing 'pages' field. Modifications to this document skipped.")
            continue

        if len(pages) > POST_SCENARIO_PAGE_INDEX and pages[POST_SCENARIO_PAGE_INDEX].get("name") == "Post-Scenario Measures":
            target_page = pages[POST_SCENARIO_PAGE_INDEX]
        else:
            print(f"{doc.get('_id')} document missing 'Post-Scenario Measures' page. Modifications to this document skipped.")
            continue

        elements = target_page.get("elements", [])
        modified = False

        # Bug A: Change Configuration of Follow Up Question After Current Role Question
        if len(elements) > QUESTION7_INDEX:
            role_element = elements[ROLE_QUESTION_INDEX]
            if role_element.get("name") == "What is your current role":
                if role_element.get("type") != "checkbox":
                    role_element["type"] = "checkbox"
                    modified = True
            else:
                print(f"Expected element {ROLE_QUESTION_INDEX} to be 'What is your current role' in {doc.get('_id')}.")
            follow_up = elements[QUESTION7_INDEX]
            if follow_up.get("name") == "question7":
                if follow_up.get("visibleIf") != ROLE_ANYOF:
                    follow_up["visibleIf"] = ROLE_ANYOF
                    modified = True
            else:
                print(f"Expected element {QUESTION7_INDEX} to be 'question7' in {doc.get('_id')}.")
        else:
            print(f"Fewer than expected number of elements in 'Post-Scenario Measures' page for {doc.get('_id')} document. All modifications to this document skipped.")
            continue

        # Bug B: Eliminate Sticky Military/Medical/TCCC Follow Up Questions
        question_mapping = {
            17: ("What was/is your medical-related MOS or rate", MEDICAL_ROLE),
            18: ("How many years of experience do you have serving in a medical role in the military", MEDICAL_ROLE),
            19: ("In which environments have you provided medical care during military service", MEDICAL_ROLE),
            20: ("When did you last complete TCCC training or recertification", MEDICAL_ROLE),
            21: ("How would you rate your expertise with TCCC procedures", TCCC_FOLLOWUP),
            22: ("How many real-world casualties have you assessed using TCCC protocols", TCCC_FOLLOWUP),
        }

        for index, (expected_name, visibility_expression) in question_mapping.items():
            if index >= len(elements):
                print(f"Missing element {index} in {doc.get('_id')}. Modifications to this element skipped.")
                continue
            element = elements[index]
            name = element.get("name")
            if name == expected_name:
                if element.get("visibleIf") != visibility_expression:
                    element["visibleIf"] = visibility_expression
                    modified = True
            else:
                print(f"Unexpected name at element {index} in {doc.get('_id')}: '{name}'")
        
        #Bug C: Last TCCC Question in Survey Should Be Required
        if len(elements) > 22:
            element22 = elements[22]
            if element22.get("name") == "How many real-world casualties have you assessed using TCCC protocols":
                if element22.get("isRequired") is not True:
                    element22["isRequired"] = True
                    modified = True
    
        if modified:
            delegation_collection.update_one(
                {"_id": doc["_id"]},
                {"$set": {"survey.pages": pages}}
            )