
'''
This script cleans up all the entries in surveyResults and scenarioResults collections 
that do not have a participantID in participantLogs OR its participantID field value is null

** CLEAN UP UNECESSARY CODE & MAKE IT ORGANIZED 

'''
def main(mongo_db):
    # get all necessary collections and variables
    survey_collection = mongo_db['surveyResults']
    scenarioResult_collection = mongo_db['userScenarioResults']
    pid_collection = mongo_db['participantLog']
    
    # get valid pids from participantLog
    log_pids = pid_collection.find({"ParticipantID" : {"$exists": true, "$nin": null}})
    valid_pids = set()
    for doc in log_pids:
        valid_pids.add(doc["ParticipantID"])

    # delete all entries from both surveyResults and scenarioResults that's pid is null
    survey_null = survey_collection.find({"results.pid": {"$exists": true, "$eq": null}})
    ids_to_delete = []
    for doc in survey_null:
        ids_to_delete.append(doc["_id"])

    survey_collection.delete_many("_id": {"$in": ids_to_delete})

    scenario_null = scenarioResult_collection.find("participantID": {"$exists": true, "$eq": null})
    delete_null_ids = []
    for doc in scenario_null:
        delete_null_ids.append(doc["_id"])
    scenarioResult_collection.delete_many("_id": {"$in": delete_null_ids})

    # get surveyResults and scenarioResults non-null ids & cross reference them in valid_pids
    survey_pid = survey_collection.find({"results.pid": {"$exists": true, "$nin": null}})
    delete_survey_ids = []
    for doc in survey_pid:
        pid = doc["results"].get("pid")
        if pid not in valid_pids:
            # add pid to ids to delete IFF data is pre-DRE (eval number 4)
            if doc["evalNumber"] != null and doc["evalNumber"] < 4:
                delete_survey_ids.append(doc["_id"])

    # delete non-valid survey ids
    survey_collection.delete_many("_id": {"$in": delete_survey_ids})

    scenario_pid = survey_collection.find({"results.pid": {"$exists": true, "$nin": null}})
    delete_scenario_ids = []
    for doc in scenario_pid:
        pid = doc["participantID"]
        if pid not in valid_pids:
            # add pid to ids to delete IFF data is pre-DRE (eval number 4)
            if doc["evalNumber"] != null and doc["evalNumber"] < 4:
                delete_scenario_ids.append(doc["_id"])

     # delete non-valid scenario ids
    scenarioResult_collection.delete_many("_id": {"$in": delete_scenario_ids})
    

