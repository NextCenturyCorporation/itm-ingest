from pymongo import MongoClient
import boto3, os, csv, calendar
from tccc_analyzer import SimAnalyzer
from decouple import config
# from botocore.exceptions import ClientError

def lambda_handler(event, context):
    bucket = event["Records"][0]["s3"]["bucket"]["name"]
    key = event["Records"][0]["s3"]["object"]["key"]
    csv_file = os.path.basename(key)
    json_key = key.replace('csv', 'json')
    json_file = os.path.basename(json_key)

    # s3 = boto3.client('s3')
    # s3.download_file(bucket, key, '/tmp/' + csv_file)
    # try:
    #     s3.head_object(Bucket=bucket, Key=json_key)
    #     s3.download_file(bucket, json_key, '/tmp/' + json_file)
    # except ClientError:
    #     pass


    analyzer = SimAnalyzer('C:/tmp')

    pid = csv_file.split('.csv')[0]
    pid = pid.split('Clean')[0]
    if '_' in pid:
        pid = pid.split('_')[1]
    analyzer.load_scenario_data('C:/tmp/' + csv_file)
    analyzer.initialize_participant(pid)
    data = analyzer.listify_data('C:/tmp/' + csv_file)
    to_analyze = 'C:/tmp/' + csv_file
    json_path = to_analyze.replace('.csv', '.json')
    
    if os.path.exists(json_path):
        analyzer.load_json_data(json_path)

    analyzer.analyze_file(pid, data)

    analyzer.generate_csv()
    analyzer.get_all_tagging_data()
    analyzer.calculate_tagging_accuracy_over_time()
    analyzer.record_interaction_times()
    analyzer.record_hc_times()

    analysis_data = None
    interaction_time = None
    ordered_tagging = None
    patient_hc_times = None

    with open('C:/tmp/analyzed.csv', newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['PID'] == pid:
                analysis_data = dict(row)

    with open('C:/tmp/interaction_time.csv', newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['PID'] == pid:
                interaction_time = dict(row)

    with open('C:/tmp/ordered_tagging.csv', newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['Participant'] == pid:
                ordered_tagging = dict(row)
    
    with open('C:/tmp/patient_hc_times.csv', newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['PID'] == pid:
                patient_hc_times = dict(row)

    client = MongoClient(config("MONGO_URL"))
    db = client.dashboard
    tccc_results_collection = db["tcccResults"]
    
    if analysis_data is not None:
        tccc_doc = {
            "pid": pid,
            "eval": calendar.month_name[int(pid[4:6])] + " " + pid[:4],
            "tccc_analysis": analysis_data,
            "ordered_tagging": ordered_tagging,
            "interaction_time": interaction_time,
            "patient_hc_times": patient_hc_times,
        }

        tccc_results_collection.update_one({"_id": pid}, {'$set': tccc_doc}, upsert=True)