import os
import base64
from pymongo import MongoClient
from decouple import config

def main():
    client = MongoClient(config('MONGO_URL'))
    db = client.dashboard
    textbased_images_collection = db['textBasedImages']

    current_dir = os.path.dirname(os.path.abspath(__file__))
    picture_folder = os.path.join(current_dir, 'DRE-Screenshots')

    for root, dirs, files in os.walk(picture_folder):
        for file in files:
            if file.lower().endswith('.png'):
                file_path = os.path.join(root, file)
                casualty_id = os.path.splitext(file)[0]  # Get filename without extension

                # Read the image and convert to byte code
                with open(file_path, 'rb') as image_file:
                    image_byte_code = base64.b64encode(image_file.read()).decode('utf-8')

                # Prepare the document
                document = {
                    'casualtyId': casualty_id,
                    'imageByteCode': image_byte_code
                }

                # Upload to MongoDB
                textbased_images_collection.insert_one(document)
                print(f"Uploaded {file} to MongoDB")

if __name__ == "__main__":
    main()