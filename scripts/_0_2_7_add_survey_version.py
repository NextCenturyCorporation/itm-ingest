def add_survey_version_collection(mongo_db):
    survey_version_collection = mongo_db['surveyVersion']

    version_document = {'version': '4'}
    
    survey_version_collection.insert_one(version_document)
    
    print("Survey version collection created with initial document.")