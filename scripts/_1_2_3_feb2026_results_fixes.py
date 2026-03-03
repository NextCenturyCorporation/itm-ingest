from scripts._0_8_3_June_Collab_Comparison_Generation import main as gen_comp
from bson import ObjectId
def main(mongo_db):
    # spurious incomplete/empty survey documents messing with results
    # pids: 202602175, 202602143, 202602145, 202602172, 202602176
    ids_to_delete = ['699a1849b2fa81755e9c3205', '699affdab2fa81755e9c6974', '699b50f0b2fa81755e9c839f', '699a0c92b2fa81755e9c2e0b', '699a169eb2fa81755e9c316b']
    survey_collection = mongo_db['surveyResults']
    text_scenario_collection = mongo_db['userScenarioResults']

    result = survey_collection.delete_many({
        '_id': {'$in': [ObjectId(id) for id in ids_to_delete]}
    })
    print(f"Deleted {result.deleted_count} spurious survey documents")
    #6999f2f7b2fa81755e9c25e0 this is the first 171 which should actually be 123
    text_results_to_delete = ['202602176']

    result = text_scenario_collection.delete_many({
        'participantID': {'$in': [id for id in text_results_to_delete]}
    })

    print(f"Deleted {result.deleted_count} spurious text scenario documents")

    # this is the first 171 which should actually be 123
    wrong_pid_doc_id = '6999f2f7b2fa81755e9c25e0'
    correct_pid = '202602123'

    survey_collection.update_one(
        {'_id': ObjectId(wrong_pid_doc_id)},
        {'$set': {
            'results.pid': correct_pid,
            'results.Participant ID Page.questions.Participant ID.response': correct_pid
        }}
    )
    print(f"Updated PID to {correct_pid} for document {wrong_pid_doc_id}")


    #gen_comp(mongo_db, 15)