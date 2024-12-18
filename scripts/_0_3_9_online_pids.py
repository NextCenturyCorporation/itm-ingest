'''
Update the results of the online survey to make sure participant id is stored where we want it
'''

def main(mongo_db):
    survey_collection = mongo_db['surveyResults']
    online_surveys = survey_collection.find({"results.pid": {"$exists": True}})
    for doc in online_surveys:
        doc_id = doc['_id']
        survey_collection.update_one({'_id': doc_id}, {'$set': {'results.Participant ID Page.questions.Participant ID.response': doc['results']['pid']}})
