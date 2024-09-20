import base64
import PIL
from PIL import Image
from io import BytesIO

def decode_image(base64_string):
    # Decode the Base64 string
    image_data = base64.b64decode(base64_string)
    # Convert the binary data to an image
    image_obj = Image.open(BytesIO(image_data))

    return image_obj

def encode_image_file(image_file):
    with open(image_file, 'rb') as image_file:
        # Read the image file
        image_data = image_file.read()
        # Encode the image data using Base64
        base64_encoded_data = base64.b64encode(image_data)
        # Convert the encoded bytes to a string
        base64_string = base64_encoded_data.decode('utf-8')


    return base64_string

def encode_image_bytesio(image_obj_bio):
    return base64.b64encode(image_obj_bio.getvalue()).decode('utf-8')

def save_image(image_obj, filename):
    return image_obj.save(filename)

def reduce_image(image_obj, img_format, new_size_ratio=0.75, compression_level=50):
    #Allocated mem for image obj (so I don't have to save to file)
    temp_image_obj = BytesIO()

    #Resize
    resize_image_obj = image_obj.resize((int(image_obj.width * new_size_ratio), int(image_obj.height * new_size_ratio)), PIL.Image.NEAREST)

    #Save to memory
    # note PNG's are lossless, so compression_level has no effect
    rgb_image_obj.save(temp_image_obj, format=img_format, optimize=True, quality=compression_level)

    return temp_image_obj

def convert_reduce_png_to_jpeg(image_obj, new_size_ratio=0.75, compression_level=50):
    #Allocated mem for image obj (so I don't have to save to file)
    temp_image_obj = BytesIO()

    #Resize
    resize_image_obj = image_obj.resize((int(image_obj.width * new_size_ratio), int(image_obj.height * new_size_ratio)), PIL.Image.NEAREST)

    #Save to memory
    rgb_image_obj = image_obj.convert('RGB')
    rgb_image_obj.save(temp_image_obj, format="JPEG", optimize=True, quality=compression_level)

    return temp_image_obj

def image_data_from_file(image_file):
    with open(image_file, 'rb') as image_file:
        image_data = image_file.read()

    return image_data