import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler
import fitz # PyMuPDF
from pdf_converter import (convert_pdf_to_images, create_zip_archive, 
                         convert_images_to_pdf, convert_image_format)
import os
import logging
import tempfile # Import tempfile for standardized temp file management
import shutil # Import shutil for directory removal
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler
import fitz # PyMuPDF
from pdf_converter import (convert_pdf_to_images, create_zip_archive, 
                         convert_images_to_pdf, convert_image_format as convert_image_format_pdf_converter) # Renamed to avoid conflict
from database import save_user_info
from utility_handlers import cancel, send_or_edit_message, _get_file_info_from_update
from database import get_user_premium_status, get_daily_conversion_count, increment_daily_conversion_count
from constants import (
    MAX_FREE_IMAGE_SIZE_MB, MAX_FREE_PDF_SIZE_MB, MAX_FREE_WORD_SIZE_MB, MAX_FREE_PPT_SIZE_MB,
    MAX_FREE_DAILY_CONVERSIONS,
    MAX_PREMIUM_IMAGE_SIZE_MB, MAX_PREMIUM_PDF_SIZE_MB, MAX_PREMIUM_WORD_SIZE_MB, MAX_PREMIUM_PPT_SIZE_MB
)
from r2_utils import upload_file_to_r2, schedule_file_deletion, download_file_from_r2
from datetime import datetime
from database import save_r2_file_metadata # Import the new function
from notification_utils import send_notification_to_channel # Import the new notification utility
from user_content_logger import log_outgoing_message # Import the new user content logger
from constants import (
    SELECT_CONVERSION_TYPE, SELECT_PAGES, SELECT_OUTPUT_FORMAT, 
    SELECT_IMAGE_FORMAT, COMPRESSION_PROCESSING,
    RESIZE_INPUT, ROTATE_INPUT # New states for image processing
)
from image_processor import resize_image, rotate_image, convert_image_format # Import new image processing functions
from docx_converter import handle_docx_to_pdf, handle_docx_to_image, handle_docx_to_pptx # For handle_document_type
from pptx_converter import handle_pptx_to_pdf, handle_pptx_to_image, handle_pptx_to_docx # For handle_document_type

logger = logging.getLogger(__name__)

from utility_handlers import cancel, send_or_edit_message, _get_file_info_from_update # Import centralized cancel, send_or_edit_message, and _get_file_info_from_update

async def handle_pdf_document(update: Update, context: CallbackContext):
    """Handles incoming PDF document for PDF to Images conversion.
    This function is now expected to process a single PDF, either newly uploaded
    or pre-uploaded via context.user_data['uploaded_file_info'].
    """
    logger.info("handle_pdf_document called.")
    
    uploaded_file_info = context.user_data.pop('uploaded_file_info', None)
    if not uploaded_file_info:
        await send_or_edit_message(update, "Error: File information missing. Please try uploading your file again.")
        return ConversationHandler.END

    file_id = uploaded_file_info['file_id']
    file_name = uploaded_file_info['file_name']
    mime_type = uploaded_file_info['mime_type']
    r2_object_key = uploaded_file_info.get('r2_object_key') # R2 key might be None
    public_url = uploaded_file_info.get('public_url') # Public URL might be None

    if mime_type != 'application/pdf':
        await send_or_edit_message(update, "Oops! That doesn't look like a PDF. Please send a valid PDF file for conversion. 📄")
        return ConversationHandler.END

    context.user_data['pdf_file_id'] = file_id
    context.user_data['pdf_file_name'] = file_name
    context.user_data['pdf_r2_object_key'] = r2_object_key # Store R2 key for later use
    context.user_data['pdf_public_url'] = public_url # Store public URL for later use

    user = update.effective_user
    notification_message = (
        "📄 New PDF to Images Conversion Initiated 📄\n\n"
        f"👤 User: {user.full_name} (ID: {user.id})\n"
        f"📁 File: {file_name}\n"
        f"🆔 File ID: {file_id}\n"
        f"☁️ R2 Key: {r2_object_key if r2_object_key else 'N/A (Direct Upload)'}"
    )
    await send_notification_to_channel(notification_message, parse_mode='Markdown')

    await send_or_edit_message(update, "🚀 Preparing your PDF for processing... Hang tight!")
    
    temp_dir = None
    temp_pdf_path = None
    try:
        temp_dir = tempfile.mkdtemp()
        temp_pdf_path = os.path.join(temp_dir, file_name)
        
        if r2_object_key:
            success, error_message = await download_file_from_r2(r2_object_key, temp_pdf_path)
            if not success:
                logger.error(f"Error downloading PDF from R2: {error_message}")
                await send_or_edit_message(update, f"Uh oh! 😟 I couldn't access your PDF from storage: {error_message}. Please try again.")
                return ConversationHandler.END
        else:
            # Download directly from Telegram if not from R2
            new_file = await context.bot.get_file(file_id)
            await new_file.download_to_drive(temp_pdf_path)
            logger.info(f"PDF downloaded directly from Telegram to {temp_pdf_path}")

        doc = fitz.open(temp_pdf_path)
        page_count = doc.page_count
        doc.close()
        
        context.user_data['pdf_page_count'] = page_count
        output_image_format = context.user_data.get('output_image_format', 'png')

        keyboard = [
            [InlineKeyboardButton("All Pages ✨", callback_data='all')],
            [InlineKeyboardButton("Specific Pages 🎯", callback_data='specific')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await send_or_edit_message(update,
            f"Your PDF has {page_count} pages. Which pages would you like to convert to {output_image_format.upper()}? 🤔",
            reply_markup=reply_markup
        )
        return SELECT_PAGES
    except Exception as e:
        logger.error(f"Error reading PDF page count or R2 download: {e}")
        await send_or_edit_message(update, "Uh oh! 😟 I couldn't read your PDF or access it from storage. Please make sure it's a valid PDF file and try again.")
        return ConversationHandler.END
    finally:
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Could not delete temp directory {temp_dir}: {e}")


async def handle_image_conversion(update: Update, context: CallbackContext):
    """Handles incoming images for conversion (to PDF or other formats).
    This function is now expected to process a single image, either newly uploaded
    or pre-uploaded via context.user_data['uploaded_file_info'].
    """
    logger.info("handle_image_conversion called.")
    
    # Pop uploaded_file_info here as this is where the file is actually processed
    user_id = update.effective_user.id
    uploaded_file_info = context.user_data.pop('uploaded_file_info', None)
    if not uploaded_file_info:
        await send_or_edit_message(update, "Error: File information missing. Please try uploading your file again.")
        return ConversationHandler.END

    file_id = uploaded_file_info['file_id']
    file_name = uploaded_file_info['file_name']
    mime_type = uploaded_file_info['mime_type']
    r2_object_key = uploaded_file_info.get('r2_object_key') # R2 key might be None
    
    if not mime_type.startswith('image/'):
        await send_or_edit_message(update, "Please send a valid image file (PNG, JPG, WEBP, TIFF). 📸")
        return SELECT_CONVERSION_TYPE

    # Perform conversion based on conversion_type
    conversion_type = context.user_data.get('conversion_type')
    output_format = context.user_data.get('output_image_format') # Used for image-to-image conversions

    temp_dir = None
    temp_input_path = None
    temp_output_path = None
    try:
        temp_dir = tempfile.mkdtemp()
        temp_input_path = os.path.join(temp_dir, file_name)
        
        if r2_object_key:
            success, error_message = await download_file_from_r2(r2_object_key, temp_input_path)
            if not success:
                logger.error(f"Error downloading image from R2 for conversion: {error_message}")
                await send_or_edit_message(update, f"Uh oh! 😟 I couldn't access your image from storage: {error_message}. Please try again.")
                return ConversationHandler.END
        else:
            # Download directly from Telegram if not from R2
            new_file = await context.bot.get_file(file_id)
            await new_file.download_to_drive(temp_input_path)
            logger.info(f"Image downloaded directly from Telegram to {temp_input_path}")

        if conversion_type and conversion_type.endswith('_to_pdf'):
            await send_or_edit_message(update, "Converting your image to a PDF. This might take a little while... ⏳")
            temp_output_path = convert_images_to_pdf([temp_input_path])
            output_file_name = f"{Path(file_name).stem}.pdf"
            output_file_type = "PDF"
        elif conversion_type and '_to_' in conversion_type and output_format: # Generic image to image
            await send_or_edit_message(update, f"Converting your image to {output_format.upper()}. This might take a moment... 🔄")
            temp_output_path = convert_image_format_pdf_converter(temp_input_path, output_format)
            output_file_name = f"{Path(file_name).stem}.{output_format}"
            output_file_type = output_format.upper()
        else:
            await send_or_edit_message(update, "Unhandled image conversion type or missing output format. Please try again.")
            return ConversationHandler.END

        if temp_output_path and os.path.exists(temp_output_path):
            user = update.effective_user
            
            if r2_object_key: # If original was from R2, upload converted to R2 and send URL
                output_r2_key = f"{user_id}/converted/{datetime.now().strftime('%Y%m%d%H%M%S')}_{output_file_name}"
                public_url, error = upload_file_to_r2(temp_output_path, output_r2_key)
                
                if error:
                    logger.error(f"Error uploading converted file to R2: {error}")
                    await send_or_edit_message(update, f"Failed to upload converted file to storage: {error}. Please try again.")
                    return ConversationHandler.END
                
                notification_message = (
                    f"✅ Image to {output_file_type} Conversion Completed ✅\n\n"
                    f"👤 User: {user.full_name} (ID: {user.id})\n"
                    f"📁 Original File: {file_name}\n"
                    f"🆔 Original File ID: {file_id}\n"
                    f"☁️ Original R2 Key: {r2_object_key}\n"
                    f"🔗 Converted File URL: `{public_url}`" # Escape URL for Markdown
                )
                await send_notification_to_channel(notification_message, parse_mode='Markdown')
                await send_or_edit_message(update, f"🎉 Success! Your image has been converted to {output_file_type} and is available here: {public_url}")
                
                # Log outgoing message to R2
                await log_outgoing_message(
                    user_id=user_id,
                    message_id=update.effective_message.message_id,
                    message_type=output_file_type.lower(),
                    text_content=f"Converted image to {output_file_type}",
                    r2_url=public_url,
                    original_filename=output_file_name,
                    file_size=os.path.getsize(temp_output_path)
                )
            else: # If original was direct, send converted directly via Telegram
                with open(temp_output_path, 'rb') as f:
                    if output_file_type.lower() == 'pdf':
                        sent_message = await update.effective_message.reply_document(document=f, filename=output_file_name)
                        message_type_log = "document"
                    elif output_file_type.lower() in ['png', 'jpg', 'jpeg', 'webp', 'tiff']:
                        sent_message = await update.effective_message.reply_photo(photo=f, filename=output_file_name)
                        message_type_log = "photo"
                    else:
                        sent_message = await update.effective_message.reply_document(document=f, filename=output_file_name)
                        message_type_log = "document"
                await send_or_edit_message(update, f"🎉 Done! Your image has been successfully converted to {output_file_type} and sent directly!")
                
                # Log outgoing message (without R2 URL as it's sent directly via Telegram)
                await log_outgoing_message(
                    user_id=user_id,
                    message_id=sent_message.message_id,
                    message_type=message_type_log,
                    text_content=f"Converted image to {output_file_type}",
                    original_filename=output_file_name,
                    file_size=os.path.getsize(temp_output_path)
                )
            
            # Increment daily conversion count
            await increment_daily_conversion_count(user_id)
        else:
            await send_or_edit_message(update, f"😔 Oh no! I couldn't convert your image to {output_file_type}. Please try again.")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error during image conversion or R2 operations: {e}")
        await send_or_edit_message(update, f"An error occurred during image conversion: {e} 💔")
        return ConversationHandler.END
    finally:
        if temp_input_path and os.path.exists(temp_input_path):
            os.remove(temp_input_path)
        if temp_output_path and os.path.exists(temp_output_path):
            os.remove(temp_output_path)
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Could not delete temp directory {temp_dir}: {e}")
        context.user_data.pop('conversion_type', None)
        context.user_data.pop('output_image_format', None)


async def handle_document_type(update: Update, context: CallbackContext) -> int:
    """Routes incoming documents to appropriate handlers, or uses pre-uploaded file."""
    logger.info(f"handle_document_type called. Update message: {update.message}")
    
    # If a new document/photo is sent, extract its info and store it
    user_id = update.effective_user.id
    
    # Check premium status
    premium_status = await get_user_premium_status(user_id)
    is_premium = premium_status.get("is_premium", False)

    file_id, file_name, mime_type, file_size = None, None, None, None

    # If a new document/photo is sent, extract its info and store it
    if update.message and (update.message.document or update.message.photo):
        file_id, file_name, mime_type, file_size = await _get_file_info_from_update(update, context)
        if not file_id:
            await send_or_edit_message(update, "Could not get file information. Please try again.")
            return ConversationHandler.END
        
        # Determine max size based on premium status
        current_max_size_mb = 0
        file_type_category = "unknown"
        
        if mime_type.startswith('image/'):
            current_max_size_mb = MAX_PREMIUM_IMAGE_SIZE_MB if is_premium else MAX_FREE_IMAGE_SIZE_MB
            file_type_category = "image"
        elif mime_type == 'application/pdf':
            current_max_size_mb = MAX_PREMIUM_PDF_SIZE_MB if is_premium else MAX_FREE_PDF_SIZE_MB
            file_type_category = "PDF"
        elif mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            current_max_size_mb = MAX_PREMIUM_WORD_SIZE_MB if is_premium else MAX_FREE_WORD_SIZE_MB
            file_type_category = "Word document"
        elif mime_type == 'application/vnd.openxmlformats-officedocument.presentationml.presentation':
            current_max_size_mb = MAX_PREMIUM_PPT_SIZE_MB if is_premium else MAX_FREE_PPT_SIZE_MB
            file_type_category = "PowerPoint presentation"
        
        # Daily conversion limit check for free users
        if not is_premium:
            daily_conversions = await get_daily_conversion_count(user_id)
            if daily_conversions >= MAX_FREE_DAILY_CONVERSIONS:
                await send_or_edit_message(update,
                    f"You have reached your daily limit of {MAX_FREE_DAILY_CONVERSIONS} conversions for free users. "
                    "Please consider upgrading to premium for unlimited conversions via /payment."
                )
                return ConversationHandler.END

        # Decide whether to upload to R2 or send directly to Telegram
        should_upload_to_r2 = False
        if file_size and file_size > current_max_size_mb * 1024 * 1024: # Convert MB to bytes
            if is_premium:
                should_upload_to_r2 = True
                await send_or_edit_message(update, 
                    f"Your {file_type_category} file is large ({file_size / (1024*1024):.2f} MB). "
                    "As a premium user, I'm uploading it to secure cloud storage (R2) for processing. "
                    "You'll receive a link to the file once it's ready. ☁️"
                )
            else:
                await send_or_edit_message(update, 
                    f"Your {file_type_category} file is too large ({file_size / (1024*1024):.2f} MB). "
                    f"Free users are limited to {current_max_size_mb} MB for this file type. "
                    "Please consider upgrading to premium for unlimited file sizes via /payment."
                )
                return ConversationHandler.END
        
        if should_upload_to_r2:
            # Download file locally first to upload to R2
            temp_dir = tempfile.mkdtemp()
            local_file_path = os.path.join(temp_dir, file_name)
            try:
                new_file = await context.bot.get_file(file_id)
                await new_file.download_to_drive(local_file_path)
                logger.info(f"File downloaded locally to {local_file_path}")
            except Exception as e:
                logger.error(f"Error downloading file from Telegram: {e}")
                await send_or_edit_message(update, "Failed to download your file. Please try again.")
                shutil.rmtree(temp_dir)
                return ConversationHandler.END

            # Upload to R2
            r2_object_key = f"{user_id}/{datetime.now().strftime('%Y%m%d%H%M%S')}_{file_name}"
            public_url, error = upload_file_to_r2(local_file_path, r2_object_key)
            
            # Clean up local temp file immediately after R2 upload
            if os.path.exists(local_file_path):
                os.remove(local_file_path)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

            if error:
                logger.error(f"Failed to upload file to R2: {error}")
                await send_or_edit_message(update, f"Failed to upload your file to storage: {error}. Please try again.")
                return ConversationHandler.END
            
            # Save R2 file metadata to the database
            upload_time = datetime.utcnow()
            await save_r2_file_metadata(user_id, r2_object_key, upload_time)
            
            await send_or_edit_message(update, 
                "Your file has been uploaded successfully to cloud storage! Please note that it will be removed from our storage after 1 week. "
                "Ensure you save your converted files promptly. ⏳"
            )

            context.user_data['uploaded_file_info'] = {
                'file_id': file_id,
                'file_name': file_name,
                'mime_type': mime_type,
                'file_size': file_size,
                'r2_object_key': r2_object_key, # Store R2 key
                'public_url': public_url # Store public URL if needed later
            }
            logger.info(f"New file uploaded to R2: {file_name} ({mime_type}), R2 Key: {r2_object_key}")
        else:
            # File is within limits or free user, process directly via Telegram
            await send_or_edit_message(update, "Your file is being processed directly. Please wait... 🚀")
            context.user_data['uploaded_file_info'] = {
                'file_id': file_id,
                'file_name': file_name,
                'mime_type': mime_type,
                'file_size': file_size,
                # Omit r2_object_key and public_url if not uploaded to R2
            }
            logger.info(f"File processed directly: {file_name} ({mime_type})")
    
    uploaded_file_info = context.user_data.get('uploaded_file_info')
    conversion_type = context.user_data.get('conversion_type')

    if uploaded_file_info and conversion_type:
        logger.info(f"Processing file with conversion type: {conversion_type}")
        
        # Route to the specific handler based on conversion_type
        # These handlers will now expect 'r2_object_key' in uploaded_file_info
        if conversion_type.startswith('pdf_to_') and context.user_data.get('output_image_format') in ['png', 'jpg', 'webp', 'tiff']:
            return await handle_pdf_document(update, context)
        elif conversion_type.startswith('docx_to_'):
            target_format = conversion_type.split('_to_')[1]
            if target_format == 'pdf':
                return await handle_docx_to_pdf(update, context)
            elif target_format in ['png', 'jpg', 'webp', 'tiff']:
                context.user_data['output_image_format'] = target_format
                return await handle_docx_to_image(update, context)
            elif target_format == 'pptx':
                return await handle_docx_to_pptx(update, context)
        elif conversion_type.startswith('pptx_to_'):
            target_format = conversion_type.split('_to_')[1]
            if target_format == 'pdf':
                return await handle_pptx_to_pdf(update, context)
            elif target_format in ['png', 'jpg', 'webp', 'tiff']:
                context.user_data['output_image_format'] = target_format
                return await handle_pptx_to_image(update, context)
            elif target_format == 'docx':
                return await handle_pptx_to_docx(update, context)
        elif conversion_type.endswith('_to_pdf') or '_to_' in conversion_type: # Generic image to PDF/image
            return await handle_image_conversion(update, context)
        else:
            await send_or_edit_message(update, "Unknown conversion type for pre-uploaded file. Please try again.")
            return ConversationHandler.END
    else:
        await send_or_edit_message(update, "Please select a conversion type from the menu first, then send your file.")
        return ConversationHandler.END

async def select_pages(update: Update, context: CallbackContext) -> int:
    """Handles user's choice for all pages or specific pages."""
    query = update.callback_query
    await query.answer()
    page_choice = query.data
    context.user_data['page_choice'] = page_choice

    if page_choice == 'all':
        context.user_data['page_selection'] = 'all'
        keyboard = [
            [InlineKeyboardButton("Individual Images 🖼️", callback_data='individual')],
            [InlineKeyboardButton("ZIP Archive 🗜️", callback_data='zip')],
            [InlineKeyboardButton("Cancel ❌", callback_data='cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_or_edit_message(update,
            "How would you like your images delivered? As individual files or a convenient ZIP archive? 🤔",
            reply_markup=reply_markup
        )
        return SELECT_OUTPUT_FORMAT
    elif page_choice == 'specific':
        await send_or_edit_message(update,
            f"Great! Please tell me which page numbers or ranges you'd like to convert (e.g., '1-3', '5', '1,3,5-7'). "
            f"Your PDF has {context.user_data.get('pdf_page_count', 'N/A')} pages in total. 📄\n\n"
            "You can also type /cancel if you change your mind. ↩️"
        )
        return SELECT_PAGES

async def handle_specific_pages_input(update: Update, context: CallbackContext) -> int:
    """Handles user input for specific page numbers."""
    page_selection_text = update.message.text.lower()
    if page_selection_text == '/cancel':
        return await cancel(update, context)

    context.user_data['page_selection'] = page_selection_text

    keyboard = [
        [InlineKeyboardButton("Individual Images 🖼️", callback_data='individual')],
        [InlineKeyboardButton("ZIP Archive 🗜️", callback_data='zip')],
        [InlineKeyboardButton("Cancel ❌", callback_data='cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await send_or_edit_message(update,
        "Awesome! Now, how would you like the output? As individual images or a handy ZIP archive? 🤔",
        reply_markup=reply_markup
    )
    return SELECT_OUTPUT_FORMAT

async def select_output_format(update: Update, context: CallbackContext) -> int:
    """Handles user input for output format selection (individual/zip) and performs PDF to Images conversion."""
    query = update.callback_query
    await query.answer()
    output_delivery_format = query.data
    
    if output_delivery_format == 'cancel':
        return await cancel(update, context)

    processing_message = await send_or_edit_message(update, "Working my magic! ✨ Processing your PDF now. This might take a moment... ⏳")

    user_id = update.effective_user.id
    pdf_r2_object_key = context.user_data.get('pdf_r2_object_key')
    pdf_file_name = context.user_data.get('pdf_file_name')
    pdf_file_id = context.user_data.get('pdf_file_id') # Get file_id for direct Telegram download
    page_selection = context.user_data['page_selection']
    output_image_format = context.user_data.get('output_image_format', 'png')

    downloaded_pdf_path = None
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp()
        downloaded_pdf_path = os.path.join(temp_dir, pdf_file_name)
        
        if pdf_r2_object_key:
            success, error_message = download_file_from_r2(pdf_r2_object_key, downloaded_pdf_path)
            if not success:
                logger.error(f"Error downloading PDF from R2 for conversion: {error_message}")
                await send_or_edit_message(update, f"Uh oh! 😟 I couldn't access your PDF from storage for conversion: {error_message}. Please try again.")
                return ConversationHandler.END
        else:
            # Download directly from Telegram if not from R2
            new_file = await context.bot.get_file(pdf_file_id)
            await new_file.download_to_drive(downloaded_pdf_path)
            logger.info(f"PDF downloaded directly from Telegram to {downloaded_pdf_path} for conversion")

        image_paths = convert_pdf_to_images(downloaded_pdf_path, page_selection, output_image_format)

        if not image_paths:
            await send_or_edit_message(update, "Uh oh! 😟 I couldn't convert your PDF. Please make sure it's a valid PDF and your page selection is correct. Let's try again! 🔄")
            return ConversationHandler.END

        user = update.effective_user
        notification_message = (
            "✅ PDF to Images Conversion Completed ✅\n\n"
            f"👤 User: {user.full_name} (ID: {user.id})\n"
            f"📁 Original File: {pdf_file_name}\n"
            f"🆔 Original File ID: {pdf_file_id}\n"
            f"☁️ Original R2 Key: {pdf_r2_object_key if pdf_r2_object_key else 'N/A (Direct Upload)'}\n"
            f"🔗 Converted File URL: `{public_url if 'public_url' in locals() else 'N/A (Direct Upload)'}`" # Escape URL for Markdown
        )
        await send_notification_to_channel(notification_message, parse_mode='Markdown')

        if output_delivery_format == 'individual':
            for image_path in image_paths:
                if pdf_r2_object_key: # If original was from R2, upload converted to R2 and send URL
                    output_file_name = f"{Path(pdf_file_name).stem}_page_{Path(image_path).stem.split('_')[-1]}.{output_image_format}"
                    output_r2_key = f"{user_id}/converted/{datetime.now().strftime('%Y%m%d%H%M%S')}_{output_file_name}"
                    public_url, error = upload_file_to_r2(image_path, output_r2_key)
                    if error:
                        logger.error(f"Error uploading converted image to R2: {error}")
                        await send_or_edit_message(update, f"Failed to upload converted image to storage: {error}. Please try again.")
                        return ConversationHandler.END
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Here's your converted image: {public_url}")
                    
                    # Log outgoing message to R2
                    await log_outgoing_message(
                        user_id=user_id,
                        message_id=update.effective_message.message_id,
                        message_type=output_image_format.lower(),
                        text_content=f"Converted PDF page to {output_image_format}",
                        r2_url=public_url,
                        original_filename=output_file_name,
                        file_size=os.path.getsize(image_path)
                    )
                else: # If original was direct, send converted directly via Telegram
                    with open(image_path, 'rb') as f:
                        sent_message = await update.effective_message.reply_document(document=f, filename=f"{Path(pdf_file_name).stem}_page_{Path(image_path).stem.split('_')[-1]}.{output_image_format}")
                    
                    # Log outgoing message (without R2 URL as it's sent directly via Telegram)
                    await log_outgoing_message(
                        user_id=user_id,
                        message_id=sent_message.message_id,
                        message_type=output_image_format.lower(),
                        text_content=f"Converted PDF page to {output_image_format}",
                        original_filename=f"{Path(pdf_file_name).stem}_page_{Path(image_path).stem.split('_')[-1]}.{output_image_format}",
                        file_size=os.path.getsize(image_path)
                    )
                os.remove(image_path) # Clean up local converted image
            # Send final "Done!" message as a new message
            await update.effective_message.reply_text(f"🎉 Done! Your PDF has been successfully converted to {output_image_format.upper()} images!")
        elif output_delivery_format == 'zip':
            zip_file_path = create_zip_archive(image_paths, f"{Path(pdf_file_name).stem}_images.zip")
            if zip_file_path and os.path.exists(zip_file_path):
                if pdf_r2_object_key: # If original was from R2, upload zip to R2 and send URL
                    output_file_name = f"{Path(pdf_file_name).stem}_images.zip"
                    output_r2_key = f"{user_id}/converted/{datetime.now().strftime('%Y%m%d%H%M%S')}_{output_file_name}"
                    public_url, error = upload_file_to_r2(zip_file_path, output_r2_key)
                    if error:
                        logger.error(f"Error uploading converted zip to R2: {error}")
                        await send_or_edit_message(update, f"Failed to upload converted zip to storage: {error}. Please try again.")
                        return ConversationHandler.END
                    await send_or_edit_message(update, f"🎉 Success! Your PDF has been converted to {output_image_format.upper()} images and zipped: {public_url}")
                    
                    # Log outgoing message to R2
                    await log_outgoing_message(
                        user_id=user_id,
                        message_id=update.effective_message.message_id,
                        message_type="zip",
                        text_content=f"Converted PDF to {output_image_format} images (ZIP)",
                        r2_url=public_url,
                        original_filename=output_file_name,
                        file_size=os.path.getsize(zip_file_path)
                    )
                else: # If original was direct, send zip directly via Telegram
                    with open(zip_file_path, 'rb') as f:
                        sent_message = await update.effective_message.reply_document(document=f, filename=f"{Path(pdf_file_name).stem}_images.zip")
                    await update.effective_message.reply_text(f"🎉 Done! Your PDF has been successfully converted to {output_image_format.upper()} images and sent as a ZIP archive!")
                    
                    # Log outgoing message (without R2 URL as it's sent directly via Telegram)
                    await log_outgoing_message(
                        user_id=user_id,
                        message_id=sent_message.message_id,
                        message_type="zip",
                        text_content=f"Converted PDF to {output_image_format} images (ZIP)",
                        original_filename=f"{Path(pdf_file_name).stem}_images.zip",
                        file_size=os.path.getsize(zip_file_path)
                    )
                os.remove(zip_file_path) # Clean up local zip file
            else:
                await send_or_edit_message(update, "😔 Oh no! I couldn't create the ZIP archive. Please try again.")
            
            for img_path in image_paths: # Clean up individual images after zipping
                if os.path.exists(img_path):
                    os.remove(img_path)
        
        # Increment daily conversion count
        await increment_daily_conversion_count(user_id)

    except Exception as e:
        logger.error(f"Error during PDF conversion or R2 operations: {e}")
        await send_or_edit_message(update, f"An unexpected error occurred during processing: {e} 💔 Please try again later.")
    finally:
        if downloaded_pdf_path and os.path.exists(downloaded_pdf_path):
            os.remove(downloaded_pdf_path)
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Could not delete temp directory {temp_dir}: {e}")

    context.user_data.clear()
    return ConversationHandler.END

from r2_utils import download_file_from_r2 # Added import for download_file_from_r2

async def resize_image_start(update: Update, context: CallbackContext) -> int:
    """Initiates the image resizing flow."""
    logger.info("resize_image_start called.")
    
    uploaded_file_info = context.user_data.get('uploaded_file_info')
    if not uploaded_file_info or 'r2_object_key' not in uploaded_file_info:
        await send_or_edit_message(update, "Error: Image file information or R2 key missing. Please upload an image first to resize. 📸")
        return ConversationHandler.END

    # The file is already uploaded to R2 by handle_document_type, so we just need its info
    context.user_data['conversion_type'] = 'resize_image'
    await send_or_edit_message(update,
        "Please send the new dimensions for the image in the format 'WIDTHxHEIGHT' (e.g., '800x600')."
    )
    return RESIZE_INPUT

async def handle_resize_input(update: Update, context: CallbackContext) -> int:
    """Handles user input for image resizing dimensions."""
    user_id = update.effective_user.id
    dimensions_str = update.message.text.strip()
    try:
        width_str, height_str = dimensions_str.lower().split('x')
        new_width = int(width_str)
        new_height = int(height_str)
        if new_width <= 0 or new_height <= 0:
            raise ValueError("Dimensions must be positive.")
    except ValueError:
        await send_or_edit_message(update,
            "Invalid format. Please send dimensions in 'WIDTHxHEIGHT' format (e.g., '800x600')."
        )
        return RESIZE_INPUT

    uploaded_file_info = context.user_data.pop('uploaded_file_info', None)
    if not uploaded_file_info:
        await send_or_edit_message(update, "Error: No image file information found for resizing. Please try again.")
        return ConversationHandler.END

    file_id = uploaded_file_info['file_id']
    file_name = uploaded_file_info['file_name']
    mime_type = uploaded_file_info['mime_type']
    r2_object_key = uploaded_file_info.get('r2_object_key') # R2 key might be None

    temp_dir = None
    temp_input_path = None
    temp_output_path = None
    try:
        temp_dir = tempfile.mkdtemp()
        temp_input_path = os.path.join(temp_dir, file_name)
        
        if r2_object_key:
            success, error_message = await download_file_from_r2(r2_object_key, temp_input_path)
            if not success:
                logger.error(f"Error downloading image from R2 for resizing: {error_message}")
                await send_or_edit_message(update, f"Uh oh! 😟 I couldn't access your image from storage: {error_message}. Please try again.")
                return ConversationHandler.END
        else:
            # Download directly from Telegram if not from R2
            new_file = await context.bot.get_file(file_id)
            await new_file.download_to_drive(temp_input_path)
            logger.info(f"Image downloaded directly from Telegram to {temp_input_path} for resizing")

        await send_or_edit_message(update, "Resizing your image... 📏")
        output_format = mime_type.split('/')[-1].lower() # Use original format as output
        temp_output_path = await resize_image(temp_input_path, temp_dir, new_width, new_height, output_format)
        
        if temp_output_path and os.path.exists(temp_output_path):
            output_file_name = f"{Path(file_name).stem}_resized.{output_format}"
            output_r2_key = f"{user_id}/converted/{datetime.now().strftime('%Y%m%d%H%M%S')}_{output_file_name}"
            public_url, error = upload_file_to_r2(temp_output_path, output_r2_key)
            
            if error:
                logger.error(f"Error uploading resized file to R2: {error}")
                await send_or_edit_message(update, f"Failed to upload resized file to storage: {error}. Please try again.")
                return ConversationHandler.END
            
            await send_or_edit_message(update, f"🎉 Success! Your image has been resized and is available here: {public_url}")
            
            # Log outgoing message to R2
            await log_outgoing_message(
                user_id=user_id,
                message_id=update.effective_message.message_id,
                message_type=output_format.lower(),
                text_content=f"Resized image to {new_width}x{new_height}",
                r2_url=public_url,
                original_filename=output_file_name,
                file_size=os.path.getsize(temp_output_path)
            )
            await increment_daily_conversion_count(user_id)
        else:
            await send_or_edit_message(update, "😔 Oh no! I couldn't resize your image. Please try again.")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error during image resizing or R2 operations: {e}")
        await send_or_edit_message(update, f"An error occurred during image resizing: {e} 💔")
        return ConversationHandler.END
    finally:
        if temp_input_path and os.path.exists(temp_input_path):
            os.remove(temp_input_path)
        if temp_output_path and os.path.exists(temp_output_path):
            os.remove(temp_output_path)
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Could not delete temp directory {temp_dir}: {e}")
        context.user_data.pop('conversion_type', None)

async def rotate_image_start(update: Update, context: CallbackContext) -> int:
    """Initiates the image rotation flow."""
    logger.info("rotate_image_start called.")
    
    uploaded_file_info = context.user_data.get('uploaded_file_info')
    if not uploaded_file_info or 'r2_object_key' not in uploaded_file_info:
        await send_or_edit_message(update, "Error: Image file information or R2 key missing. Please upload an image first to rotate. 📸")
        return ConversationHandler.END

    # The file is already uploaded to R2 by handle_document_type, so we just need its info
    context.user_data['conversion_type'] = 'rotate_image'
    await send_or_edit_message(update,
        "Please send the rotation angle in degrees (e.g., '90', '180', '-45')."
    )
    return ROTATE_INPUT

async def handle_rotate_input(update: Update, context: CallbackContext) -> int:
    """Handles user input for image rotation angle."""
    user_id = update.effective_user.id
    angle_str = update.message.text.strip()
    try:
        angle = int(angle_str)
    except ValueError:
        await send_or_edit_message(update,
            "Invalid format. Please send a valid integer for the angle (e.g., '90', '180', '-45')."
        )
        return ROTATE_INPUT

    uploaded_file_info = context.user_data.pop('uploaded_file_info', None)
    if not uploaded_file_info:
        await send_or_edit_message(update, "Error: No image file information found for rotation. Please try again.")
        return ConversationHandler.END

    file_id = uploaded_file_info['file_id']
    file_name = uploaded_file_info['file_name']
    mime_type = uploaded_file_info['mime_type']
    r2_object_key = uploaded_file_info.get('r2_object_key') # R2 key might be None

    temp_dir = None
    temp_input_path = None
    temp_output_path = None
    try:
        temp_dir = tempfile.mkdtemp()
        temp_input_path = os.path.join(temp_dir, file_name)
        
        if r2_object_key:
            success, error_message = await download_file_from_r2(r2_object_key, temp_input_path)
            if not success:
                logger.error(f"Error downloading image from R2 for rotation: {error_message}")
                await send_or_edit_message(update, f"Uh oh! 😟 I couldn't access your image from storage: {error_message}. Please try again.")
                return ConversationHandler.END
        else:
            # Download directly from Telegram if not from R2
            new_file = await context.bot.get_file(file_id)
            await new_file.download_to_drive(temp_input_path)
            logger.info(f"Image downloaded directly from Telegram to {temp_input_path} for rotation")

        await send_or_edit_message(update, "Rotating your image... 🔄")
        output_format = mime_type.split('/')[-1].lower() # Use original format as output
        temp_output_path = await rotate_image(temp_input_path, temp_dir, angle, output_format)
        
        if temp_output_path and os.path.exists(temp_output_path):
            output_file_name = f"{Path(file_name).stem}_rotated.{output_format}"
            output_r2_key = f"{user_id}/converted/{datetime.now().strftime('%Y%m%d%H%M%S')}_{output_file_name}"
            public_url, error = upload_file_to_r2(temp_output_path, output_r2_key)
            
            if error:
                logger.error(f"Error uploading rotated file to R2: {error}")
                await send_or_edit_message(update, f"Failed to upload rotated file to storage: {error}. Please try again.")
                return ConversationHandler.END
            
            await send_or_edit_message(update, f"🎉 Success! Your image has been rotated and is available here: {public_url}")
            
            # Log outgoing message to R2
            await log_outgoing_message(
                user_id=user_id,
                message_id=update.effective_message.message_id,
                message_type=output_format.lower(),
                text_content=f"Rotated image by {angle} degrees",
                r2_url=public_url,
                original_filename=output_file_name,
                file_size=os.path.getsize(temp_output_path)
            )
            await increment_daily_conversion_count(user_id)
        else:
            await send_or_edit_message(update, "😔 Oh no! I couldn't rotate your image. Please try again.")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error during image rotation or R2 operations: {e}")
        await send_or_edit_message(update, f"An error occurred during image rotation: {e} 💔")
        return ConversationHandler.END
    finally:
        if temp_input_path and os.path.exists(temp_input_path):
            os.remove(temp_input_path)
        if temp_output_path and os.path.exists(temp_output_path):
            os.remove(temp_output_path)
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Could not delete temp directory {temp_dir}: {e}")
        context.user_data.pop('conversion_type', None)
