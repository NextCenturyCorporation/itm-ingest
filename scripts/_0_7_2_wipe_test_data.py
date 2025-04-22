def main(mongo_db):
    survey_results = mongo_db['surveyResults']

    start_date = "Mon Apr 21 2025 00:00:00 GMT-0400 (Eastern Daylight Time)"
    end_date = "Mon Apr 21 2025 23:59:59 GMT-0400 (Eastern Daylight Time)"

    delete_result = survey_results.delete_many({
        "$or": [
            {"results.timeComplete": {"$gte": start_date, "$lte": end_date}},
            {"results.startTime": {"$gte": start_date, "$lte": end_date}}
        ]
    })

    print(f"Deleted {delete_result.deleted_count} entries from April 21st, 2025")