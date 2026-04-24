import pymongo

'''
This script cleans up all the entries in surveyResults and scenarioResults collections 
that do not have a participantID in participantLogs OR its participantID field value is null, does not exist, or has junk test data

Delete Count Breakdown
** 259 DOCUMENTS IN TOTAL SHOULD BE DELETED ACROSS BOTH SURVEY/SCENARIO COLLECTIONS (all fact checked in mongoDB Compass)
    * 39 DNE PIDs & 2 NULL PIDs in surveyResults (ALL FACT CHECKED W/ DB) 
    * 133 TEST DATA PIDS in surveyResults 
    * 47 INVALID PIDS in surveyResults
    * 8 TEST DATA in scenarioResults
    * 30 INVALID PIDS in scenarioResults

'''
DELETE = False # only delete documents after EVERYTHING is checked

def get_valid_participant_ids(pid_collection):
    # get valid pids from participantLog
    log_pids = pid_collection.find({"ParticipantID" : {"$exists": True, "$ne": None}})
    valid_pids = set()

    # match participant log pids type to surveyResults and scenarioResults
    for doc in log_pids:
        valid_pids.add(str(doc["ParticipantID"]))

    return valid_pids

def log_and_delete(collection, query, label):
    # count documents that need to be deleted
    count = collection.count_documents(query)
    print(f"\n{label} Total Documents:", count)

    # print the ids of docs that will be deleted
    for doc in collection.find(query):
        print("Document IDs: ", doc["_id"])

    # delete the documents
    if DELETE:
        result = collection.delete_many(query)
        print(f"[{label}] Deleted:", result.deleted_count)
    else:
        print(f"{label} DRY RUN - NOTHING DELETED")

def delete_null_pids(collection, pid_field, label):
    # delete all entries where pid has a null value or does not exist
    query = {
        "$or": [
            {pid_field: None},
            {pid_field: {"$exists": False}}
        ]
    }

    # log && delete documents
    log_and_delete(collection, query, label)
   

def delete_invalid_pids(collection, pid_field, eval_field, valid_pids, label):
    # delete entires where pid is
        # NOT in valid_pids from Participant Logs + evalNumber >= 4
        # obvious test data regardless of evalNumber
    query = {
        "$or": [
            # invalid PIDs after eval 4 
            {
                "$expr": {
                    "$not": {
                        "$in": [
                            {"$toString": f"${pid_field}"},
                            valid_pids
                        ]
                    }
                },
                eval_field: {"$gte": 4},
                pid_field: {"$ne": None, "$exists": True}
            },
            { # obvious test data regardless of eval
                pid_field: {"$regex": "test", "$options": "i"},
            }
        ]
    }

    # log && delete documents
    log_and_delete(collection, query, label)

def delete_old_pids(collection, pid_field, eval_field, valid_pids, label):
    # delete old pids before eval 4 where it has junk data not containing proper pid syntax: [year, month, XX]
        query =  {
            "$expr": {
                    "$and": [
                        {"$ne": [f"${eval_field}", None]},
                        {"$lte": [f"${eval_field}", 4]},
                        {
                            "$not": {
                                "$regexMatch": {
                                    "input": { "$toString": f"${pid_field}" },
                                    "regex": r"(2024|2025|2026|2\d?0\d?2\d?4)"
                                }
                            }
                        }
                    ]
                },

            pid_field: {"$ne": None, "$exists": True}                
        }
    # log && delete documents
        log_and_delete(collection, query, label)

def main(mongo_db):
    # get all necessary collections and variables
    survey_collection = mongo_db['surveyResults']
    scenario_collection = mongo_db['userScenarioResults']
    pid_collection = mongo_db['participantLog']

    # get a list of valid PID from participantLog collection (mongoDB prefers lists)
    valid_pids = list(get_valid_participant_ids(pid_collection))

# -------- SURVEY CLEANUP -------- #   
    # remove null, missing, && invalid PIDs
    delete_null_pids(survey_collection, "results.pid", "SurveyResults | NULL PIDs")
    delete_invalid_pids(survey_collection, "results.pid", "results.evalNumber", valid_pids, "SurveyResults | INVALID PIDs AFTER 4") # after evalNumber 4
    delete_old_pids(survey_collection, "results.pid", "evalNumber", valid_pids, "SurveyResults | OLD PIDs BEFORE 4") # before evalNumber 4

# -------- SCENARIO CLEANUP -------- #   
    # remove null, missing, && invalid PIDs
    delete_null_pids(scenario_collection, "participantID", "UserScenarioResults | NULL PIDs")
    delete_invalid_pids(scenario_collection, "participantID", "evalNumber", valid_pids, "UserScenarioResults | INVALID PIDs")
    delete_old_pids(scenario_collection, "participantID", "evalNumber", valid_pids, "UserScenarioResults | OLD PIDs BEFORE 4")
    
   
