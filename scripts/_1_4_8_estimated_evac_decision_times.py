from misc_scripts.evac_response_window import compute_evac_windows


def main(mongo_db):
    counter = 0
    tcccResults = mongo_db['tcccResults']
    for pid, window_seconds, confidence in compute_evac_windows('TCCC-Trainer'):
        estimated_time = str(round(window_seconds, 3)) if window_seconds is not None else ""

        result = tcccResults.update_one({"_id": str(pid)},
            {"$set": {
                "tccc_analysis.Estimated Evac Decision Time": estimated_time,
                "tccc_analysis.Estimated Evac Decision Time Confidence": confidence
            }}
        )

        counter += result.matched_count

    print(f"Finished updating {counter} documents")
