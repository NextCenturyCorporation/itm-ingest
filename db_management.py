import json_util
from pymongo import MongoClient
import os
import json

database_name = "dashboard"

def upload_to_mongodb(data, collection_name, client):
    """
    Upload session json to MongoDB 

    Args:
        data: Data to be uploaded as a document. (already parsed in json_util)
        collection_name: Name of the MongoDB collection.
        client: MongoDB client.

    Prints a message indicating the successful upload and the document ID.
    """

    db = client[database_name]
    collection = db[collection_name]

    result = collection.insert_one(data)

    print(f"Data uploaded to MongoDB with document ID: {result.inserted_id}")

def create_collection(collection_name, client):
    """
    Create new mongoDB collection

    Args:
        collection_name: Name of the MongoDB collection.
        client: MongoDB client.

    Returns:
        The created or existing collection.

    Prints a message indicating whether the collection was created or already existed. Returns collection.
    """

    db = client[database_name]

    try:
        # Check if the collection already exists
        if collection_name in db.list_collection_names():
            print(f"Collection '{collection_name}' already exists.")
        else:
            # If the collection doesn't exist, create it
            db.create_collection(collection_name)
            print(f"Collection '{collection_name}' created successfully.")

        # Return the collection object, whether it's new or existing
        return db[collection_name]
    except Exception as e:
        print(f"Error creating collection '{collection_name}': {e}")
        return None

def upload_json_file(file_path, collection_name, client):
    """
    Upload a JSON file to a MongoDB collection.

    Args:
        file_path: Path to the JSON file.
        collection_name: Name of the MongoDB collection.
        client: MongoDB client.

    Skips non-JSON files and prints a message upon successful upload.
    """
    if not json_util.is_json_file(file_path):
        print(f"Skipping non-JSON file: {file_path}")
        return

    # Read JSON data from the file
    json_data = json_util.read_json_file(file_path)
    
    # Upload the JSON data to the specified collection
    upload_to_mongodb(json_data, collection_name, client)

def upload_json_files_in_folder(folder_path, collection_name, client):
    """
    Upload JSON files in a folder to a MongoDB collection.

    Args:
        folder_path: Path to the folder containing JSON files.
        collection_name: Name of the MongoDB collection.
        client: MongoDB client.

    Checks for the existence of the folder and uploads JSON files found within it.
    """
    if not os.path.exists(folder_path):
        print(f"Error: The specified folder '{folder_path}' does not exist.")
        return

    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)
        if os.path.isfile(item_path):
            upload_json_file(item_path, collection_name, client)

def empty_collection(collection_name, client):
    """
    Empty a MongoDB collection.

    Args:
        collection_name: Name of the MongoDB collection to be emptied.
        client: MongoDB client.

    Deletes all documents in the collection and prints a message with the count of deleted documents.
    """
    db = client[database_name]
    collection = db[collection_name]

    try:
        # Delete all documents in the collection
        result = collection.delete_many({})
        print(f"Collection '{collection_name}' emptied. Deleted {result.deleted_count} documents.")
    except Exception as e:
        print(f"Error emptying collection '{collection_name}': {e}")

def delete_by_session_id(collection_name, session_id, client):
    """
    Delete a document by session_id from a MongoDB collection.

    Args:
        collection_name: Name of the MongoDB collection.
        session_id: The session_id used for document deletion.
        client: MongoDB client.

    Deletes a document with the specified session_id and prints a success or not found message.
    """
    db = client[database_name]
    collection = db[collection_name]

    try:
        result = collection.delete_one({"session_id": session_id})
        if result.deleted_count == 1:
            print(f"Document with session_id '{session_id}' deleted successfully.")
        else:
            print(f"No document with session_id '{session_id}' found for deletion.")
    except Exception as e:
        print(f"Error deleting document with session_id '{session_id}': {e}")

def update_by_session_id(collection_name, session_id, update_data, client):
    """
    Update a document by session_id in a MongoDB collection.

    Args:
        collection_name: Name of the MongoDB collection.
        session_id: The session_id used for document update.
        update_data: Data for updating the document.
        client: MongoDB client.

    Replaces a document with the specified session_id and prints a success or not found message.
    """
    db = client[database_name]
    collection = db[collection_name]

    try:
        query = {"session_id": session_id}
        result = collection.update_one(query, {"$set": update_data})
        if result.modified_count > 0:
            print(f"Document with session_id '{session_id}' updated successfully.")
        else:
            print(f"No document with session_id '{session_id}' found for updating.")
    except Exception as e:
        print(f"Error updating document by session_id: {e}")

def query_by_session_id(collection_name, session_id, client):
    """
    Query data by session_id from a MongoDB collection.

    Args:
        collection_name: Name of the MongoDB collection.
        session_id: The session_id used for document retrieval.
        client: MongoDB client.
    
    Returns:
        Entry with matching session_id or None if it doesn't exist.

    Retrieves and prints data for the specified session_id.
    """
    db = client[database_name]
    collection = db[collection_name]

    try:
        query = {"session_id": session_id}
        result = collection.find_one(query)
        if result:
            print(f"Data for session_id '{session_id}': {result}")
            return result
        else:
            print(f"No data found for session_id '{session_id}'.")
            return None
    except Exception as e:
        print(f"Error querying data by session_id: {e}")

def backup_whole_collection(collection_name, backup_collection_name, client):
    """
    Create a backup of a whole MongoDB collection.

    Args:
        collection_name: Name of the MongoDB collection to be backed up.
        backup_collection_name: Name of the new backup collection.
        client: MongoDB client.

    Creates a backup by copying the entire collection and prints a confirmation message.
    """
    db = client[database_name]

    try:
        db.command("create", backup_collection_name, source=collection_name)
        print(f"Collection '{collection_name}' backed up to '{backup_collection_name}'")
    except Exception as e:
        print(f"Error creating full backup: {e}")

def export_data_by_session_id(collection_name, session_id, output_file, client):
    """
    Export data from a MongoDB collection based on session_id to a JSON file.

    Args:
        collection_name: Name of the MongoDB collection to export data from.
        session_id: The session_id used to filter the document for export.
        output_file: Path to the JSON file where the data will be exported.
        client: MongoDB client.

    Returns:
        The exported data document.

    """
    db = client[database_name]
    collection = db[collection_name]

    exported_data = None

    try:
        query = {"session_id": session_id}
        result = collection.find_one(query)

        if result:
            exported_data = result

            with open(output_file, "w") as f:
                json.dump(exported_data, f, default=str)

            print(f"Data for session_id '{session_id}' exported to {output_file}")
        else:
            print(f"No data found for session_id '{session_id}'.")
    except Exception as e:
        print(f"Error exporting data by session_id: {e}")

    return exported_data
