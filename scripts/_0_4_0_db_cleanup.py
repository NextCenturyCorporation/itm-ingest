from bson.objectid import ObjectId

'''
Update some database entries to match reality and remove duplicate entries
'''

def main(mongo_db):
    survey_collection = mongo_db['surveyResults']
    # 327 took 336's survey
    survey_327 = survey_collection.find_one({"results.pid": '202411336'})
    if survey_327:
        doc_id = survey_327['_id']
        # update pid to 327 (from 336) and update admChoiceProcess
        survey_collection.update_one({'_id': doc_id}, {'$set': {
            'results.Participant ID Page.questions.Participant ID.response': '202411327', 
            'results.pid': '202411327',
            'results.Medic-X2.admChoiceProcess': 'most aligned',
            'results.Medic-B3.admChoiceProcess': 'incorrect survey taken. Is 4 above least aligned',
            'results.Medic-J19.admChoiceProcess': 'incorrect survey taken. Is 1 below most aligned',
            'results.Medic-V21.admChoiceProcess': 'incorrect survey taken. Is 1 below most aligned'}})
        
    text_collection = mongo_db['userScenarioResults']
    # 316 had to go through text twice (except VOL) - remove the duplicate entries
    bad_ids = [
        ObjectId('675760b21a0833d93bca1712'),
        ObjectId('67575f381a08330785ca170e'),
        ObjectId('67575f381a08337187ca170b'),
        ObjectId('67575f381a0833ea6eca1709')
    ]
    text_collection.delete_many({'_id': {'$in': bad_ids}})
