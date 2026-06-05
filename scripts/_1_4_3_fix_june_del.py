from scripts._1_4_2_june2026_del import main as redo_del
def main(mongo_db):
    mongo_db['delegation_config'].delete_one({'_id': 'delegation_v12.0'})
    mongo_db['admMedics'].delete_many({'evalNumber': 17})
    redo_del(mongo_db)