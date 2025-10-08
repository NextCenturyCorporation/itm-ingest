def main(mongo_db):
    collection_names = mongo_db.list_collection_names()
    if 'evaluationIDS' in collection_names:
        collection_orig = mongo_db['evaluationIDS']
        if 'evalData' not in collection_names:
            collection_orig.rename('evalData')
    collection = mongo_db['evalData']
    collection.drop()

    mvp = {
        "evalNumber": 1,
        "evalName": "MVP",
        "pages": {
            "rq1": False,
            "rq2": False,
            "rq3": False,
            "exploratoryAnalysis": False,
            "admProbeResponses": False,
            "admAlignment": True,
            "admResults": True,
            "humanSimPlayByPlay": False, 
            "humanSimProbes": False,
            "participantLevelData": False,
            "textResults": False,
            "programQuestions": False
        }
    }

    sept = {
        "evalNumber": 2,
        "evalName": "September Milestone",
        "pages": {
            "rq1": False,
            "rq2": False,
            "rq3": False,
            "exploratoryAnalysis": False,
            "admProbeResponses": False,
            "admAlignment": True,
            "admResults": True,
            "humanSimPlayByPlay": False, 
            "humanSimProbes": False,
            "participantLevelData": False,
            "textResults": False,
            "programQuestions": False
        }    
    }

    metrics = {
        "evalNumber": 3,
        "evalName": "Metrics Evaluation",
        "pages": {
            "rq1": False,
            "rq2": False,
            "rq3": False,
            "exploratoryAnalysis": False,
            "admProbeResponses": True,
            "admAlignment": True,
            "admResults": True,
            "humanSimPlayByPlay": True, 
            "humanSimProbes": True,
            "participantLevelData": True,
            "textResults": True,
            "programQuestions": True
        }    
    }

    dre = {
        "evalNumber": 4,
        "evalName": "Dry Run Evaluation",
        "pages": {
            "rq1": True,
            "rq2": True,
            "rq3": True,
            "exploratoryAnalysis": True,
            "admProbeResponses": True,
            "admAlignment": True,
            "admResults": True,
            "humanSimPlayByPlay": True, 
            "humanSimProbes": True,
            "participantLevelData": True,
            "textResults": True,
            "programQuestions": True
        }
    }

    ph1 = {
        "evalNumber": 5,
        "evalName": "Phase 1 Evaluation",
        "pages": {
            "rq1": True,
            "rq2": True,
            "rq3": True,
            "exploratoryAnalysis": True,
            "admProbeResponses": True,
            "admAlignment": True,
            "admResults": True,
            "humanSimPlayByPlay": True, 
            "humanSimProbes": True,
            "participantLevelData": True,
            "textResults": True,
            "programQuestions": True
        }
    }

    jan = {
        "evalNumber": 6,
        "evalName": "Jan 2025 Evaluation",
        "pages": {
            "rq1": True,
            "rq2": False,
            "rq3": True,
            "exploratoryAnalysis": True,
            "admProbeResponses": False,
            "admAlignment": False,
            "admResults": False,
            "humanSimPlayByPlay": True, 
            "humanSimProbes": True,
            "participantLevelData": True,
            "textResults": True,
            "programQuestions": False
        }
    }

    experiment = {
        "evalNumber": 7,
        "evalName": "Multi-KDMA experiment",
        "pages": {
            "rq1": False,
            "rq2": True,
            "rq3": False,
            "exploratoryAnalysis": False,
            "admProbeResponses": True,
            "admAlignment": False,
            "admResults": True,
            "humanSimPlayByPlay": False, 
            "humanSimProbes": False,
            "participantLevelData": False,
            "textResults": False,
            "programQuestions": False
        }
    }

    june = {
        "evalNumber": 8,
        "evalName": "Phase II June 2025 Collaboration",
        "pages": {
            "rq1": True,
            "rq2": True,
            "rq3": True,
            "exploratoryAnalysis": True,
            "admProbeResponses": True,
            "admAlignment": True,
            "admResults": True,
            "humanSimPlayByPlay": False, # for now
            "humanSimProbes": False,
            "participantLevelData": True,
            "textResults": True,
            "programQuestions": False # for now
        }
    }

    july = {
        "evalNumber": 9,
        "evalName": "Phase II July 2025 Collaboration",
        "pages": {
            "rq1": True,
            "rq2": True,
            "rq3": True,
            "exploratoryAnalysis": True,
            "admProbeResponses": True,
            "admAlignment": True,
            "admResults": True,
            "humanSimPlayByPlay": False, # for now
            "humanSimProbes": False,
            "participantLevelData": True,
            "textResults": True,
            "programQuestions": False # for now
        }
    }

    phase2_sept = {
        "evalNumber": 10,
        "evalName": "Phase II September 2025 Collaboration",
        "pages": {
            "rq1": True,
            "rq2": False,
            "rq3": False,
            "exploratoryAnalysis": False,
            "admProbeResponses": False,
            "admAlignment": False,
            "admResults": False,
            "humanSimPlayByPlay": False, # for now
            "humanSimProbes": False,
            "participantLevelData": True,
            "textResults": True,
            "programQuestions": False # for now
        }
    }

    fourD = {
        "evalNumber": 11,
        "evalName": "Phase II 4D Experiment",
        "pages": {
            "rq1": False,
            "rq2": False,
            "rq3": False,
            "exploratoryAnalysis": False,
            "admProbeResponses": False, # only false for now
            "admAlignment": False, # only false for now
            "admResults": False, # only false for now
            "humanSimPlayByPlay": False,
            "humanSimProbes": False,
            "participantLevelData": False,
            "textResults": False,
            "programQuestions": False
        }  
    }

    uk_eval = {
        "evalNumber": 12,
        "evalName": "Eval 12 UK Phase 1",
        "pages": {
            "rq1": False,
            "rq2": False,
            "rq3": False,
            "exploratoryAnalysis": False,
            "admProbeResponses": False,
            "admAlignment": False,
            "admResults": False,
            "humanSimPlayByPlay": False, # only false for now
            "humanSimProbes": False, # only false for now
            "participantLevelData": False, # only false for now
            "textResults": True,
            "programQuestions": False
        }  
    }

    collection.insert_many([mvp, sept, metrics, dre, ph1, jan, experiment, june, july, phase2_sept, fourD, uk_eval])