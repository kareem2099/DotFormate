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
from admin_handlers import send_admin_notification # Import for admin notifications

logger = logging.getLogger(__name__)

async def handle_docx_to_pdf(update: Update, context: CallbackContext):
    """Convert DOCX to PDF using LibreOffice.
    This function is now expected to process a single DOCX, either newly uploaded
    or pre-uploaded via context.user_data['uploaded_file_info'].
    """
    logger.info("handle_docx_to_pdf called.")
    temp_dir = None
    
    file_id, file_name, mime_type = await _get_file_info_from_update(update, context)

    if not file_id or mime_type != 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        await send_or_edit_message(update, "Oops! That doesn't look like a Word document. Please send a valid DOCX file for conversion. 📝")
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
            # Sometimes LibreOffice outputs to a slightly different name or directory,
            # or fails silently. Check common variations or log more.
            # For now, re-raise if not found.
            raise FileNotFoundError(f"LibreOffice failed to create PDF from DOCX. Expected: {output_path}")

        # Send the converted PDF
        with open(output_path, 'rb') as pdf_file:
            await update.message.reply_document(
                document=pdf_file,
                caption="Here's your converted PDF file"
            )
        user = update.effective_user
        notification_message = (
            f"✅ DOCX to PDF Conversion Completed ✅\n\n"
            f"👤 User: {user.full_name} (ID: {user.id})\n"
            f"📁 File: {file_name}\n"
            f"🆔 File ID: {file_id}"
        )
        await send_admin_notification(context, notification_message)
        await send_or_edit_message(update, "🎉 Success! Your DOCX has been converted to PDF and sent!")
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
    temp_dir = None
    
    file_id, file_name, mime_type = await _get_file_info_from_update(update, context)

    if not file_id or mime_type != 'application/pdf':
        await send_or_edit_message(update, "Oops! That doesn't look like a PDF. Please send a valid PDF file for conversion. 📄")
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
        
        # Send the converted DOCX
        with open(output_path, 'rb') as docx_file:
            await update.message.reply_document(
                document=docx_file,
                caption="Here's your converted DOCX file"
            )
        user = update.effective_user
        notification_message = (
            f"✅ PDF to DOCX Conversion Completed ✅\n\n"
            f"👤 User: {user.full_name} (ID: {user.id})\n"
            f"📁 File: {file_name}\n"
            f"🆔 File ID: {file_id}"
        )
        await send_admin_notification(context, notification_message)
        await send_or_edit_message(update, "🎉 Success! Your PDF has been converted to DOCX and sent!")
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
    temp_dir = None
    
    file_id, file_name, mime_type = await _get_file_info_from_update(update, context)

    if not file_id or mime_type != 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        await send_or_edit_message(update, "Oops! That doesn't look like a Word document. Please send a valid DOCX file for conversion. 📝")
        return ConversationHandler.END

    try:
        temp_dir = tempfile.mkdtemp()
        
        input_docx_path = os.path.join(temp_dir, file_name)
        file_object = await context.bot.get_file(file_id)
        await file_object.download_to_drive(input_docx_path)

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

        # Send images (or zip if multiple)
        if len(image_paths) > 1:
            zip_path = create_zip_archive(image_paths, Path(file_name).stem) # Use original name for zip
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
            f"✅ DOCX to {output_image_format.upper()} Conversion Completed ✅\n\n"
            f"👤 User: {user.full_name} (ID: {user.id})\n"
            f"📁 File: {file_name}\n"
            f"🆔 File ID: {file_id}"
        )
        await send_admin_notification(context, notification_message)
        await send_or_edit_message(update, f"🎉 Success! Your DOCX has been converted to {output_image_format.upper()} images and sent!")
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
    temp_dir = None
    
    file_id, file_name, mime_type = await _get_file_info_from_update(update, context)

    if not file_id or mime_type != 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        await send_or_edit_message(update, "Oops! That doesn't look like a Word document. Please send a valid DOCX file for conversion. 📝")
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

        # Send the converted PPTX
        with open(output_path, 'rb') as pptx_file:
            await update.message.reply_document(
                document=pptx_file,
                caption="Here's your converted PPTX file"
            )
        user = update.effective_user
        notification_message = (
            f"✅ DOCX to PPTX Conversion Completed ✅\n\n"
            f"👤 User: {user.full_name} (ID: {user.id})\n"
            f"📁 File: {file_name}\n"
            f"🆔 File ID: {file_id}"
        )
        await send_admin_notification(context, notification_message)
        await send_or_edit_message(update, "🎉 Success! Your DOCX has been converted to PPTX and sent!")
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
