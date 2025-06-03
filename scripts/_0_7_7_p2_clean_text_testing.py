def main(mongo_db):
    pids = ['202506100', '202506101', '202506102', '202506103']
    p_log = mongo_db['participantLog']
    text_based = mongo_db['userScenarioResults']
    
    pids_as_numbers = [int(pid) for pid in pids]
    
    result_p_log = p_log.delete_many({'ParticipantID': {'$in': pids_as_numbers}})
    print(f"Deleted {result_p_log.deleted_count} documents from participantLog")
    
    result_text_based = text_based.delete_many({'participantID': {'$in': pids}})
    print(f"Deleted {result_text_based.deleted_count} documents from userScenarioResults")