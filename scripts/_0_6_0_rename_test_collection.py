def main(mongo_db):
    test = mongo_db['test']
    test.rename('admTargetRuns')