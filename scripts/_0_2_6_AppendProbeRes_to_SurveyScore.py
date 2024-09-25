import utils.image_utils as image_utils
import utils.probe_matcher_utils as pmu
import dre_probe_matcher as dpm
import PIL
import os
from PIL import Image


def append_probe_response_to_survey_score(mongoDB):
    test_col = mongoDB['test']
    # test_res = test_col.find({"evalNumber":4})

    surveyResults_col = mongoDB['surveyResults']
    surveyResults_res = surveyResults_col.find({"results.evalNumber":4})

    admMedics_col = mongoDB['admMedics']
    admMedics_res = admMedics_col.find({"evalNumber":4})

    scenarios_col = mongoDB['scenarios']
    # scenarios_res = scenarios_col.find({"evalNumber":4, "id":"qol-dre-1-eval"})

    # medics = []
    # for medic in admMedics_res:
    #     scenarioIndex = medic["scenarioIndex"]
    #     medicName = medic["elements"][0]["dmName"]
    #     scenes = medic["elements"][0]["scenes"]
    #     question = []
    #     answer = []
    #     for scene in scenes:
    #         question.append(scene["actions"][0])
    #         answer.append(scene["actions"][1])
    
    #     new_record = {
    #                     "scenarioIndex": scenarioIndex,
    #                     "medic": medicName,
    #                     "question": question,
    #                     "answer": answer
    #                 }
    #     medics.append(new_record)

    # print(medics)

    for surveyResult in surveyResults_res:
        for key in surveyResult["results"].keys():
            if "admName" in str(surveyResult["results"][key]):
                scenarioIndex = (surveyResult["results"][key]["scenarioIndex"])
                admName = (surveyResult["results"][key]["admName"])
                admTarget = (surveyResult["results"][key]["admTarget"])
                for ques in surveyResult["results"][key]["questions"].keys():
                    if "response" in surveyResult["results"][key]["questions"][ques]:
                        medic = (ques.split(':')[0])
                        # question = (ques.split(':')[1].strip())
                        # response = (surveyResult["results"][key]["questions"][ques]["response"])

                print("survey_scenarioIndex: " + scenarioIndex)
                print("survey_admName: " + admName)
                print("survey_admTarget: " + admTarget)
                print("survey_medic: " + medic)
                # print("question: " + question)
                # print("response: " + response)

                admMedics = admMedics_col.find({"evalNumber":4, "elements.dmName": medic})
                for admMedic in admMedics:
                    scenes = admMedic["elements"][0]["scenes"]
                    admMedics_question = []
                    admMedics_answer = []
                    for scene in scenes:
                        admMedics_question.append(scene["actions"][0])
                        admMedics_answer.append(scene["actions"][1])
    
                    print("admMedic_question")
                    print(admMedics_question)
                    print("admMedic_answer")
                    print(admMedics_answer)

                test_res = test_col.find({"evalNumber":4, "history.parameters.adm_name": admName, "history.parameters.scenario_id": scenarioIndex })
                probe_score_from_adm = []
                for test in test_res:
                    oid = test["_id"]
                    # print("oid: " +  str(oid))
                    for history in test["history"]:
                        if history["command"] == "Start Session":
                            test_adm_name = history["parameters"]["adm_name"]
                    
                        # if test_adm_name != admName:
                        #     break

                        if history["command"] == "Respond to TA1 Probe":
                            choice = history["parameters"]["choice"]
                        if history["command"] == "TA1 Probe Response Alignment":
                            
                            session_id = history["parameters"]["session_id"]
                            scenario_id = history["parameters"]["scenario_id"]
                            target_id = history["parameters"]["target_id"]
                            probe_id = history["parameters"]["probe_id"]
                            score = history["response"]["score"]

                            if admTarget == target_id:

                                new_record = {"oid": str(oid), "session_id": session_id, "scenario_id": scenario_id, "target_id": target_id, "probe_id": probe_id,"choice": choice,  "score": score}
                                probe_score_from_adm.append(new_record)

                                print("test_oid:" + str(oid))
                                print("test_adm_name:" + test_adm_name)
                                print("test_session_id:" + session_id)
                                print("test_scenario_id:" + scenario_id)
                                print("test_target_id:" + target_id)
                                print("test_probe_id:" + probe_id)
                                print("test_choice:" + choice)
                                print("test_score:" + str(score))
                                print("--------------------------")


                #scenarios_res = scenarios_col.find({"evalNumber":4, "id": scenarioIndex})
                # for document in scenarios_res:
                #     print(document)
                print("--------------------------")




    # for medic in admMedics_res:




    # probe_score_from_adm = []
    # for test in test_res:
    #     oid = test["_id"]
    #     # print("oid: " +  str(oid))
    #     for history in test["history"]:
    #         if history["command"] == "Respond to TA1 Probe":
    #             choice = history["parameters"]["choice"]
    #         if history["command"] == "TA1 Probe Response Alignment":
    #             session_id = history["parameters"]["session_id"]
    #             scenario_id = history["parameters"]["scenario_id"]
    #             target_id = history["parameters"]["target_id"]
    #             probe_id = history["parameters"]["probe_id"]
    #             score = history["response"]["score"]

    #             new_record = {"oid": str(oid), "session_id": session_id, "scenario_id": scenario_id, "target_id": target_id, "probe_id": probe_id,"choice": choice,  "score": score}
    #             probe_score_from_adm.append(new_record)

    #             print("oid:" + str(oid))
    #             print("session_id:" + session_id)
    #             print("scenario_id:" + scenario_id)
    #             print("target_id:" + target_id)
    #             print("probe_id:" + probe_id)
    #             print("choice:" + choice)
    #             print("score:" + str(score))
    #             print("--------------------------")
        

       
            #key = "target_id"
            #print(next(d[key] for d in probe_score_from_adm if key in d))

