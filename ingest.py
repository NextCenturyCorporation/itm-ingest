import json
from pymongo import MongoClient

host = 'localhost'
port = 27017
database_name = 'dashboard'
collection_name = 'testing_collection'

def read_json_file(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data

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
    db = create_connection()
    print(db)
    
    created_collection = create_collection(collection_name)
    print(created_collection)

    json_file_path = 'example.json'  
    json_data = read_json_file(json_file_path)

    upload_to_mongodb(json_data, collection_name)


