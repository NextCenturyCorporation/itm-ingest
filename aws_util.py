import ingest
import boto3
import logging
import os
def main():
    client = ingest.create_connection()

# listing out buckets i've made 
def list_bucket():
    try:
        s3 = boto3.client('s3')
        response = s3.list_buckets()
        if response:
            for bucket in response['Buckets']:
                print(f'{bucket["Name"]}')
    except Exception as e:
        logging.error(e)
        return False
    return True

# make a new bucket with name following these requirements https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html
def create_bucket(bucket_name):
    try:
        s3_client = boto3.client('s3')
        s3_client.create_bucket(Bucket=bucket_name)
    except Exception as e:
        logging.error(e)

def upload_file_to_bucket(file_name, bucket, object_name=None):
    if object_name is None:
        object_name = os.path.basename(file_name)
    
    s3_client = boto3.client('s3')
    try:
        response = s3_client.upload_file(file_name, bucket, object_name)
    except Exception as e:
        logging.error(e)
        return False
    return True

def download_file(file_name, bucket, object_name):
    s3_client = boto3.client('s3')
    try:
        s3_client.download_file(bucket, object_name, file_name)
    except Exception as e:
        logging.error(e)
        return False
    return True

def delete_file(bucket, key_name):
    s3_client = boto3.client('s3')
    try:
        s3_client.delete_object(Bucket=bucket, Key=key_name)
    except Exception as e:
        logging.error(e)
        return False
    return True

def delete_bucket(bucket):
    s3_client = boto3.client('s3')
    try:
        bucket = s3_client.delete_bucket(Bucket=bucket)
    except Exception as e:
        logging.error(e)
        return False
    return True

if __name__ == '__main__':
    upload_file_to_bucket("example.json", "awstestingnopp")
    