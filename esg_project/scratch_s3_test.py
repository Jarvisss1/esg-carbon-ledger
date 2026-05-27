import os
import boto3
from botocore.config import Config

# Credentials
access_key = "6ab50edbea92e9078a8570a188a186d4"
secret_key = "945935fd10fb588852a99e230ca8ec34f6939bb91348c372930644f57d3c5811"
bucket_name = "raw_data"
endpoint_url = "https://bapkrtqntvdwhqtbppgf.storage.supabase.co/storage/v1/s3"
region_name = "ap-northeast-1"

print("Initializing S3 client...")
try:
    s3_client = boto3.client(
        's3',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        endpoint_url=endpoint_url,
        region_name=region_name,
        config=Config(signature_version='s3v4')
    )
    
    print("Listing buckets...")
    response = s3_client.list_buckets()
    print("Buckets found:")
    for bucket in response.get('Buckets', []):
        print(f" - {bucket['Name']}")
        
    print("\nListing objects in bucket raw_data...")
    try:
        objs = s3_client.list_objects_v2(Bucket=bucket_name)
        print("Objects in raw_data:")
        for obj in objs.get('Contents', []):
            print(f" - {obj['Key']} ({obj['Size']} bytes)")
    except Exception as e:
        print(f"Error listing objects: {e}")
        
    print("\nTrying to upload a small test file...")
    test_key = "test_upload.txt"
    test_content = b"Hello Supabase Storage S3 from Antigravity!"
    s3_client.put_object(Bucket=bucket_name, Key=test_key, Body=test_content)
    print("Upload successful!")
    
    print("\nTrying to read the uploaded test file...")
    get_resp = s3_client.get_object(Bucket=bucket_name, Key=test_key)
    read_content = get_resp['Body'].read()
    print(f"Content read back: {read_content}")
    
    print("\nCleaning up test file...")
    s3_client.delete_object(Bucket=bucket_name, Key=test_key)
    print("Cleanup successful! Connection test completed successfully.")
    
except Exception as e:
    print(f"Error during S3 operations: {e}")
