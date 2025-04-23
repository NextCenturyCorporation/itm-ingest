'''
We started placing the pid towards the top level of survey results documents `results.pid`
This retroactively applies that to older documents 
Makes it easier for future processing of survey data
ALSO, this script deletes garbage documents that were added to this collection by cyber a while back (around MRE time)
'''
def main(mongo_db):
    survey_results = mongo_db["surveyResults"]

    query = {
        "results": {"$exists": True},
        "$or": [
            {"evalNumber": {"$gte": 3}},
            {"results.evalNumber": {"$gte": 3}}
        ]
    }

    surveys = survey_results.find(query)

    for survey in surveys:
        if "results" in survey and not isinstance(survey["results"], dict):
            # deletes cyber inserted noise from db
            survey_results.delete_one({"_id": survey["_id"]})
            continue
        try:
            if "Participant ID Page" in survey["results"]:
                participant_id_page = survey["results"]["Participant ID Page"]
            elif "Participant ID" in survey["results"]:
                # some very old (1.1 1.2) data has a different page name
                participant_id_page = survey["results"]["Participant ID"]
            else:
                continue


            if isinstance(participant_id_page["questions"], list):
                # some invalid incomplete documents
                continue
            else:
                pid = participant_id_page["questions"]["Participant ID"]["response"]


            # most from eval 5 onward have it already
            if "pid" not in survey["results"]:
                survey_results.update_one(
                    {"_id": survey["_id"]},
                    {"$set": {"results.pid": pid}}
                )
        except KeyError:
            # dont need to do anything, just means that survey doesnt have that field (incomplete or old)
            pass
