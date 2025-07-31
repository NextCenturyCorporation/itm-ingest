def main(mongo_db):
    plog_collection = mongo_db["participantLog"]
    all_docs = plog_collection.find({})
    dre = [202409100, 202409199] # 4
    alsoDre = [20249201, 20249299] # 4
    ph1 = [202411300, 202411399] # 5
    ph1Online = [202411500, 202411599] # 5
    janEval = [202501700, 202501799] # 6
    juneEval = [202506100, 202506299] # 8
    julyEval = [202507100, 202507299] # 9
    for doc in all_docs:
        if 'hashedEmail' in doc:
            pid = doc['ParticipantID']

            try:
                pid = int(pid)
            except:
                if pid == '202409113A' or pid == '202409113B':
                    evalNum = 4
                    plog_collection.update_one({'_id': doc['_id']}, {'$set': {'evalNum': evalNum}})
                else:
                    print(f'Could not convert pid {pid} to int')
                continue
            evalNum = None
            if (pid >= dre[0] and pid <= dre[1]) or (pid >= alsoDre[0] and pid <= alsoDre[1]):
                evalNum = 4
            elif (pid >= ph1[0] and pid <= ph1[1]) or (pid >= ph1Online[0] and pid <= ph1Online[1]):
                evalNum = 5
            elif (pid >= janEval[0] and pid <= janEval[1]):
                evalNum = 6
            elif (pid >= juneEval[0] and pid <= juneEval[1]):
                evalNum = 8
            elif (pid >= julyEval[0] and pid <= julyEval[1]):
                evalNum = 9
            if evalNum:
                plog_collection.update_one({'_id': doc['_id']}, {'$set': {'evalNum': evalNum}})

