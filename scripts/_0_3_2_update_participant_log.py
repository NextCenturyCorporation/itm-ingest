def main(mongoDB):
    participant_log = mongoDB['participantLog']
    text_scenario_collection = mongoDB['userScenarioResults']
    survey_collection = mongoDB['surveyResults']
    sim_collection = mongoDB['humanSimulatorRaw']

    participants = participant_log.find()

    for participant in participants:
        pid = participant['ParticipantID']
        text_found = text_scenario_collection.count_documents({"participantID": str(pid)})
        surveys_found = survey_collection.count_documents({"results.Participant ID Page.questions.Participant ID.response": str(pid)})
        sim_found = sim_collection.count_documents({"pid": str(pid)})
        participant_log.update_one(
            {"ParticipantID": pid},
            {"$set": {"claimed": text_found > 0 or surveys_found > 0 or sim_found > 0, "textEntryCount": text_found, 
                      "surveyEntryCount": surveys_found, "simEntryCount": sim_found}}
        )

    print("Updated the participant log to track used ids.")