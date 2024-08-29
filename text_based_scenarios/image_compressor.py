import os
from PIL import Image

def compress_image(image_path, target_size_ratio=0.25, initial_quality=85):
    with Image.open(image_path) as img:
        # Convert to RGB if necessary
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        original_size = os.path.getsize(image_path)
        quality = initial_quality
        
        while True:
            # Save to a temporary file
            temp_path = image_path + ".temp"
            img.save(temp_path, format='JPEG', quality=quality, optimize=True)
            
            new_size = os.path.getsize(temp_path)
            
            if new_size <= original_size * target_size_ratio or quality <= 20:
                os.replace(temp_path, image_path)
                break
            else:
                os.remove(temp_path)
                quality -= 5
        
        compression_ratio = new_size / original_size
        print(f"Processed: {image_path}")
        print(f"Original size: {original_size / 1024:.2f} KB")
        print(f"New size: {new_size / 1024:.2f} KB")
        print(f"Compression ratio: {compression_ratio:.2%}")
        print(f"Final quality: {quality}")
        print("------------------------")

def main():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    picture_folder = os.path.join(current_dir, 'DRE-Screenshots')

    for root, dirs, files in os.walk(picture_folder):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                file_path = os.path.join(root, file)
                compress_image(file_path)

if __name__ == "__main__":
    main()
    print("All images have been processed and overwritten.")