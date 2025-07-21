import os
import logging
from datetime import datetime
from telegram import File
from telegram.ext import CallbackContext
from r2_utils import upload_file_to_r2
from database import save_user_message_log

logger = logging.getLogger(__name__)

async def log_incoming_message(
    user_id: int,
    message_id: int,
    message_type: str,
    text_content: str = None,
    file_id: str = None,
    file_size: int = None,
    file_name: str = None,
    context: CallbackContext = None
):
    """
    Logs incoming user messages and optionally stores associated files in R2.
    """
    r2_url = None
    if file_id and context:
        try:
            # Get the file from Telegram
            telegram_file: File = await context.bot.get_file(file_id)
            
            # Create a temporary path to save the file before uploading to R2
            temp_file_path = f"/tmp/{file_id}_{file_name or 'temp_file'}"
            await telegram_file.download_to_drive(temp_file_path)

            # Define R2 object key
            r2_object_key = f"user_content/{user_id}/{datetime.utcnow().strftime('%Y-%m-%d')}/{message_id}_{file_name or file_id}"
            
            # Upload to R2
            public_url, error_message = upload_file_to_r2(temp_file_path, r2_object_key)
            if public_url:
                r2_url = public_url
                logger.info(f"Incoming file {file_name} for user {user_id} uploaded to R2: {r2_url}")
            else:
                logger.error(f"Failed to upload incoming file {file_name} to R2: {error_message}")
            
            # Clean up temporary file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

        except Exception as e:
            logger.error(f"Error processing incoming file for user {user_id}, file_id {file_id}: {e}")

    await save_user_message_log(
        user_id=user_id,
        message_id=message_id,
        direction="incoming",
        message_type=message_type,
        timestamp=datetime.utcnow(),
        text_content=text_content,
        r2_url=r2_url,
        original_filename=file_name,
        file_size=file_size
    )

async def log_outgoing_message(
    user_id: int,
    message_id: int,
    message_type: str,
    text_content: str = None,
    file_path: str = None, # Local path to the file being sent by the bot
    original_filename: str = None,
    file_size: int = None
):
    """
    Logs outgoing bot messages and optionally stores associated files in R2.
    """
    r2_url = None
    if file_path:
        try:
            # Define R2 object key
            r2_object_key = f"bot_outgoing/{user_id}/{datetime.utcnow().strftime('%Y-%m-%d')}/{message_id}_{original_filename or os.path.basename(file_path)}"
            
            # Upload to R2
            public_url, error_message = upload_file_to_r2(file_path, r2_object_key)
            if public_url:
                r2_url = public_url
                logger.info(f"Outgoing file {original_filename} for user {user_id} uploaded to R2: {r2_url}")
            else:
                logger.error(f"Failed to upload outgoing file {original_filename} to R2: {error_message}")

        except Exception as e:
            logger.error(f"Error processing outgoing file for user {user_id}, file_path {file_path}: {e}")

    await save_user_message_log(
        user_id=user_id,
        message_id=message_id,
        direction="outgoing",
        message_type=message_type,
        timestamp=datetime.utcnow(),
        text_content=text_content,
        r2_url=r2_url,
        original_filename=original_filename,
        file_size=file_size
    )
