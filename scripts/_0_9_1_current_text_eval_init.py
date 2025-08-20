def main(mongo_db):
    current_text_eval = mongo_db['textEvalVersion']

    doc = {
        'eval': 'Phase 2 July 2025 Collaboration'
    }

    current_text_eval.insert_one(doc)