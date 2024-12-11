import hashlib

def main(mongo_db):
    participant_log = mongo_db['participantLog']
    result = participant_log.find({'hashedEmail': None})

    for doc in result:
        pid = str(doc['ParticipantID']).encode('utf-8')
        hashed_pid = hashlib.sha256(pid).hexdigest()
        participant_log.update_one({'_id': doc['_id']}, {'$set': {'hashedEmail': hashed_pid}})
