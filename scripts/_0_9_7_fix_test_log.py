def main(mongo_db, pid=202507147):
    participant_log = mongo_db['participantLog']

    participant_log.find_one_and_update(
        {'ParticipantID': pid},
        {'$set': {'Type': 'emailParticipant'}}
    )
