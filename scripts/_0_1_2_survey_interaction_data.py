import re
import csv
def survey_interaction_data(mongoDB):
    survey_results_collection = mongoDB['surveyResults']

    query = {
        "results.surveyVersion": 2
    }

    metrics_results = survey_results_collection.find(query)
    csv_data = []

    for result in metrics_results:
        try:
            results = result['results']
            participant_id = results['Participant ID Page']['questions']['Participant ID']['response']
            if re.search(r'test', participant_id, re.IGNORECASE) is None:
                for key, value in results.items():
                    if (isinstance(value, dict) and 'scenarioName' in value and value['pageType'] == "singleMedic" and 'Omnibus' not in value['scenarioName']):
                        questions = value['questions']
                        if questions:
                            first_question_key, first_question_value = list(questions.items())[0]
                            csv_data.append([participant_id, key, first_question_value.get('response')])
        except KeyError:
            print("")
    with open("output_file.csv", 'w', newline='') as f:
        writer = csv.writer(f)
        # Writing the header
        writer.writerow(["Participant ID", "Scenario", "User Interactions"])
        
        # Writing rows
        for row in csv_data:
            writer.writerow(row)

