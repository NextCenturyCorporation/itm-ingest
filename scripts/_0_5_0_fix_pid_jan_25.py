def main(mongo_db):
    p_log = mongo_db['participantLog']
    #update plog w new id
    p_log.update_one(
        {"ParticipantID": 202411371},
        {"$set": {"ParticipantID": 202501700}}
    )

    #update the text scenario results they already took
    text_scenarios = mongo_db['userScenarioResults']
    text_scenarios.update_many(
       {"participantID": "202411371"},
       {"$set": {
           "participantID": "202501700",
           "evalNumber": 6,
           "evalName": "Jan 2025 Eval"
       }}
   )