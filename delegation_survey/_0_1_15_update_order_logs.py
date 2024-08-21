def update_order_logs(mongoDB):

    medic_mapping = {
        'TAD-Adept-Desert-high': 'D1',
        'TAD-Adept-Desert-low': 'K1',
        'kitware-Adept-Desert-high': 'J1',
        'kitware-Adept-Desert-low': 'R1',
        'TAD-Adept-Submarine-high': 'S1',
        'TAD-Adept-Submarine-low': 'Z1',
        'kitware-Adept-Submarine-high': 'Y1',
        'kitware-Adept-Submarine-low': 'F2',
        'TAD-Adept-Jungle-high': 'P0',
        'TAD-Adept-Jungle-low': 'W0',
        'kitware-Adept-Jungle-high': 'V0',
        'kitware-Adept-Jungle-low': 'C1',
        'TAD-Adept-Urban-high': 'A0',
        'TAD-Adept-Urban-low': 'H0',
        'kitware-Adept-Urban-high': 'G0',
        'kitware-Adept-Urban-low': 'N0',
        'TAD-SoarTech-Desert-high': 'G2',
        'TAD-SoarTech-Desert-low': 'N2',
        'kitware-SoarTech-Desert-high': 'M2',
        'kitware-SoarTech-Desert-low': 'U2',
        'TAD-SoarTech-Submarine-high': 'J3',
        'TAD-SoarTech-Submarine-low': 'R3',
        'kitware-SoarTech-Submarine-high': 'Q3',
        'kitware-SoarTech-Submarine-low': 'X3',
        'TAD-SoarTech-Jungle-high': 'V2',
        'TAD-SoarTech-Jungle-low': 'C3',
        'kitware-SoarTech-Jungle-high': 'B3',
        'kitware-SoarTech-Jungle-low': 'I3',
        'TAD-SoarTech-Urban-high': 'Y3',
        'TAD-SoarTech-Urban-low': 'F4',
        'kitware-SoarTech-Urban-high': 'E4',
        'kitware-SoarTech-Urban-low': 'L4'
    }
     
    survey_results_collection = mongoDB['surveyResults']
    survey_results = survey_results_collection.find({})

    for result in survey_results:
        if ('results' not in result or 'surveyVersion' not in result['results'] or result['results']['surveyVersion'] != 3 or 'orderLog' not in result['results']):
            continue
        updatedOrderLog = []
        for entry in result['results']['orderLog']:
            parts = entry.split('-')
            if len(parts) == 6:
                
                number, alignment, company, environment, _, difficulty = parts
                
                alignment = 'kitware' if alignment == 'kitware-hybrid-kaleido' else alignment
                key = f"{alignment}-{company}-{environment}-{difficulty}"
                
                medic_name = medic_mapping.get(key, "")
                
                new_entry = f"{number}-{medic_name}-{alignment}-{company}-{environment}-{_}-{difficulty}"
                
                updatedOrderLog.append(new_entry)

        result['results']['updatedOrderLog'] = updatedOrderLog
        survey_results_collection.update_one(
                {'_id': result['_id']},
                {'$set': result}
            )
        
    print("Updated order logs field added to survey version 3 results")