import pymongo

'''
This script cleans up all the entries in surveyResults and scenarioResults collections 
that do not have a participantID in participantLogs OR its participantID field value is null or does not exist

Next Steps
** DEBUG SCRIPT BY ONLY QUERYING WHAT NEEDS TO BE DELETED AND PRINT THAT TOO CONSOLE 

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
    print(f"\n{label} docs:", count)

    # print the ids of docs that will be deleted
    for doc in collection.find(query):
        print("Document IDs: ", doc["_id"])

    # delete the documents
    if DELETE:
        result = collection.delete_many(query)
        print(f"[{label}] Deleted:", result.deleted_count)
    else:
        print(f"[{label}] DRY RUN - nothing deleted")

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
    # delete entires where pid is NOT in valid_pids from Participant Logs
    # AND if evalNumber >= 4 where Participant Logs exist post DRE 4
    query = {
        "$or": [
            { # invalid PIDs after eval 4 
                pid_field: {"$exists": True, "$nin": valid_pids},
                eval_field: {"$gte": 4}
            },
            { # obvious test data
                pid_field: {"$regex": "test", "$options": "i"},
            }
        ]
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
    delete_null_pids(survey_collection, "results.pid", "NULL: surveyResults__results.pid")
    delete_invalid_pids(survey_collection, "results.pid", "results.evalNumber", valid_pids, "INVALID: surveyResults__results.pid")
   
# -------- SCENARIO CLEANUP -------- #   
    # remove null, missing, && invalid PIDs
    delete_null_pids(scenario_collection, "participantID", "NULL: ScenarioResults__participantID")
    delete_invalid_pids(scenario_collection, "participantID", "evalNumber", valid_pids, "INVALID: ScenarioResults__participantID")
    
   
