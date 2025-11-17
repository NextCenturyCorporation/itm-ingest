def main(mongo_db):
    mongo_db['userScenarioResults'].delete_many({
        'participantID': 'undefined',
        'evalNumber': 13
    })