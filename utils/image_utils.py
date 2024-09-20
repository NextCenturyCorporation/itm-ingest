import base64
from PIL import Image
from io import BytesIO


def decode_image(base64_string)
    # Decode the Base64 string
    image_data = base64.b64decode(base64_string)
    # Convert the binary data to an image
    image_obj = Image.open(BytesIO(image_data))

    return image_obj


def encode_image(image_obj)
    return base64.b64encode(image_obj.read())


def save_image(image_obj, filename)
    return image_obj.save(filename)


def compress_image(image_obj, target_size_ratio=0.75, initial_quality=60):
    img.resize((width, height), Image.ANTIALIAS)
    image_obj.save(output_path, format='PNG', optimize=True, quality=quality)

# Example usage
compress_image('input_image.png', 'compressed_image.png')


def image_data_from_file(image)
    with open(image, 'rb') as image_file:
        image_data = image_file.read()
    return image_data