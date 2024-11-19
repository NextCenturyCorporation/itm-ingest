def participant_log_p1_update(mongo_db):
    participant_log = mongo_db['participantLog']
    result = participant_log.delete_many({
        '$or': [
            {'claimed': {'$ne': True}},
            {'claimed': {'$exists': False}}
        ]
    })

    example_civ = {
        'Type': 'Civ',
        'ParticipantID': 202411301,
        'Text-1': 'AD-1',
        'Text-2': 'ST-1',
        'Sim-1': 'AD-2',
        'Sim-2': 'ST-2',
        'Del-1': 'AD-3',
        'Del-2': 'ST-3',
        'ADMOrder': 3,
        'claimed': False,
        'simEntryCount': 0,
        'surveyEntryCount': 0,
        'textEntryCount': 0 
    }
    
    participant_log.insert_many([example_civ, example_mil])
