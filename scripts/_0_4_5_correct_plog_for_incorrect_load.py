def main(mongo_db):
    p_log = mongo_db['participantLog']
    bad_pids = ['202411514', '202411534', '202411536', '202411537', '202411539', '202411541', '202411543', '202411544', '202411545', '202411547', '202411556', '202411327', '202411337', '202411568', '202411573']
    
    for pid in bad_pids:
        result = p_log.update_one(
            {"ParticipantID": int(pid)},
            {
                "$set": {
                    "Del-1": "AD-1",
                    "Del-2": "ST-3",
                    "ADMOrder": 1
                }
            }
        )
        if result.modified_count > 0:
            print(f"Updated entry for ParticipantID: {pid}")
        else:
            print(f"No entry found for ParticipantID: {pid}")