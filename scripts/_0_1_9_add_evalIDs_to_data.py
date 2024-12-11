import os
import io
import json
import yaml

    
def main(mongoDB):

    db_surveyResults = mongoDB["surveyResults"]
    db_userScenarioResults = mongoDB["userScenarioResults"]
    db_evaluationIDS = mongoDB["evaluationIDS"]

    result = db_surveyResults.update_many({"evalNumber": None }, { '$set': { "evalNumber": 3 } }) 
    print(f'Updated {result.modified_count} set evalNumber to 3 in surveyResults')

    result = db_surveyResults.update_many({ "evalName": None }, { '$set': { "evalName": "Metrics Evaluation" } }) 
    print(f'Updated {result.modified_count} set evalName to "Metrics Evaluation" in surveyResults')

    result = db_userScenarioResults.update_many({ "evalNumber": None }, { '$set': { "evalNumber": 3 } }) 
    print(f'Updated {result.modified_count} set evalNumber to 3 in userScenarioResults')

    result = db_userScenarioResults.update_many({ "evalName": None }, { '$set': { "evalName": "Metrics Evaluation" } }) 
    print(f'Updated {result.modified_count} set evalName to "Metrics Evaluation" in surveyuserScenarioResultsResults')

    db_evaluationIDS.insert_one({  
    "evalNumber": 1,  
    "evalName": "MVP",  
    "showMainPage": False})  
    db_evaluationIDS.insert_one({  
    "evalNumber": 2,  
    "evalName": "September Milestone",  
    "showMainPage": False})  
    db_evaluationIDS.insert_one({  
    "evalNumber": 3,  
    "evalName": "Metrics Evaluation",  
    "showMainPage": True})  
    db_evaluationIDS.insert_one({  
    "evalNumber": 4,  
    "evalName": "Dry Run Evaluation",  
    "showMainPage": False})  
    print("Created evaluationIDS collection and inserted values")



