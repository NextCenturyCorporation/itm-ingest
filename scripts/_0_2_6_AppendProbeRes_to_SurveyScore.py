import utils.image_utils as image_utils
import PIL
import os
from PIL import Image


def append_probe_response_to_survey_score(mongoDB):
    test_col = mongoDB['test']
    test_res = test_col.find({"evalNumber":4})

    surveyResults_col = mongoDB['surveyResults']
    surveyResults_res = surveyResults_col.find({"results.evalNumber":4})


    probe_score_from_adm = []
    for test in test_res:
        oid = test["_id"]
        # print("oid: " +  str(oid))
        for history in test["history"]:
            if history["command"] == "TA1 Probe Response Alignment":
                session_id = history["parameters"]["session_id"]
                scenario_id = history["parameters"]["scenario_id"]
                target_id = history["parameters"]["target_id"]
                probe_id = history["parameters"]["probe_id"]
                score = history["response"]["score"]

                new_record = {"oid": str(oid), "scenario_id": scenario_id, "target_id": target_id, "probe_id": probe_id, "score": score}
                probe_score_from_adm.append(new_record)

                # print("oid:" + str(oid))
                # print("session_id:" + session_id)
                # print("scenario_id:" + scenario_id)
                # print("target_id:" + target_id)
                # print("probe_id:" + probe_id)
                # print("score:" + str(score))

    for surveyResult in surveyResults_res:
        for key in surveyResult["results"].keys():
            # print(surveyResult["results"][key])
            if "admName" in str(surveyResult["results"][key]):
                print(surveyResult["results"][key]["admName"])
                print(surveyResult["results"][key]["admTarget"])
                # print(surveyResult["results"][key]["questions"])
                for ques in surveyResult["results"][key]["questions"].keys():
                    if "response" in surveyResult["results"][key]["questions"][ques]:
                        print(ques)
                        print(surveyResult["results"][key]["questions"][ques]["response"])
            print("--------------------------")
        
        break
            #key = "target_id"
            #print(next(d[key] for d in probe_score_from_adm if key in d))

