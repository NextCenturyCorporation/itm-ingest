import utils.image_utils as image_utils
import dre_probe_matcher as dpm
import requests
import os

ADEPT_URL = "https://darpaitm.caci.com/adept" # config("ADEPT_URL")
ST_URL = "https://darpaitm.caci.com/soartech" # config("ST_URL")

#For testing, so I'm not creating a million recs
ST_SID = "6bb3ce2f-23e5-4606-81ba-24a099656c56"
ADEPT_SID = "142ca17f-d98e-4537-be39-8471f573bd7f"


def get_session_alignment(probe_url, align_url, probes, sid, scenario):
    '''
    Takes in the list of probes/matches and the urls to access and returns the session alignment
    '''
    print("probe_url: " + probe_url)
    print("align_url: " + align_url)
    print("probes: " + str(probes))
    print("sid: " + sid)
    print("scenario: " + scenario)

    for x in probes:
        if 'scenario_probe_id' in x and 'scenario_choice' in x:
            print("scenario_choice: " + x["scenario_choice"])
            print("probe_id: " + x["scenario_probe_id"])
            requests.post(probe_url, json={
                "response": {
                    "choice": x["scenario_choice"],
                    "justification": "justification",
                    "probe_id": x["scenario_probe_id"],
                    "scenario_id": scenario,
                },
                "session_id": sid
            })
    result = requests.get(align_url).json()
    print("result")
    print(str(result))
    if "score" in result:
        print("Score: " + str(result["score"]))
    else:
        print("NO SCORE")

    return result

def append_probe_response_to_survey_score(mongoDB):

    # new TA1 session
    ADEPT_SID = requests.post(f'{ADEPT_URL}/api/v1/new_session').text
    ST_SID = requests.post(f'{ST_URL}/api/v1/new_session?user_id=default_use').json()

    print("ST_SID: " + ST_SID)
    print("ADEPT_SID: " + ADEPT_SID)

    # collections
    test_col = mongoDB['test']
    surveyResults_col = mongoDB['surveyResults']
    surveyResults_res = surveyResults_col.find({"results.evalNumber":4})
    admMedics_col = mongoDB['admMedics']
    scenarios_col = mongoDB['scenarios']

    ad_align = []
    st_align = []

    for surveyResult in surveyResults_res:
        survey_oid = surveyResult["_id"]
        output = []
        output_prob_id = []
        for key in surveyResult["results"].keys():
            if "admName" in str(surveyResult["results"][key]):
                survey_scenarioIndex = (surveyResult["results"][key]["scenarioIndex"])
                survey_admName = (surveyResult["results"][key]["admName"])
                survey_admTarget = (surveyResult["results"][key]["admTarget"])
                for ques in surveyResult["results"][key]["questions"].keys():
                    if "response" in surveyResult["results"][key]["questions"][ques]:
                        survey_medic = (ques.split(':')[0])
                        # survey_question = (ques.split(':')[1].strip())
                        # survey_response = (surveyResult["results"][key]["questions"][ques]["response"])

                # print("survey_oid: " + str(survey_oid))
                # print("survey_scenarioIndex: " + survey_scenarioIndex)
                # print("survey_admName: " + survey_admName)
                # print("survey_admTarget: " + survey_admTarget)
                # print("survey_medic: " + survey_medic)

                medics_qa = []
                admMedics_res = admMedics_col.find({"evalNumber":4, "scenarioIndex": survey_scenarioIndex, "elements.dmName": survey_medic})

                if survey_scenarioIndex == "DryRunEval-IO2-eval":
                    survey_scenarioIndex = "DryRunEval-MJ2-eval"
                if survey_scenarioIndex == "DryRunEval-IO4-eval":
                    survey_scenarioIndex = "DryRunEval-MJ4-eval"
                if survey_scenarioIndex == "DryRunEval-IO5-eval":
                    survey_scenarioIndex = "DryRunEval-MJ5-eval"
                scenarios_res =  scenarios_col.find({"id":survey_scenarioIndex})

#################################################
                test_res = test_col.find({"evalNumber":4, "history.response.id":survey_scenarioIndex, "history.parameters.adm_name": survey_admName, "history.parameters.target_id": survey_admTarget})
                probes_score_from_test = []
                for test in test_res:
                    # There should only be one
                    test_oid = test["_id"]
                    test_adm_name = ""
                    # print("test_oid:" + str(test_oid))
                    for history in test["history"]:
                        if history["command"] == "Start Session":
                            test_adm_name = history["parameters"]["adm_name"]
                            # print("test_adm_name:" + test_adm_name)

                        if history["command"] == "Respond to TA1 Probe":
                            test_session_id = history["parameters"]["session_id"]
                            # test_choice = history["parameters"]["choice"]
                            # test_justification = history["parameters"]["justification"]

                            # print("test_session_id:" + test_session_id)
                            # print("test_choice:" + test_choice)
                            # print("test_justification:" + test_justification)

                        if history["command"] == "TA1 Probe Response Alignment":
                            test_align_session_id = history["parameters"]["session_id"]
                            # test_scenario_id = history["parameters"]["scenario_id"]
                            # test_target_id = history["parameters"]["target_id"]
                            test_probe_id = history["parameters"]["probe_id"]
                            test_score = history["response"]["score"]

                            # print("test_align_session_id:" + test_align_session_id)
                            # print("test_scenario_id:" + test_scenario_id)
                            # print("test_target_id:" + test_target_id)
                            # print("test_probe_id:" + test_probe_id)
                            # print("test_score:" + str(test_score))

                            probe_score = {
                                "test_probe_id" : test_probe_id,
                                "test_score" :  str(test_score)
                            }
                            # use this to disambiguate Adept
                            if str(test_score) != 'nan':
                                probes_score_from_test.append(probe_score)

                        if history["command"] == "TA1 Session Alignment":
                            test_alignment_score = history["response"]["score"]
                            # print("test_alignment_score:" + str(test_alignment_score))

                # print("test_session_id:" + test_session_id)
                # print("test_align_session_id:" + test_align_session_id)
                # print(probes_score_from_test)
#################################################

                for medic in admMedics_res:
                    if medic["elements"][0]["dmName"] == survey_medic:
                        medic_scenarioIndex = medic["scenarioIndex"]
                        medic_admSession = medic["admSession"]
                        medic_medicName = medic["elements"][0]["dmName"]
                        medic_actions = medic["elements"][0]["actions"]
                        medic_scene_id = medic["elements"][0]["scenes"][0]["id"]
                        medic_char_ids = medic["elements"][0]["scenes"][0]["char_ids"]
                        medic_supplies = medic["elements"][0]["scenes"][0]["supplies"]

                        # print("medic_scenarioIndex: " + medic_scenarioIndex)
                        # print("medic_admSession: " + medic_admSession)
                        # print("medic_medicName: " + medic_medicName)
                        # print("medic_scene_id: " + str(medic_scene_id))
                        # print("medic_char_ids: " + str(medic_char_ids))
                        # print("medic_supplies: " + str(medic_supplies))

                        if 'vol' in medic_scenarioIndex or 'qol' in medic_scenarioIndex:
                            # Soartech Scenario
                            for medic_action in medic_actions:
                                if medic_action.split(' ', 1)[0] not in ["Update:", "Question:", "Note:"]:
                                    # print("**medic_action**: " + medic_action)
                                    for scenario in scenarios_res:
                                        for scene in scenario["scenes"]:
                                            for action_mapping in scene["action_mapping"]:
                                                # action_mapping-unstructed differences with admMedic action
                                                action_mapping_fix = action_mapping["unstructured"].replace(" a ", " ").replace(".", "")
                                                if action_mapping_fix == "Save your last tourniquet":
                                                    action_mapping_fix = "Save the tourniquet for future use"
                                                if action_mapping_fix == "Treat the left leg of Casualty Y with tourniquet":
                                                    action_mapping_fix = "Treat Casualty Y with tourniquet on left thigh"
                                                if action_mapping_fix == "Treat the right leg of Casualty Y with tourniquet":
                                                    action_mapping_fix = "Treat Casualty Y with tourniquet on right thigh"

                                                if action_mapping_fix in medic_action.replace(" a ", " ").replace(".", ""):
                                                    scenario_probe_id = action_mapping["probe_id"]
                                                    scenario_choice = action_mapping["choice"]
                                                    scenario_unstructured = action_mapping["unstructured"]
                                                    # print("scenario_probe_id:" + scenario_probe_id)
                                                    # print("scenario_choice:" + scenario_choice)
                                                    # print("scenario_unstructured:" + scenario_unstructured)
                                                    output_prob_id.append({"scenario_probe_id":  scenario_probe_id, "scenario_choice": scenario_choice})

                                    scenarios_res.rewind()
                            output = {
                                "surveyResult_oid": survey_oid,
                                "survey_scenarioIndex": survey_scenarioIndex, 
                                "test_id": test_oid,
                                "test_session_id": test_session_id,
                                "test_align_session_id": test_align_session_id,
                                "admMedic_admSession": medic_admSession,
                                "probes": output_prob_id
                            }
                            st_align.append(get_session_alignment(f'{ST_URL}/api/v1/response', 
                                    f'{ST_URL}/api/v1/alignment/session?session_id={ST_SID}&target_id={survey_admTarget}&population=false',
                                    output_prob_id,
                                    ST_SID,
                                    survey_scenarioIndex))
                        else:
                            # Adept Scenario
                            # print(len(list(scenarios_res)))
                            prev_medic_action = ""
                            for medic_action in medic_actions:
                                found = False
                                if medic_action.split(' ', 1)[0] not in ["Update:", "Question:", "Note:"]:
                                    # print("**medic_action**: " + medic_action)
                                    for scenario in scenarios_res:
                                        for scene in scenario["scenes"]:
                                            for action_mapping in scene["action_mapping"]:
                                                # action_mapping-unstructed differences with admMedic action
                                                action_mapping_fix = action_mapping["unstructured"]
                                                #MJ2
                                                if action_mapping_fix == "Indicate that you intend to treat the shooter.":
                                                    action_mapping_fix = "Treat Shooter first"
                                                if action_mapping_fix == "Indicate that you intend to treat the victim.":
                                                    action_mapping_fix = "Treat Victim first"
                                                if action_mapping_fix == "Apply gauze to the victim.":
                                                    action_mapping_fix = "Treat Victim with hemostatic gauze"
                                                if action_mapping_fix == "Apply gauze to the shooter.":
                                                    action_mapping_fix = "Treat Shooter with hemostatic gauze"
                                                if action_mapping_fix == "Indicate you intend to have the shooter evacuated to the hospital.":
                                                    action_mapping_fix = "Plan to transport Shooter to a medical facility"
                                                if action_mapping_fix == "Indicate you intend to have the victim evacuated to the hospital.":
                                                    action_mapping_fix = "Plan to transport Victim to a medical facility"
                                                if action_mapping_fix == "You load the shooter.":
                                                    action_mapping_fix = "Transport Shooter to a medical facility"
                                                if action_mapping_fix == "You load the victim.":
                                                    action_mapping_fix = "Transport Victim to a medical facility"

                                                #IO2
                                                if action_mapping_fix == "You indicate you intend to evacuate Lucas.":
                                                    action_mapping_fix = "Plan to transport Translator to a medical facility"
                                                if action_mapping_fix == "You load Lucas onto the evac.":
                                                    action_mapping_fix = "Transport Translator to a medical facility"
                                                if action_mapping_fix == "You treat Lucas first.":
                                                    action_mapping_fix = "Treat Translator with "
                                                if action_mapping_fix == "Do some treatment on US military member.":
                                                    action_mapping_fix = "Treat US Military Member with "
                                                if action_mapping_fix == "You indicate you intend to evacuate Bennett.":
                                                    action_mapping_fix = "Plan to transport US Military Member to a medical facility"
                                                if action_mapping_fix == "You load Bennett onto the evac.":
                                                    action_mapping_fix = "Transport US Military Member to a medical facility"
                                                    
                                                #MJ4
                                                if action_mapping_fix == "Assess the kicker.":
                                                    action_mapping_fix = "Perform vitals assessment on Kicker"
                                                if action_mapping_fix == "Assess the passerby.":
                                                    action_mapping_fix = "Perform vitals assessment on Passerby"
                                                if action_mapping_fix == "Assess the US soldier.":
                                                    action_mapping_fix = "Perform vitals assessment on US Soldier" 
                                                if action_mapping_fix == "Treat the kicker.":
                                                    action_mapping_fix = "Treat Kicker with "            
                                                if action_mapping_fix == "Treat the US soldier.":
                                                    action_mapping_fix = "Treat US Soldier with "
                                                if action_mapping_fix == "Treat the passerby.":
                                                    action_mapping_fix = "Treat Passerby with "            
                                                if action_mapping_fix == "Plan to evacuate the passerby.":
                                                    action_mapping_fix = "Plan to transport Passerby to a medical facility"
                                                if action_mapping_fix == "Plan to evacuate the kicker.":
                                                    action_mapping_fix = "Plan to transport Kicker to a medical facility"
                                                if action_mapping_fix == "Plan to evacuate the US soldier.":
                                                    action_mapping_fix = "Plan to transport US Soldier to a medical facility"  

                                                # same probe id/choice for either
                                                if action_mapping_fix == "Move back to the kicker.":
                                                    action_mapping_fix = "Move back to others"  
                                                if action_mapping_fix == "Move back to the passerby.":
                                                    action_mapping_fix = "Move back to others"  

                                                #MJ5
                                                if action_mapping_fix == "Move Springer to evac.":
                                                    action_mapping_fix = "Plan to transport Springer to a medical facility"
                                                if action_mapping_fix == "Move Upton to evac.":
                                                    action_mapping_fix = "Plan to transport Upton to a medical facility"
                                                if action_mapping_fix == "Assess Springer first.":
                                                    action_mapping_fix = "Perform vitals assessment on Springer"
                                                if action_mapping_fix == "Assess Upton first.":
                                                    action_mapping_fix = "Perform vitals assessment on Upton"                                                                                                        
                                                if action_mapping_fix == "Treat Springer (with gauze) before assessing Upton.":
                                                    action_mapping_fix = "Treat Springer with hemostatic gauze"                                                                                                        
                                                if action_mapping_fix == "Treat Upton (with gauze) before assessing Springer.":
                                                    action_mapping_fix = "Treat Upton with hemostatic gauze"                

                                                if action_mapping_fix == "Treat Upton (with gauze) before assessing Springer.":
                                                    action_mapping_fix = "Treat Upton with hemostatic gauze"                

                                                # I DONT SEE THIS IN SCENARIO
                                                if action_mapping_fix == "Treat Upton (with tourniquet) ":
                                                    action_mapping_fix = "Treat Upton with tourniquet"   

                                                #IO5
                                                if action_mapping_fix == "Refuse to treat the attacker.":
                                                    action_mapping_fix = "No, I refuse to treat the attacker"   
                                                if action_mapping_fix == "Move attacker to evac.":
                                                    action_mapping_fix = "Plan to transport Attacker to a medical facility"
                                                if action_mapping_fix == "Move US soldier to evac.":
                                                    action_mapping_fix = "Plan to transport US Soldier to a medical facility"
                                                if action_mapping_fix == "Assess the attacker.":
                                                    action_mapping_fix = "Perform vitals assessment on Attacker"
                                                if action_mapping_fix == "Intend to treat the attacker.":
                                                    action_mapping_fix = "Yes, I am willing to treat the attacker"
                                                if action_mapping_fix == "Continue treating the wounded US soldier.":
                                                    action_mapping_fix = "Treat US Soldier with "
                                                if action_mapping_fix == "Treat the attacker.":
                                                    action_mapping_fix = "Treat Attacker "
                                                if action_mapping_fix == "Continue assessing the wounded US soldier.":
                                                    action_mapping_fix = "Perform vitals assessment on US Soldier"

                                                #IO4
                                                if action_mapping_fix == "Treat the passerby.":
                                                    action_mapping_fix = "Treat one of the civilians"                                                    

                                                if action_mapping_fix in medic_action:
                                                    scenario_probe_id = action_mapping["probe_id"]

                                                    for ps in probes_score_from_test:
                                                        # dont match probes with nan scores from test?
                                                        if ps["test_probe_id"] in scenario_probe_id:
                                                            scenario_choice = action_mapping["choice"]
                                                            scenario_unstructured = action_mapping["unstructured"]
                                                            # print("scenario_probe_id:" + scenario_probe_id)
                                                            # print("scenario_choice:" + scenario_choice)
                                                            # print("scenario_unstructured:" + scenario_unstructured)
                                                            # print("action_mapping_fix:" + action_mapping_fix)

                                                            output_prob_id.append({"scenario_probe_id":  scenario_probe_id, "scenario_choice": scenario_choice})

                                                            # Check Adept for more dups
                                                            found = True
                                                            break
                                            if found:
                                                break
                                    scenarios_res.rewind()

                              
                            output = {
                                "surveyResult_oid": survey_oid,
                                "survey_scenarioIndex": survey_scenarioIndex, 
                                "test_id": test_oid,
                                "test_session_id": test_session_id,
                                "test_align_session_id": test_align_session_id,
                                "admMedic_admSession": medic_admSession,
                                "probes": output_prob_id
                            }
                            ad_align.append(get_session_alignment(f'{ADEPT_URL}/api/v1/response', 
                                    f'{ADEPT_URL}/api/v1/alignment/session?session_id={ADEPT_SID}&target_id={survey_admTarget}&population=false',
                                    output_prob_id,
                                    ADEPT_SID,
                                    survey_scenarioIndex))
                print(output)
                print("##############################################################")



    print("$$$$$$$$$$$$$$$$$$$$$$$$$")
    print(ad_align)
    print("$$$$$$$$$$$$$$$$$$$$$$$$$")
    print(st_align)
