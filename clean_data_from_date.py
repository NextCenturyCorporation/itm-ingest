import sys
from pymongo import MongoClient
from decouple import config


def delete_data_from_date(date):
    mongo_url = config('MONGO_URL')
    client = MongoClient(mongo_url)
    db = client['dashboard']
    # three collections that need to be wiped
    text_based = db['userScenarioResults']
    survey_results = db['surveyResults']
    participantLog = db['participantLog']

def main():
    if len(sys.argv) != 2:
        print("Usage: python clean_data_from_date.py <xx/xx/xxxx>")
        print("Example: python clean_data_from_date.py 06/24/2025")
        return
    date = sys.argv[1]
    delete_data_from_date(date)

if __name__ == "__main__":
    main()