import pandas as pd
from datetime import datetime
from collections import defaultdict
scenarios_dict = {}

def parse_time(time_string):
    return datetime.strptime(time_string, "%a %b %d %Y %H:%M:%S GMT%z (Eastern Daylight Time)")

def calc_part_times(participant_id, results):
    # Create a set to keep track of unique combinations
    seen = set()
    filtered_results = []

    for result in results:
        start_time = result.get('startTime')
        scenario_id = result.get('scenario_id')
        
        # Create a unique key using startTime and scenarioID
        key = (start_time, scenario_id)
        
        # If we haven't seen this combination before, add it to filtered_results
        if key not in seen:
            seen.add(key)
            filtered_results.append(result)
    
    # Sort filtered results by timeComplete
    sorted_results = sorted(filtered_results, key=lambda x: parse_time(x['timeComplete']))
    if len(sorted_results) > 5:
        print(f"Participant {participant_id} has more than 5 results: {len(results)}")
    # Use the startTime of the first completed scenario as the overall start time
    overall_start_time = parse_time(sorted_results[0]['startTime'])
    
    for i, scenario in enumerate(sorted_results):
        scenario_id = scenario['scenario_id']
        scenario_type = 'adept' if scenario_id.startswith('Dry') else 'st'
        
        end_time = parse_time(scenario['timeComplete'])
        
        if i == 0:
            # For the first scenario, use its own startTime
            start_time = overall_start_time
        else:
            # For subsequent scenarios, use the previous scenario's end time
            start_time = parse_time(sorted_results[i-1]['timeComplete'])
        
        time_taken = (end_time - start_time).total_seconds()
        
        if scenario_id not in scenarios_dict:
            scenarios_dict[scenario_id] = {
                'type': scenario_type,
                'pids': [],
                'totalTime': 0,
                'count': 0
            }
        scenarios_dict[scenario_id]['pids'].append(participant_id)
        scenarios_dict[scenario_id]['totalTime'] += time_taken
        scenarios_dict[scenario_id]['count'] += 1
        
        #print(f"Processed scenario: {scenario_id}, Time taken: {time_taken} seconds, PID: {participant_id}")
    
    return None

def avg_text_times(mongo_db):
    text_collection = mongo_db['userScenarioResults']
    eval_4_results = list(text_collection.find({"evalNumber": 4}))
    
    grouped_results = {}
    for result in eval_4_results:
        participant_id = result.get('participantID')
        if participant_id not in grouped_results:
            grouped_results[participant_id] = []
        grouped_results[participant_id].append(result)

    for participant_id, participant_results in grouped_results.items():
        calc_part_times(participant_id, participant_results)

    scenario_data = []
    for scenario_id, data in scenarios_dict.items():
        scenario_data.append({
            'scenario_id': scenario_id,
            'type': data['type'],
            'participant_count': len(data['pids']),
            'average_time': data['totalTime'] / data['count'] if data['count'] > 0 else 0,
            'participants': ', '.join(data['pids'])
        })

    df = pd.DataFrame(scenario_data)

    excel_file = 'text_scenario_times.xlsx'
    df.to_excel(excel_file, index=False)

    return excel_file
