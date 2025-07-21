import os
import boto3
from botocore.exceptions import ClientError
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_r2_client():
    """Initializes and returns a boto3 S3 client for Cloudflare R2."""
    try:
        r2_account_id = os.getenv("R2_ACCOUNT_ID")
        r2_access_key_id = os.getenv("R2_ACCESS_KEY_ID")
        r2_secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY")
        r2_endpoint_url = f"https://{r2_account_id}.r2.cloudflarestorage.com"

        if not all([r2_account_id, r2_access_key_id, r2_secret_access_key]):
            logger.error("Missing R2 environment variables. Please check .env file.")
            return None

        s3_client = boto3.client(
            service_name='s3',
            endpoint_url=r2_endpoint_url,
            aws_access_key_id=r2_access_key_id,
            aws_secret_access_key=r2_secret_access_key,
            region_name='auto' # Cloudflare R2 uses 'auto' region
        )
        logger.info("Cloudflare R2 client initialized successfully.")
        return s3_client
    except Exception as e:
        logger.error(f"Error initializing R2 client: {e}")
        return None

def upload_file_to_r2(file_path, object_name=None):
    """Uploads a file to an S3 bucket (R2)."""
    s3_client = get_r2_client()
    if not s3_client:
        return None, "R2 client not initialized."

    bucket_name = os.getenv("R2_BUCKET_NAME")
    if not bucket_name:
        logger.error("R2_BUCKET_NAME not set in environment variables.")
        return None, "R2 bucket name not configured."

    if object_name is None:
        object_name = os.path.basename(file_path)

    try:
        s3_client.upload_file(file_path, bucket_name, object_name)
        public_url = f"{os.getenv('R2_PUBLIC_URL')}/{object_name}"
        logger.info(f"File '{file_path}' uploaded to R2 as '{object_name}'. Public URL: {public_url}")
        return public_url, None
    except ClientError as e:
        logger.error(f"Error uploading file to R2: {e}")
        return None, f"Error uploading file: {e}"
    except Exception as e:
        logger.error(f"An unexpected error occurred during R2 upload: {e}")
        return None, f"An unexpected error occurred: {e}"

def download_file_from_r2(object_name, download_path):
    """Downloads a file from an S3 bucket (R2)."""
    s3_client = get_r2_client()
    if not s3_client:
        return False, "R2 client not initialized."

    bucket_name = os.getenv("R2_BUCKET_NAME")
    if not bucket_name:
        logger.error("R2_BUCKET_NAME not set in environment variables.")
        return False, "R2 bucket name not configured."

    try:
        s3_client.download_file(bucket_name, object_name, download_path)
        logger.info(f"File '{object_name}' downloaded from R2 to '{download_path}'.")
        return True, None
    except ClientError as e:
        logger.error(f"Error downloading file from R2: {e}")
        return False, f"Error downloading file: {e}"
    except Exception as e:
        logger.error(f"An unexpected error occurred during R2 download: {e}")
        return False, f"An unexpected error occurred: {e}"

def delete_file_from_r2(object_name):
    """Deletes a file from an S3 bucket (R2)."""
    s3_client = get_r2_client()
    if not s3_client:
        return False, "R2 client not initialized."

    bucket_name = os.getenv("R2_BUCKET_NAME")
    if not bucket_name:
        logger.error("R2_BUCKET_NAME not set in environment variables.")
        return False, "R2 bucket name not configured."

    try:
        s3_client.delete_object(Bucket=bucket_name, Key=object_name)
        logger.info(f"File '{object_name}' deleted from R2.")
        return True, None
    except ClientError as e:
        logger.error(f"Error deleting file from R2: {e}")
        return False, f"Error deleting file: {e}"
    except Exception as e:
        logger.error(f"An unexpected error occurred during R2 deletion: {e}")
        return False, f"An unexpected error occurred: {e}"

def list_files_in_r2_bucket():
    """Lists all objects in the R2 bucket."""
    s3_client = get_r2_client()
    if not s3_client:
        return None, "R2 client not initialized."

    bucket_name = os.getenv("R2_BUCKET_NAME")
    if not bucket_name:
        logger.error("R2_BUCKET_NAME not set in environment variables.")
        return None, "R2 bucket name not configured."

    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        objects = [obj['Key'] for obj in response.get('Contents', [])]
        logger.info(f"Listed {len(objects)} objects in R2 bucket '{bucket_name}'.")
        return objects, None
    except ClientError as e:
        logger.error(f"Error listing files in R2 bucket: {e}")
        return None, f"Error listing files: {e}"
    except Exception as e:
        logger.error(f"An unexpected error occurred during R2 listing: {e}")
        return None, f"An unexpected error occurred: {e}"

def schedule_file_deletion(job_queue, object_name, user_id, file_type):
    """Schedules a job to delete a file from R2 after 1 week."""
    deletion_time = datetime.now() + timedelta(weeks=1)
    job_queue.run_once(
        delete_r2_file_job,
        when=deletion_time,
        data={'object_name': object_name, 'user_id': user_id, 'file_type': file_type}
    )
    logger.info(f"Scheduled deletion of '{object_name}' for {deletion_time}.")

async def delete_r2_file_job(context):
    """Job function to delete a file from R2 and notify the user."""
    job_data = context.job.data
    object_name = job_data['object_name']
    user_id = job_data['user_id']
    file_type = job_data['file_type']
    
    success, error_message = delete_file_from_r2(object_name)
    
    if success:
        message = (
            f"Your uploaded {file_type} file '{object_name}' has been removed from storage "
            "after 1 week as per our policy. Please ensure you have saved your converted files."
        )
        logger.info(f"Successfully deleted '{object_name}' and notified user {user_id}.")
    else:
        message = (
            f"Failed to remove your uploaded {file_type} file '{object_name}' from storage. "
            f"Error: {error_message}"
        )
        logger.error(f"Failed to delete '{object_name}' for user {user_id}: {error_message}")
    
    # Send notification to user (assuming context.bot and user_id are available)
    # This part needs to be integrated with your Telegram bot's application instance
    # For now, it's a placeholder. You'll need to pass the bot instance or find another way to send messages.
    # await context.bot.send_message(chat_id=user_id, text=message)
    logger.info(f"Notification for user {user_id}: {message}")
