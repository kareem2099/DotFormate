import os
import logging
from pathlib import Path
import tempfile
from PIL import Image
from admin_handlers import send_admin_notification # Import for admin notifications

logger = logging.getLogger(__name__)

async def resize_image(input_path: str, output_dir: str, new_width: int, new_height: int, output_format: str = 'PNG', context=None, user_id=None, file_name=None, file_id=None) -> str:
    """Resizes an image to the specified dimensions."""
    try:
        img = Image.open(input_path)
        resized_img = img.resize((new_width, new_height))
        output_path = os.path.join(output_dir, f"{Path(input_path).stem}_resized.{output_format.lower()}")
        resized_img.save(output_path, format=output_format)
        logger.info(f"Image resized and saved to {output_path}")

        if context and user_id and file_name and file_id:
            notification_message = (
                f"✅ Image Resize Completed ✅\n\n"
                f"👤 User ID: {user_id}\n"
                f"📁 Original File: {file_name}\n"
                f"🆔 Original File ID: {file_id}\n"
                f"📏 New Dimensions: {new_width}x{new_height}"
            )
            await send_admin_notification(context, notification_message)

        return output_path
    except Exception as e:
        logger.error(f"Error resizing image {input_path}: {e}")
        raise

async def rotate_image(input_path: str, output_dir: str, angle: int, output_format: str = 'PNG', context=None, user_id=None, file_name=None, file_id=None) -> str:
    """Rotates an image by the specified angle."""
    try:
        img = Image.open(input_path)
        rotated_img = img.rotate(angle, expand=True)
        output_path = os.path.join(output_dir, f"{Path(input_path).stem}_rotated.{output_format.lower()}")
        rotated_img.save(output_path, format=output_format)
        logger.info(f"Image rotated and saved to {output_path}")

        if context and user_id and file_name and file_id:
            notification_message = (
                f"✅ Image Rotation Completed ✅\n\n"
                f"👤 User ID: {user_id}\n"
                f"📁 Original File: {file_name}\n"
                f"🆔 Original File ID: {file_id}\n"
                f"🔄 Rotation Angle: {angle}°"
            )
            await send_admin_notification(context, notification_message)

        return output_path
    except Exception as e:
        logger.error(f"Error rotating image {input_path}: {e}")
        raise

async def convert_image_format(input_path: str, output_dir: str, output_format: str, context=None, user_id=None, file_name=None, file_id=None) -> str:
    """Converts an image to a different format."""
    try:
        img = Image.open(input_path)
        output_path = os.path.join(output_dir, f"{Path(input_path).stem}.{output_format.lower()}")
        img.save(output_path, format=output_format)
        logger.info(f"Image converted to {output_format} and saved to {output_path}")

        if context and user_id and file_name and file_id:
            notification_message = (
                f"✅ Image Format Conversion Completed ✅\n\n"
                f"👤 User ID: {user_id}\n"
                f"📁 Original File: {file_name}\n"
                f"🆔 Original File ID: {file_id}\n"
                f"➡️ Converted Format: {output_format}"
            )
            await send_admin_notification(context, notification_message)

        return output_path
    except Exception as e:
        logger.error(f"Error converting image format for {input_path}: {e}")
        raise

# You can add more image processing functions here, e.g., crop_image, apply_filter, etc.
