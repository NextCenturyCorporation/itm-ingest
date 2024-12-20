def main(mongo_db):
    survey_results = mongo_db['surveyResults']
    participant_log = mongo_db['participantLog']
    text_results = mongo_db['userScenarioResults']
    sim_results = mongo_db['humanSimulator']
    
    participant_surveys = survey_results.find({
        'results.pid': '202411353'
    })

    for survey in participant_surveys:
        if 'Post-Scenario Measures' not in survey['results']:
            survey_results.delete_one({'_id': survey['_id']})

    for participant in participant_log.find():
        pid = participant['ParticipantID']
        
        pid_str = str(pid)
        
        survey_count = survey_results.count_documents({'results.pid': pid_str})
        
        text_count = text_results.count_documents({'participantID': pid_str})
        
        sim_count = sim_results.count_documents({'pid': pid_str})
        
        participant_log.update_one(
            {'_id': participant['_id']},
            {'$set': {
                'surveyEntryCount': survey_count,
                'textEntryCount': text_count,
                'simEntryCount': sim_count
            }}
        )