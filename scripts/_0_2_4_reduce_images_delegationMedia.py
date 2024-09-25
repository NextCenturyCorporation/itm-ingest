import utils.image_utils as image_utils
import PIL
import os
from PIL import Image


def reduce_images_delegationMedia(mongoDB):
    delegationMedia_col = mongoDB['delegationMedia']
    delegationMedia_res = delegationMedia_col.find({}, {"_id":1, "url":1})
    
    # Config permission doesn't allow dataSize command
    # delegationMedia_size_orig = mongoDB.command('dataSize', 'delegationMedia')
    # print("delegationMedia Original Size: " + (delegationMedia_size_orig/1024) + " kb" )

    for result in delegationMedia_res:
        oid = result["_id"]
        base64_str = result["url"]
        
        file_size = (len(base64_str) * 6 - base64_str.count('=') * 8) / 8
        print("Original Size: " + str('{0:.2f}'.format(file_size/1024)) + " kb")
        
        image_obj = image_utils.decode_image(base64_str)
        # if you want to compare images, PNG version:
        # image_obj.show()
        image_obj.save(str(oid) + ".png")

        # Front end is decoding as PNG, hence PNG
        reduced_image_obj = Image.open(image_utils.convert_reduce_png_to_jpeg(image_obj, .75, 50))
        # if you want to compare images, JPG version:
        # image_obj.show()
        reduced_image_obj.save(str(oid) + ".jpeg")
      
        # Same to tmp file for encoding 
        reduced_image_obj.save("tmp.jpeg")
        # Encode new image
        reduced_base64_str = image_utils.encode_image_file("tmp.jpeg")
        file_size = (len(reduced_base64_str) * 6 - reduced_base64_str.count('=') * 8) / 8
        print("Reduced Size: " + str('{0:.2f}'.format(file_size/1024)) + " kb")

        # Update record with new Image
        delegationMedia_col.update_one(
            {'_id': result['_id']},
            {'$set': {'url': reduced_base64_str}}
        )
        print(str(oid) + " updated with new image.")

        os.remove("tmp.jpeg")

