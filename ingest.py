import argparse
from db_management import *
from pymongo import MongoClient
import os

database_name = "dashboard"
collection_name = "testing_collection"
user='simplemongousername'
password='simplemongopassword'
#host='dashboard-mongo:27017'
host = 'localhost:27017'



def create_connection():
    # auth failed
    # client = MongoClient(host, username=user, password=password, authSource="dashboard")
    client = MongoClient(host)
    return client


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload JSON data to MongoDB")
    parser.add_argument(
        "input_path",
        help="Path to the JSON file or folder containing JSON files to upload",
    )
    args = parser.parse_args()

    client = create_connection()
    
    #delete_by_session_id(collection_name, 123, client)
    
    created_collection = create_collection(collection_name, client)
    # uploading one file or directory
    if os.path.isfile(args.input_path):
        upload_json_file(args.input_path, collection_name, client)
    elif os.path.isdir(args.input_path):
        upload_json_files_in_folder(args.input_path, collection_name, client)
    else:
        print(
            f"Error: The specified path '{args.input_path}' is neither a file nor a folder."
        )
    
    all_documents = created_collection.find()
    
    print("Data in the collection:")
    for document in all_documents:
        print(document)
    
    
