import pymongo

'''
This script cleans up all the entries in surveyResults and scenarioResults collections 
that do not have a participantID in participantLogs OR its participantID field value is null or does not exist

** FACT CHECK FIELD NAMES && TYPES W/ MONGODB

'''

def get_valid_participant_ids(pid_collection):
    # get valid pids from participantLog
    log_pids = pid_collection.find({"ParticipantID" : {"$exists": True, "$nin": None}})
    valid_pids = set()

    for doc in log_pids:
        valid_pids.add(doc["ParticipantID"])

    return valid_pids

def delete_null_pids(collection, pid_field):
    # delete all entries where pid has a null value or does not exist
    survey_collection.delete_many({
        "$or": [
            {pid_field: None},
            {pid_field: {"$exists": False}}
        ]
    })

def delete_invalid_pids(collection, pid_field, valid_pids):
    # delete entires where pid is NOT in valid_pids from Participant Logs
    # AND if evalNumber <= 4 (we want data that's pre-DRE only)
    collection.delete_many({
        pid_field: {"$nin": valid_pids},
        "evalNumber": {"$lte": 4}
        })


def main(mongo_db):
    # get all necessary collections and variables
    survey_collection = mongo_db['surveyResults']
    scenarioResult_collection = mongo_db['userScenarioResults']
    pid_collection = mongo_db['participantLog']
    
    # get a set of valid PID from participantLog collection
    valid_pids = get_valid_participant_ids(pid_collection)

    # remove null/missing PIDs
    delete_null_pids(survey_collection, "results.pid")
    delete_null_pids(scenario_collection, "participantID")

    # remove invalid PIDs (ONLY pre-DRE data)
    delete_invalid_pids(survey_collection, "results.pid", valid_pids)
    delete_invalid_pids(scenario_collection, "participantID", valid_pids)
    

