from scripts._0_8_3_June_Collab_Comparison_Generation import main as gen_comp
from bson import ObjectId


def rescore_observed_adms():
    pass


def main(mongo_db):
    text_collec = mongo_db['userScenarioResults']
    # pid to remove bad second run: 137, 148, 152, 160
    bad_text_docs = {
        '202606137': ['6a344ae462f0ee5e0f35ea25', '6a344ae462f0ee04af35ea27', '6a344ae462f0eeb9e435ea29', '6a344ae462f0ee7f9735ea2b'],
        '202606148': ['6a3dbb3162f0ee4f6f35fb4b', '6a3dbb3162f0eea81835fb49', '6a3dbb3162f0eed38d35fb47', '6a3dbb3162f0ee2ffd35fb45', '6a3dbb0e62f0ee186d35fb41', '6a3dbb0e62f0ee68da35fb3f'],
        '202606152': ['6a3d90b662f0eedd5f35fade', '6a3d90b662f0ee56da35fae1'],
        '202606160': ['6a3e6b5062f0ee046635fbda', '6a3e6b4f62f0eeb4dc35fbd7']
    }

    # remove bad text docs before we make any comparison scores
    for pid, oid_strings in bad_text_docs.items():
        object_ids = [ObjectId(oid) for oid in oid_strings]
        text_collec.delete_many({'_id': {'$in': object_ids}})


    #re score observed adm run alignment scores
    rescore_observed_adms()
    #gen_comp(mongo_db, EVAL_NUMBER=17)