import os
import logging
import tempfile
import subprocess
import shutil
from pathlib import Path
from telegram import Update
from telegram.ext import CallbackContext, ConversationHandler
import fitz # PyMuPDF
import uuid # For generating unique filenames

# Import utility functions and constants
from utility_handlers import send_or_edit_message
# from file_handlers import _get_file_info_from_update # No longer needed, file info comes from context
from pdf_converter import convert_pdf_to_images, create_zip_archive # Assuming these exist and work
from r2_utils import upload_file_to_r2, download_file_from_r2
from database import increment_daily_conversion_count
from datetime import datetime
from notification_utils import send_notification_to_channel
from user_content_logger import log_outgoing_message # Import for logging outgoing messages

logger = logging.getLogger(__name__)

async def handle_docx_to_pdf(update: Update, context: CallbackContext):
    """Convert DOCX to PDF using LibreOffice.
    This function is now expected to process a single DOCX, either newly uploaded
    or pre-uploaded via context.user_data['uploaded_file_info'].
    """
    logger.info("handle_docx_to_pdf called.")
    user_id = update.effective_user.id
    temp_dir = None
    
    uploaded_file_info = context.user_data.pop('uploaded_file_info', None)
    if not uploaded_file_info or 'r2_object_key' not in uploaded_file_info:
        await send_or_edit_message(update, "Error: File information or R2 key missing. Please try uploading your file again.")
        return ConversationHandler.END

    file_id = uploaded_file_info['file_id']
    file_name = uploaded_file_info['file_name']
    mime_type = uploaded_file_info['mime_type']
    r2_object_key = uploaded_file_info['r2_object_key']

    if mime_type != 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        await send_or_edit_message(update, "Oops! That doesn't look like a Word document. Please send a valid DOCX file for conversion. 📝")
        return ConversationHandler.END

    try:
        temp_dir = tempfile.mkdtemp()
        
        input_path = os.path.join(temp_dir, file_name)
        success, error_message = await download_file_from_r2(r2_object_key, input_path)
        if not success:
            logger.error(f"Error downloading DOCX from R2 for PDF conversion: {error_message}")
            await send_or_edit_message(update, f"Uh oh! 😟 I couldn't access your DOCX from storage: {error_message}. Please try again.")
            return ConversationHandler.END
        
        # Create a sanitized filename for LibreOffice if original has problematic characters
        sanitized_file_name = f"{uuid.uuid4().hex}_{Path(file_name).stem}{Path(file_name).suffix}"
        sanitized_input_path = os.path.join(temp_dir, sanitized_file_name)
        os.rename(input_path, sanitized_input_path) # Rename the downloaded file
        input_path = sanitized_input_path # Use the sanitized path for conversion
        
        # Convert DOCX to PDF using LibreOffice
        output_pdf_name = f"{Path(sanitized_file_name).stem}.pdf"
        output_path = os.path.join(temp_dir, output_pdf_name)
        
        cmd = ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", temp_dir, input_path]
        
        # Set HOME environment variable for LibreOffice to prevent potential issues
        env = os.environ.copy()
        env['HOME'] = temp_dir # LibreOffice might write config files here

        process = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60, env=env)
        
        if process.returncode != 0:
            logger.error(f"LibreOffice DOCX to PDF conversion failed with error code {process.returncode}.")
            logger.error(f"LibreOffice stdout: {process.stdout}")
            logger.error(f"LibreOffice stderr: {process.stderr}")
            raise Exception(f"LibreOffice conversion failed: {process.stderr or process.stdout}")

        # Check if the output PDF was created
        if not os.path.exists(output_path):
            raise FileNotFoundError(f"LibreOffice failed to create PDF from DOCX. Expected: {output_path}")

        # Upload to R2
        output_r2_key = f"{user_id}/converted/{datetime.now().strftime('%Y%m%d%H%M%S')}_{output_pdf_name}"
        public_url, error = upload_file_to_r2(output_path, output_r2_key)
        
        if error:
            logger.error(f"Error uploading converted PDF to R2: {error}")
            await send_or_edit_message(update, f"Failed to upload converted file to storage: {error}. Please try again.")
            return ConversationHandler.END
        
        user = update.effective_user
        notification_message = (
            f"✅ DOCX to PDF Conversion Completed ✅\n\n"
            f"👤 User: {user.full_name} (ID: {user.id})\n"
            f"📁 Original File: {file_name}\n"
            f"🆔 Original File ID: {file_id}\n"
            f"☁️ Original R2 Key: {r2_object_key}\n"
            f"🔗 Converted File URL: `{public_url}`" # Escape URL for Markdown
        )
        await send_notification_to_channel(notification_message, parse_mode='Markdown')
        await send_or_edit_message(update, f"🎉 Success! Your DOCX has been converted to PDF and is available here: {public_url}")
        
        # Log outgoing message to R2
        await log_outgoing_message(
            user_id=user_id,
            message_id=update.effective_message.message_id,
            message_type="pdf",
            text_content="Converted DOCX to PDF",
            r2_url=public_url,
            original_filename=output_pdf_name,
            file_size=os.path.getsize(output_path)
        )
        await increment_daily_conversion_count(user_id)
        return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"DOCX to PDF conversion failed: {e}")
        await send_or_edit_message(update, f"Failed to convert DOCX to PDF: {e}. Please try again.")
        return ConversationHandler.END
    finally:
        # Clean up temp files
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.error(f"Error cleaning up temp directory {temp_dir}: {e}")

async def handle_pdf_to_docx(update: Update, context: CallbackContext):
    """Convert PDF to DOCX using LibreOffice.
    This function is now expected to process a single PDF, either newly uploaded
    or pre-uploaded via context.user_data['uploaded_file_info'].
    """
    logger.info("handle_pdf_to_docx called.")
    user_id = update.effective_user.id
    temp_dir = None
    
    uploaded_file_info = context.user_data.pop('uploaded_file_info', None)
    if not uploaded_file_info or 'r2_object_key' not in uploaded_file_info:
        await send_or_edit_message(update, "Error: File information or R2 key missing. Please try uploading your file again.")
        return ConversationHandler.END

    file_id = uploaded_file_info['file_id']
    file_name = uploaded_file_info['file_name']
    mime_type = uploaded_file_info['mime_type']
    r2_object_key = uploaded_file_info['r2_object_key']

    if mime_type != 'application/pdf':
        await send_or_edit_message(update, "Oops! That doesn't look like a PDF. Please send a valid PDF file for conversion. 📄")
        return ConversationHandler.END

    try:
        temp_dir = tempfile.mkdtemp()
        
        input_path = os.path.join(temp_dir, file_name)
        success, error_message = await download_file_from_r2(r2_object_key, input_path)
        if not success:
            logger.error(f"Error downloading PDF from R2 for DOCX conversion: {error_message}")
            await send_or_edit_message(update, f"Uh oh! 😟 I couldn't access your PDF from storage: {error_message}. Please try again.")
            return ConversationHandler.END
        
        # Create a sanitized filename for LibreOffice if original has problematic characters
        sanitized_file_name = f"{uuid.uuid4().hex}_{Path(file_name).stem}{Path(file_name).suffix}"
        sanitized_input_path = os.path.join(temp_dir, sanitized_file_name)
        os.rename(input_path, sanitized_input_path) # Rename the downloaded file
        input_path = sanitized_input_path # Use the sanitized path for conversion
        
        # Convert PDF to DOCX
        output_docx_name = f"{Path(sanitized_file_name).stem}.docx"
        output_path = os.path.join(temp_dir, output_docx_name)
        
        cmd = ["libreoffice", "--headless", "--convert-to", "docx", "--outdir", temp_dir, input_path]
        
        process = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if process.returncode != 0:
            logger.error(f"LibreOffice PDF to DOCX conversion failed with error code {process.returncode}.")
            logger.error(f"LibreOffice stdout: {process.stdout}")
            logger.error(f"LibreOffice stderr: {process.stderr}")
            raise Exception(f"LibreOffice conversion failed: {process.stderr or process.stdout}")

        # Check if the output DOCX was created
        if not os.path.exists(output_path):
            raise FileNotFoundError(f"LibreOffice failed to create DOCX from PDF. Expected: {output_path}")
        
        # Upload to R2
        output_r2_key = f"{user_id}/converted/{datetime.now().strftime('%Y%m%d%H%M%S')}_{output_docx_name}"
        public_url, error = upload_file_to_r2(output_path, output_r2_key)
        
        if error:
            logger.error(f"Error uploading converted DOCX to R2: {error}")
            await send_or_edit_message(update, f"Failed to upload converted file to storage: {error}. Please try again.")
            return ConversationHandler.END
        
        user = update.effective_user
        notification_message = (
            f"✅ PDF to DOCX Conversion Completed ✅\n\n"
            f"👤 User: {user.full_name} (ID: {user.id})\n"
            f"📁 Original File: {file_name}\n"
            f"🆔 Original File ID: {file_id}\n"
            f"☁️ Original R2 Key: {r2_object_key}\n"
            f"🔗 Converted File URL: `{public_url}`" # Escape URL for Markdown
        )
        await send_notification_to_channel(notification_message, parse_mode='Markdown')
        await send_or_edit_message(update, f"🎉 Success! Your PDF has been converted to DOCX and is available here: {public_url}")
        
        # Log outgoing message to R2
        await log_outgoing_message(
            user_id=user_id,
            message_id=update.effective_message.message_id,
            message_type="docx",
            text_content="Converted PDF to DOCX",
            r2_url=public_url,
            original_filename=output_docx_name,
            file_size=os.path.getsize(output_path)
        )
        await increment_daily_conversion_count(user_id)
        return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"PDF to DOCX conversion failed: {e}")
        await send_or_edit_message(update, f"Failed to convert PDF to DOCX: {e}. Please try again.")
        return ConversationHandler.END
    finally:
        # Clean up temp files
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.error(f"Error cleaning up temp directory {temp_dir}: {e}")

async def handle_docx_to_image(update: Update, context: CallbackContext) -> int:
    """Convert DOCX to images (PNG, JPG, WEBP, TIFF).
    This function is now expected to process a single DOCX, either newly uploaded
    or pre-uploaded via context.user_data['uploaded_file_info'].
    """
    logger.info("handle_docx_to_image called.")
    user_id = update.effective_user.id
    temp_dir = None
    
    uploaded_file_info = context.user_data.pop('uploaded_file_info', None)
    if not uploaded_file_info or 'r2_object_key' not in uploaded_file_info:
        await send_or_edit_message(update, "Error: File information or R2 key missing. Please try uploading your file again.")
        return ConversationHandler.END

    file_id = uploaded_file_info['file_id']
    file_name = uploaded_file_info['file_name']
    mime_type = uploaded_file_info['mime_type']
    r2_object_key = uploaded_file_info['r2_object_key']

    if mime_type != 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        await send_or_edit_message(update, "Oops! That doesn't look like a Word document. Please send a valid DOCX file for conversion. 📝")
        return ConversationHandler.END

    try:
        temp_dir = tempfile.mkdtemp()
        
        input_docx_path = os.path.join(temp_dir, file_name)
        success, error_message = await download_file_from_r2(r2_object_key, input_docx_path)
        if not success:
            logger.error(f"Error downloading DOCX from R2 for image conversion: {error_message}")
            await send_or_edit_message(update, f"Uh oh! 😟 I couldn't access your DOCX from storage: {error_message}. Please try again.")
            return ConversationHandler.END

        # Create a sanitized filename for LibreOffice if original has problematic characters
        sanitized_file_name = f"{uuid.uuid4().hex}_{Path(file_name).stem}{Path(file_name).suffix}"
        sanitized_input_docx_path = os.path.join(temp_dir, sanitized_file_name)
        os.rename(input_docx_path, sanitized_input_docx_path) # Rename the downloaded file
        input_docx_path = sanitized_input_docx_path # Use the sanitized path for conversion

        output_image_format = context.user_data.get('output_image_format', 'png')
        
        # Step 1: Convert DOCX to PDF
        pdf_output_name = f"{Path(sanitized_file_name).stem}.pdf"
        pdf_output_path = os.path.join(temp_dir, pdf_output_name)
        
        cmd = ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", temp_dir, input_docx_path]
        # Set HOME environment variable for LibreOffice to prevent potential issues
        env = os.environ.copy()
        env['HOME'] = temp_dir # LibreOffice might write config files here

        process = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60, env=env)

        if process.returncode != 0:
            logger.error(f"LibreOffice DOCX to PDF (for image conversion) failed with error code {process.returncode}.")
            logger.error(f"LibreOffice stdout: {process.stdout}")
            logger.error(f"LibreOffice stderr: {process.stderr}")
            raise Exception(f"LibreOffice conversion failed: {process.stderr or process.stdout}")

        if not os.path.exists(pdf_output_path):
            raise FileNotFoundError(f"LibreOffice failed to create PDF from DOCX. Expected: {pdf_output_path}")

        # Step 2: Convert PDF to images
        image_paths = convert_pdf_to_images(pdf_output_path, 'all', output_image_format)

        if not image_paths:
            await send_or_edit_message(update, "Uh oh! 😟 I couldn't convert your DOCX to images. Please try again.")
            return ConversationHandler.END

        output_r2_urls = []
        if len(image_paths) > 1:
            # If multiple images, create a zip, upload the zip, and send its URL
            zip_path = create_zip_archive(image_paths, file_name, temp_dir)
            
            if zip_path and os.path.exists(zip_path):
                output_file_name = Path(zip_path).name
                output_r2_key = f"{user_id}/converted/{datetime.now().strftime('%Y%m%d%H%M%S')}_{output_file_name}"
                public_url, error = upload_file_to_r2(zip_path, output_r2_key)
                if error:
                    logger.error(f"Error uploading converted ZIP to R2: {error}")
                    await send_or_edit_message(update, f"Failed to upload converted ZIP to storage: {error}. Please try again.")
                    return ConversationHandler.END
                output_r2_urls.append(public_url)
                await send_or_edit_message(update, f"Here are your converted {output_image_format.upper()} images in a ZIP archive: {public_url}")
            else:
                await send_or_edit_message(update, "😔 Oops! Failed to create the ZIP archive. Sending individual images instead.")
                for i, img_path in enumerate(image_paths):
                    output_file_name = f"{Path(file_name).stem}_page_{i+1}.{output_image_format}"
                    output_r2_key = f"{user_id}/converted/{datetime.now().strftime('%Y%m%d%H%M%S')}_{output_file_name}"
                    public_url, error = upload_file_to_r2(img_path, output_r2_key)
                    if error:
                        logger.error(f"Error uploading converted image to R2: {error}")
                        await send_or_edit_message(update, f"Failed to upload converted image to storage: {error}. Please try again.")
                        return ConversationHandler.END
                    output_r2_urls.append(public_url)
                    await send_or_edit_message(update, f"Converted image {i+1}: {public_url}")
        else:
            output_file_name = f"{Path(file_name).stem}.{output_image_format}"
            output_r2_key = f"{user_id}/converted/{datetime.now().strftime('%Y%m%d%H%M%S')}_{output_file_name}"
            public_url, error = upload_file_to_r2(image_paths[0], output_r2_key)
            if error:
                logger.error(f"Error uploading converted image to R2: {error}")
                await send_or_edit_message(update, f"Failed to upload converted image to storage: {error}. Please try again.")
                return ConversationHandler.END
            output_r2_urls.append(public_url)
            await send_or_edit_message(update, f"Here's your converted {output_image_format.upper()} image: {public_url}")

        user = update.effective_user
        notification_message = (
            f"✅ DOCX to {output_image_format.upper()} Conversion Completed ✅\n\n"
            f"👤 User: {user.full_name} (ID: {user.id})\n"
            f"📁 Original File: {file_name}\n"
            f"🆔 Original File ID: {file_id}\n"
            f"☁️ Original R2 Key: {r2_object_key}\n"
            f"🔗 Converted File URLs: `{', '.join(output_r2_urls)}`" # Escape URL for Markdown
        )
        await send_notification_to_channel(notification_message, parse_mode='Markdown')
        await send_or_edit_message(update, f"🎉 Success! Your DOCX has been converted to {output_image_format.upper()} images and links sent!")
        
        # Log outgoing messages to R2
        for url in output_r2_urls:
            # Extract filename from URL for logging
            filename_from_url = url.split('/')[-1]
            await log_outgoing_message(
                user_id=user_id,
                message_id=update.effective_message.message_id,
                message_type=output_image_format.lower(),
                text_content=f"Converted DOCX to {output_image_format} image(s)",
                r2_url=url,
                original_filename=filename_from_url,
                file_size=None # File size is not readily available here without re-downloading
            )
        await increment_daily_conversion_count(user_id)
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"DOCX to Image conversion failed: {e}")
        await send_or_edit_message(update, f"An error occurred during DOCX to Image conversion: {e} 💔 Please try again.")
        return ConversationHandler.END
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.error(f"Error cleaning up temp directory {temp_dir}: {e}")

async def handle_docx_to_pptx(update: Update, context: CallbackContext) -> int:
    """Convert DOCX to PPTX using LibreOffice."""
    logger.info("handle_docx_to_pptx called.")
    user_id = update.effective_user.id
    temp_dir = None
    
    uploaded_file_info = context.user_data.pop('uploaded_file_info', None)
    if not uploaded_file_info or 'r2_object_key' not in uploaded_file_info:
        await send_or_edit_message(update, "Error: File information or R2 key missing. Please try uploading your file again.")
        return ConversationHandler.END

    file_id = uploaded_file_info['file_id']
    file_name = uploaded_file_info['file_name']
    mime_type = uploaded_file_info['mime_type']
    r2_object_key = uploaded_file_info['r2_object_key']

    if mime_type != 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        await send_or_edit_message(update, "Oops! That doesn't look like a Word document. Please send a valid DOCX file for conversion. 📝")
        return ConversationHandler.END

    try:
        temp_dir = tempfile.mkdtemp()
        
        input_path = os.path.join(temp_dir, file_name)
        success, error_message = await download_file_from_r2(r2_object_key, input_path)
        if not success:
            logger.error(f"Error downloading DOCX from R2 for PPTX conversion: {error_message}")
            await send_or_edit_message(update, f"Uh oh! 😟 I couldn't access your DOCX from storage: {error_message}. Please try again.")
            return ConversationHandler.END
        
        # Create a sanitized filename for LibreOffice if original has problematic characters
        sanitized_file_name = f"{uuid.uuid4().hex}_{Path(file_name).stem}{Path(file_name).suffix}"
        sanitized_input_path = os.path.join(temp_dir, sanitized_file_name)
        os.rename(input_path, sanitized_input_path) # Rename the downloaded file
        input_path = sanitized_input_path # Use the sanitized path for conversion
        
        # Convert DOCX to PPTX using LibreOffice
        output_pptx_name = f"{Path(sanitized_file_name).stem}.pptx"
        output_path = os.path.join(temp_dir, output_pptx_name)
        
        cmd = ["libreoffice", "--headless", "--convert-to", "pptx", "--outdir", temp_dir, input_path]
        
        # Set HOME environment variable for LibreOffice to prevent potential issues
        env = os.environ.copy()
        env['HOME'] = temp_dir # LibreOffice might write config files here

        process = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60, env=env)
        
        if process.returncode != 0:
            logger.error(f"LibreOffice DOCX to PPTX conversion failed with error code {process.returncode}.")
            logger.error(f"LibreOffice stdout: {process.stdout}")
            logger.error(f"LibreOffice stderr: {process.stderr}")
            raise Exception(f"LibreOffice conversion failed: {process.stderr or process.stdout}")

        # Check if the output PPTX was created
        if not os.path.exists(output_path):
            raise FileNotFoundError(f"LibreOffice failed to create PPTX from DOCX. Expected: {output_path}")

        # Upload to R2
        output_r2_key = f"{user_id}/converted/{datetime.now().strftime('%Y%m%d%H%M%S')}_{output_pptx_name}"
        public_url, error = upload_file_to_r2(output_path, output_r2_key)
        
        if error:
            logger.error(f"Error uploading converted PPTX to R2: {error}")
            await send_or_edit_message(update, f"Failed to upload converted file to storage: {error}. Please try again.")
            return ConversationHandler.END
        
        user = update.effective_user
        notification_message = (
            f"✅ DOCX to PPTX Conversion Completed ✅\n\n"
            f"👤 User: {user.full_name} (ID: {user.id})\n"
            f"📁 Original File: {file_name}\n"
            f"🆔 Original File ID: {file_id}\n"
            f"☁️ Original R2 Key: {r2_object_key}\n"
            f"🔗 Converted File URL: `{public_url}`" # Escape URL for Markdown
        )
        await send_notification_to_channel(notification_message, parse_mode='Markdown')
        await send_or_edit_message(update, f"🎉 Success! Your DOCX has been converted to PPTX and is available here: {public_url}")
        
        # Log outgoing message to R2
        await log_outgoing_message(
            user_id=user_id,
            message_id=update.effective_message.message_id,
            message_type="pptx",
            text_content="Converted DOCX to PPTX",
            r2_url=public_url,
            original_filename=output_pptx_name,
            file_size=os.path.getsize(output_path)
        )
        await increment_daily_conversion_count(user_id)
        return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"DOCX to PPTX conversion failed: {e}")
        await send_or_edit_message(update, f"Failed to convert DOCX to PPTX: {e}. Please try again.")
        return ConversationHandler.END
    finally:
        # Clean up temp files
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.error(f"Error cleaning up temp directory {temp_dir}: {e}")
