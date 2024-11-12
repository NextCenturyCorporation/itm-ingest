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

    processed_count = 0
    updated_count = 0
    inserted_count = 0

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

            result = textbased_images_collection.update_one(
                {
                    "casualtyId": casualty_id,
                    "scenarioId": scenario_id
                },
                {"$set": document},
                upsert=True
            )

            processed_count += 1
            if result.matched_count > 0:
                updated_count += 1
                print(f"Updated document for casualtyId: {casualty_id}, scenarioId: {scenario_id}")
            else:
                inserted_count += 1
                print(f"Inserted new document for casualtyId: {casualty_id}, scenarioId: {scenario_id}")

    print(f"\nProcessing complete:")
    print(f"Total files processed: {processed_count}")
    print(f"Documents updated: {updated_count}")
    print(f"Documents inserted: {inserted_count}")


if __name__ == "__main__":
    main()