def main(mongo_db):
    current_text_eval = mongo_db['textEvalVersion']
    pid_bounds = mongo_db['pidBounds']

    eval_doc = {
        'eval': 'Phase 2 July 2025 Collaboration'
    }

    current_text_eval.insert_one(eval_doc)

    pid_doc = {
        'lowPid': 202570100,
        'highPid': 202570299
    }

    pid_bounds.insert_one(pid_doc)