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
from file_handlers import _get_file_info_from_update # Helper for file info extraction
from pdf_converter import convert_pdf_to_images, create_zip_archive # Assuming these exist and work
from pdf2pptx import convert_pdf2pptx # Specific import for PDF to PPTX conversion
from admin_handlers import send_admin_notification # Import for admin notifications

logger = logging.getLogger(__name__)

async def handle_pptx_to_pdf(update: Update, context: CallbackContext):
    """Convert PPTX to PDF using LibreOffice.
    This function is now expected to process a single PPTX, either newly uploaded
    or pre-uploaded via context.user_data['uploaded_file_info'].
    """
    logger.info("handle_pptx_to_pdf called.")
    temp_dir = None
    
    file_id, file_name, mime_type = await _get_file_info_from_update(update, context)

    if not file_id or mime_type != 'application/vnd.openxmlformats-officedocument.presentationml.presentation':
        await send_or_edit_message(update, "Oops! That doesn't look like a PowerPoint document. Please send a valid PPTX file for conversion. 📊")
        return ConversationHandler.END

    try:
        temp_dir = tempfile.mkdtemp()
        
        input_path = os.path.join(temp_dir, file_name)
        file_object = await context.bot.get_file(file_id)
        await file_object.download_to_drive(input_path)
        
        # Create a sanitized filename for LibreOffice if original has problematic characters
        sanitized_file_name = f"{uuid.uuid4().hex}_{Path(file_name).stem}{Path(file_name).suffix}"
        sanitized_input_path = os.path.join(temp_dir, sanitized_file_name)
        os.rename(input_path, sanitized_input_path) # Rename the downloaded file
        input_path = sanitized_input_path # Use the sanitized path for conversion
        
        output_pdf_name = f"{Path(sanitized_file_name).stem}.pdf"
        output_path = os.path.join(temp_dir, output_pdf_name)
        
        cmd = ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", temp_dir, input_path]
        
        # Set HOME environment variable for LibreOffice to prevent potential issues
        env = os.environ.copy()
        env['HOME'] = temp_dir # LibreOffice might write config files here

        process = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60, env=env)
        
        if process.returncode != 0:
            logger.error(f"LibreOffice PPTX to PDF conversion failed with error code {process.returncode}.")
            logger.error(f"LibreOffice stdout: {process.stdout}")
            logger.error(f"LibreOffice stderr: {process.stderr}")
            raise Exception(f"LibreOffice conversion failed: {process.stderr or process.stdout}")
        
        if not os.path.exists(output_path):
            raise FileNotFoundError(f"LibreOffice failed to create PDF from PPTX. Expected: {output_path}")

        with open(output_path, 'rb') as pdf_file:
            await update.message.reply_document(
                document=pdf_file,
                caption="Here's your converted PDF file"
            )
        user = update.effective_user
        notification_message = (
            f"✅ PPTX to PDF Conversion Completed ✅\n\n"
            f"👤 User: {user.full_name} (ID: {user.id})\n"
            f"📁 File: {file_name}\n"
            f"🆔 File ID: {file_id}"
        )
        await send_admin_notification(context, notification_message)
        await send_or_edit_message(update, "🎉 Success! Your PPTX has been converted to PDF and sent!")
        return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"PPTX to PDF conversion failed: {e}")
        await send_or_edit_message(update, f"Failed to convert PPTX to PDF: {e}. Please try again.")
        return ConversationHandler.END
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.error(f"Error cleaning up temp directory {temp_dir}: {e}")

async def handle_pdf_to_pptx(update: Update, context: CallbackContext) -> int:
    """Handles PDF to PPTX conversion using pdf2pptx.
    This function is now expected to process a single PDF, either newly uploaded
    or pre-uploaded via context.user_data['uploaded_file_info'].
    """
    logger.info("handle_pdf_to_pptx called.")
    temp_dir = None
    
    file_id, file_name, mime_type = await _get_file_info_from_update(update, context)

    if not file_id or mime_type != 'application/pdf':
        await send_or_edit_message(update, "Oops! That doesn't look like a PDF. Please send a valid PDF file for conversion. 📄")
        return ConversationHandler.END

    try:
        temp_dir = tempfile.mkdtemp()
        
        downloaded_pdf_path = os.path.join(temp_dir, file_name)
        file_object = await context.bot.get_file(file_id)
        await file_object.download_to_drive(downloaded_pdf_path)

        # Create a sanitized filename for pdf2pptx if original has problematic characters
        sanitized_file_name = f"{uuid.uuid4().hex}_{Path(file_name).stem}{Path(file_name).suffix}"
        sanitized_input_path = os.path.join(temp_dir, sanitized_file_name)
        os.rename(downloaded_pdf_path, sanitized_input_path) # Rename the downloaded file
        downloaded_pdf_path = sanitized_input_path # Use the sanitized path for conversion

        output_pptx_path = os.path.join(temp_dir, Path(sanitized_file_name).stem + '.pptx')

        # Perform the conversion
        convert_pdf2pptx(downloaded_pdf_path, output_pptx_path, resolution=300, start_page=0, page_count=None)

        if not os.path.exists(output_pptx_path):
            raise FileNotFoundError(f"pdf2pptx failed to create PPTX: {output_pptx_path}")

        with open(output_pptx_path, 'rb') as pptx_file:
            await update.message.reply_document(
                document=pptx_file,
                caption="Here's your converted PPTX file!"
            )
        user = update.effective_user
        notification_message = (
            f"✅ PDF to PPTX Conversion Completed ✅\n\n"
            f"👤 User: {user.full_name} (ID: {user.id})\n"
            f"📁 File: {file_name}\n"
            f"🆔 File ID: {file_id}"
        )
        await send_admin_notification(context, notification_message)
        await send_or_edit_message(update, "🎉 Success! Your PDF has been converted to PPTX and sent!")
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"PDF to PPTX conversion failed: {e}")
        await send_or_edit_message(update, f"An error occurred during PDF to PPTX conversion: {e} 💔 Please try again.")
        return ConversationHandler.END
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.error(f"Error cleaning up temp directory {temp_dir}: {e}")

async def handle_pptx_to_image(update: Update, context: CallbackContext) -> int:
    """Convert PPTX to images (PNG, JPG, WEBP, TIFF).
    This function is now expected to process a single PPTX, either newly uploaded
    or pre-uploaded via context.user_data['uploaded_file_info'].
    """
    logger.info("handle_pptx_to_image called.")
    temp_dir = None
    
    file_id, file_name, mime_type = await _get_file_info_from_update(update, context)

    if not file_id or mime_type != 'application/vnd.openxmlformats-officedocument.presentationml.presentation':
        await send_or_edit_message(update, "Oops! That doesn't look like a PowerPoint document. Please send a valid PPTX file for conversion. 📊")
        return ConversationHandler.END

    try:
        temp_dir = tempfile.mkdtemp()
        
        input_pptx_path = os.path.join(temp_dir, file_name)
        file_object = await context.bot.get_file(file_id)
        await file_object.download_to_drive(input_pptx_path)

        # Create a sanitized filename for LibreOffice if original has problematic characters
        sanitized_file_name = f"{uuid.uuid4().hex}_{Path(file_name).stem}{Path(file_name).suffix}"
        sanitized_input_pptx_path = os.path.join(temp_dir, sanitized_file_name)
        os.rename(input_pptx_path, sanitized_input_pptx_path) # Rename the downloaded file
        input_pptx_path = sanitized_input_pptx_path # Use the sanitized path for conversion

        output_image_format = context.user_data.get('output_image_format', 'png')
        
        # Step 1: Convert PPTX to PDF
        pdf_output_name = f"{Path(sanitized_file_name).stem}.pdf"
        pdf_output_path = os.path.join(temp_dir, pdf_output_name)
        
        cmd = ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", temp_dir, input_pptx_path]
        env = os.environ.copy()
        env['HOME'] = temp_dir

        process = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60, env=env)

        if process.returncode != 0:
            logger.error(f"LibreOffice PPTX to PDF (for image conversion) failed with error code {process.returncode}.")
            logger.error(f"LibreOffice stdout: {process.stdout}")
            logger.error(f"LibreOffice stderr: {process.stderr}")
            raise Exception(f"LibreOffice conversion failed: {process.stderr or process.stdout}")

        if not os.path.exists(pdf_output_path):
            raise FileNotFoundError(f"LibreOffice failed to create PDF from PPTX. Expected: {pdf_output_path}")

        # Step 2: Convert PDF to images
        image_paths = convert_pdf_to_images(pdf_output_path, 'all', output_image_format)

        if not image_paths:
            await send_or_edit_message(update, "Uh oh! 😟 I couldn't convert your PPTX to images. Please try again.")
            return ConversationHandler.END

        # Send images (or zip if multiple)
        if len(image_paths) > 1:
            zip_path = create_zip_archive(image_paths, Path(file_name).stem)
            if zip_path:
                with open(zip_path, 'rb') as f:
                    await context.bot.send_document(chat_id=update.effective_chat.id, document=f, caption=f"Here are your converted {output_image_format.upper()} images in a ZIP archive!")
                os.remove(zip_path)
            else:
                await send_or_edit_message(update, "😔 Oops! Failed to create the ZIP archive. Sending individual images instead.")
                for i, img_path in enumerate(image_paths):
                    with open(img_path, 'rb') as f:
                        await context.bot.send_document(chat_id=update.effective_chat.id, document=f, caption=f"Converted image {i+1}")
                    os.remove(img_path)
        else:
            with open(image_paths[0], 'rb') as f:
                await context.bot.send_document(chat_id=update.effective_chat.id, document=f, caption=f"Here's your converted {output_image_format.upper()} image!")
            os.remove(image_paths[0])

        user = update.effective_user
        notification_message = (
            f"✅ PPTX to {output_image_format.upper()} Conversion Completed ✅\n\n"
            f"👤 User: {user.full_name} (ID: {user.id})\n"
            f"📁 File: {file_name}\n"
            f"🆔 File ID: {file_id}"
        )
        await send_admin_notification(context, notification_message)
        await send_or_edit_message(update, f"🎉 Success! Your PPTX has been converted to {output_image_format.upper()} images and sent!")
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"PPTX to Image conversion failed: {e}")
        await send_or_edit_message(update, f"An error occurred during PPTX to Image conversion: {e} 💔 Please try again.")
        return ConversationHandler.END
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.error(f"Error cleaning up temp directory {temp_dir}: {e}")

async def handle_pptx_to_docx(update: Update, context: CallbackContext) -> int:
    """Convert PPTX to DOCX using LibreOffice."""
    logger.info("handle_pptx_to_docx called.")
    temp_dir = None
    
    file_id, file_name, mime_type = await _get_file_info_from_update(update, context)

    if not file_id or mime_type != 'application/vnd.openxmlformats-officedocument.presentationml.presentation':
        await send_or_edit_message(update, "Oops! That doesn't look like a PowerPoint document. Please send a valid PPTX file for conversion. 📊")
        return ConversationHandler.END

    try:
        temp_dir = tempfile.mkdtemp()
        
        input_path = os.path.join(temp_dir, file_name)
        file_object = await context.bot.get_file(file_id)
        await file_object.download_to_drive(input_path)
        
        # Create a sanitized filename for LibreOffice if original has problematic characters
        sanitized_file_name = f"{uuid.uuid4().hex}_{Path(file_name).stem}{Path(file_name).suffix}"
        sanitized_input_path = os.path.join(temp_dir, sanitized_file_name)
        os.rename(input_path, sanitized_input_path) # Rename the downloaded file
        input_path = sanitized_input_path # Use the sanitized path for conversion
        
        # Convert PPTX to DOCX using LibreOffice
        output_docx_name = f"{Path(sanitized_file_name).stem}.docx"
        output_path = os.path.join(temp_dir, output_docx_name)
        
        cmd = ["libreoffice", "--headless", "--convert-to", "docx", "--outdir", temp_dir, input_path]
        
        # Set HOME environment variable for LibreOffice to prevent potential issues
        env = os.environ.copy()
        env['HOME'] = temp_dir # LibreOffice might write config files here

        process = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60, env=env)
        
        if process.returncode != 0:
            logger.error(f"LibreOffice PPTX to DOCX conversion failed with error code {process.returncode}.")
            logger.error(f"LibreOffice stdout: {process.stdout}")
            logger.error(f"LibreOffice stderr: {process.stderr}")
            raise Exception(f"LibreOffice conversion failed: {process.stderr or process.stdout}")

        # Check if the output DOCX was created
        if not os.path.exists(output_path):
            raise FileNotFoundError(f"LibreOffice failed to create DOCX from PPTX. Expected: {output_path}")

        # Send the converted DOCX
        with open(output_path, 'rb') as docx_file:
            await update.message.reply_document(
                document=docx_file,
                caption="Here's your converted DOCX file"
            )
        user = update.effective_user
        notification_message = (
            f"✅ PPTX to DOCX Conversion Completed ✅\n\n"
            f"👤 User: {user.full_name} (ID: {user.id})\n"
            f"📁 File: {file_name}\n"
            f"🆔 File ID: {file_id}"
        )
        await send_admin_notification(context, notification_message)
        await send_or_edit_message(update, "🎉 Success! Your PPTX has been converted to DOCX and sent!")
        return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"PPTX to DOCX conversion failed: {e}")
        await send_or_edit_message(update, f"Failed to convert PPTX to DOCX: {e}. Please try again.")
        return ConversationHandler.END
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.error(f"Error cleaning up temp directory {temp_dir}: {e}")
