import pandas as pd

def average_time_per_page(pageName, results):
    total_time = 0
    count = 0
    participants_included = []
    for result in results:
        try:
            participant_id = result['results']['Participant ID Page']['questions']['Participant ID']['response']
            if 'test' in participant_id.lower():
                continue

            time_spent = result['results'][pageName]['timeSpentOnPage']
            total_time += time_spent
            count += 1
            participants_included.append(participant_id)
        except KeyError:
            continue
    if count > 0:
        return total_time / count, count, participants_included
    else:
        return None, None, None
    
def comparison_page_times(results, comparison_pages_dict):
    for result in results:
        try:
            participant_id = result['results']['Participant ID Page']['questions']['Participant ID']['response']
            if 'test' in participant_id.lower():
                continue

            comparison_pages = {key: value for key, value in result['results'].items() if 'vs' in key.lower()}
            for page_name, page_data in comparison_pages.items():
                if page_name not in comparison_pages_dict:
                    comparison_pages_dict[page_name] = {
                        'total_time': 0,
                        'count': 0,
                        'participants': []
                    }
                comparison_pages_dict[page_name]['total_time'] += page_data['timeSpentOnPage']
                comparison_pages_dict[page_name]['count'] += 1
                comparison_pages_dict[page_name]['participants'].append(participant_id)
        except KeyError:
            continue

def gen_medic_key(mongo_db):
    configs = mongo_db['delegationConfig']
    version_4 = configs.find_one({"_id": "delegation_v4.0"})
    survey_results = mongo_db['surveyResults']
    eval_4_results = list(survey_results.find({"results.evalNumber": 4}))
    
    pages = version_4['survey']['pages']

    medic_data = []

    for page in pages:
        if "Medic" not in page['name']:
            continue

        average_time, count, participants_included = average_time_per_page(page['name'], eval_4_results)
        
        if count is not None and count > 0:
            medic_info = {
                'medic_name': page['name'],
                'admAuthor': page.get('admAuthor', ''),
                'admAlignment': page.get('admAlignment', ''),
                'admType': page.get('admType', ''),
                'admName': page.get('admName', ''),
                'scenarioName': page.get('scenarioName', ''),
                'admSession': page.get('admSession', ''),
                'averageTimeSpentOnMedic': average_time,
                'numberOfParticipants': count,
                'participantsIncluded': participants_included
            }
            medic_data.append(medic_info)

    df_medic = pd.DataFrame(medic_data)

    comparison_pages_dict = {}
    comparison_page_times(eval_4_results, comparison_pages_dict)

    comparison_data = []
    for page_name, page_info in comparison_pages_dict.items():
        comparison_data.append({
            'comparison_page': page_name,
            'average_time': page_info['total_time'] / page_info['count'] if page_info['count'] > 0 else 0,
            'number_of_participants': page_info['count'],
            'participants': page_info['participants']
        })
    df_comparison = pd.DataFrame(comparison_data)

    # Create an Excel writer object
    excel_file = 'medic_key.xlsx'
    with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
        # Write each dataframe to a different sheet
        df_medic.to_excel(writer, sheet_name='Medic Data', index=False)
        df_comparison.to_excel(writer, sheet_name='Comparison', index=False)

    return excel_file