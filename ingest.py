import argparse
from json_util import read_json_file, is_json_file
from pymongo import MongoClient
import os

host = 'localhost'
port = 27017
database_name = 'dashboard'
collection_name = 'testing_collection'

def upload_to_mongodb(data, collection_name):
    client = MongoClient(host, port)
    db = client[database_name]
    collection = db[collection_name]

    result = collection.insert_one(data)
    
    print(f"Data uploaded to MongoDB with document ID: {result.inserted_id}")

def create_collection(collection_name):
    client = MongoClient(host, port)
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
    client = MongoClient(host, port)
    db = client[database_name]

    return db

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Upload JSON data to MongoDB')
    parser.add_argument('file_path', help='Path to the JSON file to upload')
    args = parser.parse_args()
    
    if not is_json_file(args.file_path):
        print("Error: The specified file is not a JSON file.")
        exit(1)
    
    db = create_connection()
    print(db)
    
    created_collection = create_collection(collection_name)
    print(created_collection)

    json_file_path = args.file_path
    json_data = read_json_file(json_file_path)

    upload_to_mongodb(json_data, collection_name)

    collection = db[collection_name]
    inserted_data = collection.find_one()
    
    if inserted_data:
        print("Data in the collection:")
        print(inserted_data)
    else:
        print("No data found in the collection.")
