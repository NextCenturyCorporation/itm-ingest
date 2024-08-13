import os
import base64
from pymongo import MongoClient
from decouple import config

folder_to_scenario_mappings = {
    'Adept Desert': 'DryRunEval-MJ5-eval',
    'Adept Jungle': 'DryRunEval-MJ4-eval',
    'Adept Urban': 'DryRunEval-MJ2-eval',
    'QOL-1': 'qol-dre-1-eval',
    'QOL-2': 'qol-dre-2-eval',
    'QOL-3': 'qol-dre-3-eval',
    'VOL-1': 'vol-dre-1-eval',
    'VOL-2': 'vol-dre-2-eval',
    'VOL-3': 'vol-dre-3-eval',
}

def main():
    client = MongoClient(config('MONGO_URL'))
    db = client.dashboard
    textbased_images_collection = db['textBasedImages']

    # clear the existing collection
    result = textbased_images_collection.delete_many({})
    print(f"Cleared {result.deleted_count} images from the collection.")

    current_dir = os.path.dirname(os.path.abspath(__file__))
    picture_folder = os.path.join(current_dir, 'DRE-Screenshots')

    documents_to_insert = []

    for root, dirs, files in os.walk(picture_folder):
        for file in files:
            if file.lower().endswith('.png'):
                file_path = os.path.join(root, file)
                casualty_id = os.path.splitext(file)[0]
                
                folder_name = os.path.basename(root)
                if 'Adept' not in folder_name:
                    casualty_id = f'casualty_{casualty_id}'

                scenario_id = folder_to_scenario_mappings.get(folder_name, 'unknown')

                # convert to byte code
                with open(file_path, 'rb') as image_file:
                    image_byte_code = base64.b64encode(image_file.read()).decode('utf-8')

                document = {
                    'casualtyId': casualty_id,
                    'imageByteCode': image_byte_code,
                    'scenarioId': scenario_id
                }

                documents_to_insert.append(document)
                print(f"Processed {file} with casualtyId: {casualty_id}, scenarioId: {scenario_id}")

    if documents_to_insert:
        result = textbased_images_collection.insert_many(documents_to_insert)
        print(f"Uploaded {len(result.inserted_ids)} images to MongoDB, replacing the existing collection.")
    else:
        print("No documents to insert.")

if __name__ == "__main__":
    main()