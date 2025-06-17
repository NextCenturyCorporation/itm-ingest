def main(mongo_db):
    p_log = mongo_db['participantLog']
    text_results = mongo_db['userScenarioResults']
    
    min_pid = 202506100
    max_pid = 202506112
    
    text_query = {
        "participantID": {
            "$gte": str(min_pid),
            "$lte": str(max_pid)
        }
    }
    
    p_log_query = {
        "ParticipantID": {
            "$gte": min_pid,
            "$lte": max_pid
        }
    }
    
    p_log_zero_text_query = {
        "ParticipantID": {"$gt": min_pid},
        "textEntryCount": 0
    }
    
    text_count = text_results.count_documents(text_query)
    if text_count > 0:
        text_docs = text_results.find(text_query, {"participantID": 1, "_id": 1})
        print("Text results documents to be deleted because of pid range:")
        for doc in text_docs:
            print(f"  - ID: {doc['_id']}, participantID: {doc['participantID']}")
    
    p_log_count = p_log.count_documents(p_log_query)
    if p_log_count > 0:
        p_log_docs = p_log.find(p_log_query, {"ParticipantID": 1, "_id": 1})
        print("Participant log documents being deleted because of pid range:")
        for doc in p_log_docs:
            print(f"  - ID: {doc['_id']}, ParticipantID: {doc['ParticipantID']}")
    
    p_log_zero_count = p_log.count_documents(p_log_zero_text_query)
    if p_log_zero_count > 0:
        p_log_zero_docs = p_log.find(p_log_zero_text_query, {"ParticipantID": 1, "textEntryCount": 1, "_id": 1})
        print("Participant log documents being deleted because they have no data associated with them:")
        for doc in p_log_zero_docs:
            print(f"  - ID: {doc['_id']}, ParticipantID: {doc['ParticipantID']}, textEntryCount: {doc['textEntryCount']}")
    
    total_deleted = 0
    
    if text_count > 0:
        text_result = text_results.delete_many(text_query)
        total_deleted += text_result.deleted_count
    
    if p_log_count > 0:
        p_log_result = p_log.delete_many(p_log_query)
        total_deleted += p_log_result.deleted_count
    
    if p_log_zero_count > 0:
        p_log_zero_result = p_log.delete_many(p_log_zero_text_query)
        total_deleted += p_log_zero_result.deleted_count
    
    return total_deleted