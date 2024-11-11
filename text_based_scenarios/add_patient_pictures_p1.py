import os
import base64
from pymongo import MongoClient
from decouple import config

folder_to_scenario_mappings = {
    "qol-eval2": "qol-ph1-eval-2",
    "qol-eval3": "qol-ph1-eval-3",
    "qol-eval4": "qol-ph1-eval-4",
    "vol-eval2": "vol-ph1-eval-2",
    "vol-eval3": "vol-ph1-eval-3",
    "vol-eval4": "vol-ph1-eval-4",
}


def main():
    client = MongoClient(config("MONGO_URL"))
    db = client.dashboard
    textbased_images_collection = db["textBasedImages"]

    current_dir = os.path.dirname(os.path.abspath(__file__))
    picture_folder = os.path.join(current_dir, "phase-1-st-screenshots")

    documents_to_insert = []

    for root, dirs, files in os.walk(picture_folder):
        for file in files:
            file_path = os.path.join(root, file)
            casualty_id = os.path.splitext(file)[0]

            folder_name = os.path.basename(root)

            scenario_id = folder_to_scenario_mappings.get(folder_name, "unknown")

            # convert to byte code
            with open(file_path, "rb") as image_file:
                image_byte_code = base64.b64encode(image_file.read()).decode("utf-8")

            document = {
                "casualtyId": casualty_id,
                "imageByteCode": image_byte_code,
                "scenarioId": scenario_id,
            }

            documents_to_insert.append(document)
            print(
                f"Processed {file} with casualtyId: {casualty_id}, scenarioId: {scenario_id}"
            )

    if documents_to_insert:
        result = textbased_images_collection.insert_many(documents_to_insert)
    else:
        print("No documents to insert.")


if __name__ == "__main__":
    main()
