import argparse
from json_util import read_json_file, is_json_file
from pymongo import MongoClient
import os

database_name = "dashboard"
collection_name = "testing_collection"
user='simplemongousername'
password='simplemongopassword'
#host='dashboard-mongo:27017'
host = 'localhost:27017'

def upload_to_mongodb(data, collection_name, client):
    db = client[database_name]
    collection = db[collection_name]

    result = collection.insert_one(data)

    print(f"Data uploaded to MongoDB with document ID: {result.inserted_id}")


def create_collection(collection_name, client):
    db = client[database_name]

    try:
        if collection_name in db.list_collection_names():
            print(f"Collection '{collection_name}' already exists.")
        else:
            db.create_collection(collection_name)
            print(f"Collection '{collection_name}' created successfully.")

        # Return the collection whether it's new or existing
        return db[collection_name]
    except Exception as e:
        print(f"Error creating collection '{collection_name}': {e}")
        return None


def create_connection():
    # auth failed
    # client = MongoClient(host, username=user, password=password, authSource="dashboard")
    client = MongoClient(host)
    return client


def upload_json_file(file_path, collection_name, client):
    if not is_json_file(file_path):
        print(f"Skipping non-JSON file: {file_path}")
        return

    json_data = read_json_file(file_path)
    upload_to_mongodb(json_data, collection_name, client)


def upload_json_files_in_folder(folder_path, collection_name, client):
    if not os.path.exists(folder_path):
        print(f"Error: The specified folder '{folder_path}' does not exist.")
        return

    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)
        if os.path.isfile(item_path):
            upload_json_file(item_path, collection_name, client)

def empty_collection(collection_name, client):
    db = client[database_name]
    collection = db[collection_name]

    try:
        result = collection.delete_many({})
        print(f"Collection '{collection_name}' emptied. Deleted {result.deleted_count} documents.")
    except Exception as e:
        print(f"Error emptying collection '{collection_name}': {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload JSON data to MongoDB")
    parser.add_argument(
        "input_path",
        help="Path to the JSON file or folder containing JSON files to upload",
    )
    args = parser.parse_args()

    client = create_connection()

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

