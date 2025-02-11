def main(mongo_db):
    surveys = mongo_db['surveyResults']
    surveys.update_one(
        {"results.pid": "202501722"},
        {"$set": {"results.evalNumber": 6, "results.evalName": "Jan 2025 Eval"}}
    )