'''
https://nextcentury.atlassian.net/browse/ITM-973
This script should be used when prod needs to be cleaned of testing data from a certain date. 
Usage ex. `python clean_data_from_date.py 06/24/2025`
It will clean out the surveyResults, userScenarioResults, and participantLog collections from that date.
'''
import sys
from pymongo import MongoClient
from decouple import config
from datetime import datetime
import re

# parse the date parameter
def parse_date_string(date_str):
    try:
        return datetime.strptime(date_str, "%m/%d/%Y")
    except ValueError:
        raise ValueError(f"Invalid date format: {date_str}. Expected format: mm/dd/yyyy")

# pull out the date to match format stored in mongo db
def extract_date_from_string(date_string):
    if not date_string:
        return None
    
    pattern = r'([A-Za-z]{3})\s+([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})'
    match = re.search(pattern, date_string)
    
    if match:
        month_str = match.group(2)
        day = int(match.group(3))
        year = int(match.group(4))

        months = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }
        
        if month_str in months:
            month = months[month_str]
            return datetime(year, month, day)
    
    return None


def delete_data_from_date(date):
    target_date = parse_date_string(date)
    print(f"Deleting data from date: {target_date.strftime('%Y-%m-%d')}")
    mongo_url = config('MONGO_URL')
    client = MongoClient(mongo_url)
    db = client['dashboard']
    
    # collections to wipe
    text_based = db['userScenarioResults']
    survey_results = db['surveyResults']
    participant_log = db['participantLog']

    participant_ids_to_delete = set()
    
    # userScenarioResults
    print("\nProcessing userScenarioResults...")
    text_cursor = text_based.find({})
    text_delete_count = 0
    
    for doc in text_cursor:
        if 'startTime' in doc:
            doc_date = extract_date_from_string(doc['startTime'])
            if doc_date and doc_date.date() == target_date.date():
                if 'participantID' in doc:
                    participant_ids_to_delete.add(str(doc['participantID']))
                
                text_based.delete_one({'_id': doc['_id']})
                text_delete_count += 1
    
    print(f"Deleted {text_delete_count} documents from userScenarioResults")
    
    # surveyResults
    print("\nProcessing surveyResults...")
    survey_cursor = survey_results.find({})
    survey_delete_count = 0
    
    for doc in survey_cursor:
        if 'results' in doc and 'startTime' in doc['results']:
            doc_date = extract_date_from_string(doc['results']['startTime'])
            if doc_date and doc_date.date() == target_date.date():
                if 'results' in doc and 'pid' in doc['results']:
                    participant_ids_to_delete.add(str(doc['results']['pid']))
                
                survey_results.delete_one({'_id': doc['_id']})
                survey_delete_count += 1
    
    print(f"Deleted {survey_delete_count} documents from surveyResults")
    
    # p log
    print(f"\nDeleting {len(participant_ids_to_delete)} participants from participantLog...")
    participant_delete_count = 0
    
    for pid in participant_ids_to_delete:
        result = participant_log.delete_many({'ParticipantID': int(pid)})
        participant_delete_count += result.deleted_count
    
    print(f"Deleted {participant_delete_count} documents from participantLog")

    print("DELETION SUMMARY")
    print(f"Date: {target_date.strftime('%m-%d-%Y')}")
    print(f"userScenarioResults: {text_delete_count} documents deleted")
    print(f"surveyResults: {survey_delete_count} documents deleted")
    print(f"participantLog: {participant_delete_count} documents deleted")
    print(f"Total participant IDs processed: {len(participant_ids_to_delete)}")
    if participant_ids_to_delete:
        print(f"Participant IDs: {', '.join(sorted(participant_ids_to_delete))}")
    
    client.close()


def main():
    if len(sys.argv) != 2:
        print("Usage: python clean_data_from_date.py <mm/dd/yyyy>")
        print("Example: python clean_data_from_date.py 06/24/2025")
        return
    
    date = sys.argv[1]
    
    try:
        parse_date_string(date)
    except ValueError as e:
        print(f"Error: {e}")
        return
    
    try:
        delete_data_from_date(date)
        print("\nDeletion completed successfully!")
    except Exception as e:
        print(f"\nError during deletion: {e}")

if __name__ == "__main__":
    sys.exit(main())