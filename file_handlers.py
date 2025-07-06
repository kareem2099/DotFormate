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
from utility_handlers import cancel, send_or_edit_message, _get_file_info_from_update # Import centralized cancel, send_or_edit_message, and _get_file_info_from_update
from admin_handlers import send_admin_notification
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
    
    # Pop uploaded_file_info here as this is where the file is actually processed
    uploaded_file_info = context.user_data.pop('uploaded_file_info', None)
    if uploaded_file_info:
        file_id = uploaded_file_info['file_id']
        file_name = uploaded_file_info['file_name']
        mime_type = uploaded_file_info['mime_type']
    else:
        # Fallback if for some reason it wasn't pre-stored (e.g., direct command)
        file_id, file_name, mime_type = await _get_file_info_from_update(update, context)

    if not file_id or mime_type != 'application/pdf':
        await send_or_edit_message(update, "Oops! That doesn't look like a PDF. Please send a valid PDF file for conversion. 📄")
        return ConversationHandler.END

    context.user_data['pdf_file_id'] = file_id
    context.user_data['pdf_file_name'] = file_name

    user = update.effective_user
    notification_message = (
        "📄 New PDF to Images Conversion Initiated 📄\n\n"
        f"👤 User: {user.full_name} (ID: {user.id})\n"
        f"📁 File: {file_name}\n"
        f"🆔 File ID: {file_id}"
    )
    await send_admin_notification(context, notification_message)

    await send_or_edit_message(update, "🚀 Downloading your PDF to check its page count... Hang tight!")
    
    temp_pdf_path = None
    try:
        temp_dir = tempfile.mkdtemp()
        temp_pdf_path = os.path.join(temp_dir, file_name)
        new_file = await context.bot.get_file(file_id)
        await new_file.download_to_drive(temp_pdf_path)
        
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
        logger.error(f"Error reading PDF page count: {e}")
        await send_or_edit_message(update, "Uh oh! 😟 I couldn't read your PDF. Please make sure it's a valid PDF file and try again.")
        return ConversationHandler.END
    finally:
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)
        if 'temp_dir' in locals() and temp_dir and os.path.exists(temp_dir):
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
    uploaded_file_info = context.user_data.pop('uploaded_file_info', None)
    if uploaded_file_info:
        file_id = uploaded_file_info['file_id']
        file_name = uploaded_file_info['file_name']
        mime_type = uploaded_file_info['mime_type']
    else:
        # Fallback if for some reason it wasn't pre-stored (e.g., direct command)
        file_id, file_name, mime_type = await _get_file_info_from_update(update, context)

    if not file_id or not mime_type.startswith('image/'):
        await send_or_edit_message(update, "Please send a valid image file (PNG, JPG, WEBP, TIFF). 📸")
        return SELECT_CONVERSION_TYPE # Or a more appropriate state

    temp_input_path = None
    try:
        temp_dir = tempfile.mkdtemp()
        temp_input_path = os.path.join(temp_dir, file_name)
        new_file = await context.bot.get_file(file_id)
        await new_file.download_to_drive(temp_input_path)
    except Exception as e:
        logger.error(f"Error downloading image file {file_name}: {e}")
        await send_or_edit_message(update, f"Failed to download your image: {e} 💔 Please try again.")
        return ConversationHandler.END

    # Perform conversion based on conversion_type
    conversion_type = context.user_data.get('conversion_type')
    output_format = context.user_data.get('output_image_format') # Used for image-to-image conversions

    temp_output_path = None
    try:
        if conversion_type and conversion_type.endswith('_to_pdf'):
            await send_or_edit_message(update, "Converting your image to a PDF. This might take a little while... ⏳")
            temp_output_path = convert_images_to_pdf([temp_input_path])
            if temp_output_path:
                with open(temp_output_path, 'rb') as f:
                    await context.bot.send_document(chat_id=update.effective_chat.id, document=f)
                user = update.effective_user
                notification_message = (
                    f"✅ Image to PDF Conversion Completed ✅\n\n"
                    f"👤 User: {user.full_name} (ID: {user.id})\n"
                    f"📁 File: {file_name}\n"
                    f"🆔 File ID: {file_id}"
                )
                await send_admin_notification(context, notification_message)
                await send_or_edit_message(update, "🎉 Success! Your image has been converted to PDF and sent!")
            else:
                await send_or_edit_message(update, "😔 Oh no! I couldn't convert your image to PDF. Please try again.")
            return ConversationHandler.END
        elif conversion_type and '_to_' in conversion_type and output_format: # Generic image to image
            await send_or_edit_message(update, f"Converting your image to {output_format.upper()}. This might take a moment... 🔄")
            temp_output_path = convert_image_format_pdf_converter(temp_input_path, output_format) # Using the one from pdf_converter
            if temp_output_path:
                with open(temp_output_path, 'rb') as f:
                    await context.bot.send_document(chat_id=update.effective_chat.id, document=f)
                user = update.effective_user
                notification_message = (
                    f"✅ Image to {output_format.upper()} Conversion Completed ✅\n\n"
                    f"👤 User: {user.full_name} (ID: {user.id})\n"
                    f"📁 File: {file_name}\n"
                    f"🆔 File ID: {file_id}"
                )
                await send_admin_notification(context, notification_message)
                await send_or_edit_message(update, f"✨ Your image converted to {output_format.upper()} and sent!")
            else:
                await send_or_edit_message(update, f"Failed to convert image. 😔")
            return ConversationHandler.END
        else:
            await send_or_edit_message(update, "Unhandled image conversion type or missing output format. Please try again.")
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error during image conversion: {e}")
        await send_or_edit_message(update, f"An error occurred during image conversion: {e} 💔")
        return ConversationHandler.END
    finally:
        if temp_input_path and os.path.exists(temp_input_path):
            os.remove(temp_input_path)
        if temp_output_path and os.path.exists(temp_output_path):
            os.remove(temp_output_path)
        if 'temp_dir' in locals() and temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Could not delete temp directory {temp_dir}: {e}")
        context.user_data.pop('conversion_type', None) # Clear conversion type after processing
        context.user_data.pop('output_image_format', None) # Clear output format after processing


async def handle_document_type(update: Update, context: CallbackContext) -> int:
    """Routes incoming documents to appropriate handlers, or uses pre-uploaded file."""
    logger.info(f"handle_document_type called. Update message: {update.message}")
    
    # If a new document/photo is sent, extract its info and store it
    if update.message and (update.message.document or update.message.photo):
        file_id, file_name, mime_type = await _get_file_info_from_update(update, context)
        if not file_id:
            await send_or_edit_message(update, "Could not get file information. Please try again.")
            return ConversationHandler.END
        context.user_data['uploaded_file_info'] = {
            'file_id': file_id,
            'file_name': file_name,
            'mime_type': mime_type
        }
        logger.info(f"New file uploaded: {file_name} ({mime_type})")
    
    uploaded_file_info = context.user_data.get('uploaded_file_info')
    conversion_type = context.user_data.get('conversion_type')

    if uploaded_file_info and conversion_type:
        logger.info(f"Processing file with conversion type: {conversion_type}")
        # The specific conversion handler will retrieve 'uploaded_file_info' from context.user_data
        # and clear it after use.
        
        # Route to the specific handler based on conversion_type
        if conversion_type.startswith('pdf_to_') and context.user_data.get('output_image_format') in ['png', 'jpg', 'webp', 'tiff']:
            # This handles PDF to PNG, PDF to JPG, etc.
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

    pdf_file_id = context.user_data['pdf_file_id']
    pdf_file_name = context.user_data['pdf_file_name']
    page_selection = context.user_data['page_selection']
    output_image_format = context.user_data.get('output_image_format', 'png')

    downloaded_pdf_path = None
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp()
        downloaded_pdf_path = os.path.join(temp_dir, pdf_file_name)
        new_file = await context.bot.get_file(pdf_file_id)
        await new_file.download_to_drive(downloaded_pdf_path)

        image_paths = convert_pdf_to_images(downloaded_pdf_path, page_selection, output_image_format)

        if not image_paths:
            await send_or_edit_message(update, "Uh oh! 😟 I couldn't convert your PDF. Please make sure it's a valid PDF and your page selection is correct. Let's try again! 🔄")
            return ConversationHandler.END

        if output_delivery_format == 'individual':
            for i, image_path in enumerate(image_paths):
                await send_or_edit_message(update, f"Sending image {i+1}/{len(image_paths)}... 📤")
                with open(image_path, 'rb') as f:
                    await context.bot.send_document(chat_id=update.effective_chat.id, document=f)
                os.remove(image_path)
            user = update.effective_user
            notification_message = (
                "✅ PDF to Images Conversion Completed ✅\n\n"
                f"👤 User: {user.full_name} (ID: {user.id})\n"
                f"📁 File: {pdf_file_name}\n"
                f"🆔 File ID: {pdf_file_id}"
            )
            await send_admin_notification(context, notification_message)
            await send_or_edit_message(update, f"🎉 Done! Your PDF has been successfully converted to {output_image_format.upper()} images and sent!")
        elif output_delivery_format == 'zip':
            await send_or_edit_message(update, "Almost there! Creating your ZIP archive... 🗜️")
            zip_path = create_zip_archive(image_paths, pdf_file_name)
            if zip_path:
                with open(zip_path, 'rb') as f:
                    await context.bot.send_document(chat_id=update.effective_chat.id, document=f)
                os.remove(zip_path)
                user = update.effective_user
                notification_message = (
                    "✅ PDF to Images Conversion Completed ✅\n\n"
                    f"👤 User: {user.full_name} (ID: {user.id})\n"
                    f"📁 File: {pdf_file_name}\n"
                    f"🆔 File ID: {pdf_file_id}"
                )
                await send_admin_notification(context, notification_message)
                await send_or_edit_message(update, f"🎉 Success! Your PDF has been converted to {output_image_format.upper()} and sent as a ZIP archive!")
            else:
                await send_or_edit_message(update, "😔 Oops! Failed to create the ZIP archive. Please try again.")
        
    except Exception as e:
        logger.error(f"Error during PDF conversion or sending: {e}")
        await send_or_edit_message(update, f"An unexpected error occurred during processing: {e} 💔 Please try again later.")
    finally:
        if downloaded_pdf_path and os.path.exists(downloaded_pdf_path):
            os.remove(downloaded_pdf_path)
        if 'image_paths' in locals(): # Ensure image_paths exists before iterating
            for path in image_paths:
                if os.path.exists(path):
                    os.remove(path)
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Could not delete temp directory {temp_dir}: {e}")

    context.user_data.clear()
    return ConversationHandler.END

async def resize_image_start(update: Update, context: CallbackContext) -> int:
    """Initiates the image resizing flow."""
    logger.info("resize_image_start called.")
    
    file_id, file_name, mime_type = await _get_file_info_from_update(update, context)
    if not file_id:
        await send_or_edit_message(update, "Please upload an image first to resize. 📸")
        return ConversationHandler.END

    context.user_data['uploaded_file_info'] = { # Re-store for handle_resize_input
        'file_id': file_id,
        'file_name': file_name,
        'mime_type': mime_type
    }
    context.user_data['conversion_type'] = 'resize_image'
    await send_or_edit_message(update,
        "Please send the new dimensions for the image in the format 'WIDTHxHEIGHT' (e.g., '800x600')."
    )
    return RESIZE_INPUT

async def handle_resize_input(update: Update, context: CallbackContext) -> int:
    """Handles user input for image resizing dimensions."""
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

    file_info = context.user_data.pop('uploaded_file_info', None)
    if not file_info:
        await send_or_edit_message(update, "No image file found to resize. Please try again.")
        return ConversationHandler.END

    file_id = file_info['file_id']
    file_name = file_info['file_name']
    mime_type = file_info['mime_type']

    downloaded_path = None
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp()
        downloaded_path = os.path.join(temp_dir, file_name)
        new_file = await context.bot.get_file(file_id)
        await new_file.download_to_drive(downloaded_path)
    except Exception as e:
        logger.error(f"Error downloading image file {file_name}: {e}")
        await send_or_edit_message(update, f"Failed to download your image: {e} 💔 Please try again.")
        return ConversationHandler.END

    await send_or_edit_message(update, "Resizing your image... 📏")
    try:
        output_format = mime_type.split('/')[-1].upper() # Use original format as output
        resized_path = await resize_image(downloaded_path, temp_dir, new_width, new_height, output_format)
        
        if resized_path and os.path.exists(resized_path):
            with open(resized_path, 'rb') as f:
                await context.bot.send_document(chat_id=update.effective_chat.id, document=f)
            await send_or_edit_message(update, "🎉 Success! Your image has been resized and sent!")
        else:
            await send_or_edit_message(update, "😔 Oh no! I couldn't resize your image. Please try again.")
    except Exception as e:
        logger.error(f"Error during image resizing: {e}")
        await send_or_edit_message(update, f"An error occurred during image resizing: {e} 💔")
    finally:
        if downloaded_path and os.path.exists(downloaded_path):
            os.remove(downloaded_path)
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Could not delete temp file {f}: {e}")
        context.user_data.pop('conversion_type', None)
    return ConversationHandler.END

async def rotate_image_start(update: Update, context: CallbackContext) -> int:
    """Initiates the image rotation flow."""
    logger.info("rotate_image_start called.")
    
    file_id, file_name, mime_type = await _get_file_info_from_update(update, context)
    if not file_id:
        await send_or_edit_message(update, "Please upload an image first to rotate. 📸")
        return ConversationHandler.END

    context.user_data['uploaded_file_info'] = { # Re-store for handle_rotate_input
        'file_id': file_id,
        'file_name': file_name,
        'mime_type': mime_type
    }
    context.user_data['conversion_type'] = 'rotate_image'
    await send_or_edit_message(update,
        "Please send the rotation angle in degrees (e.g., '90', '180', '-45')."
    )
    return ROTATE_INPUT

async def handle_rotate_input(update: Update, context: CallbackContext) -> int:
    """Handles user input for image rotation angle."""
    angle_str = update.message.text.strip()
    try:
        angle = int(angle_str)
    except ValueError:
        await send_or_edit_message(update,
            "Invalid format. Please send a valid integer for the angle (e.g., '90', '180', '-45')."
        )
        return ROTATE_INPUT

    file_info = context.user_data.pop('uploaded_file_info', None)
    if not file_info:
        await send_or_edit_message(update, "No image file found to rotate. Please try again.")
        return ConversationHandler.END

    file_id = file_info['file_id']
    file_name = file_info['file_name']
    mime_type = file_info['mime_type']

    downloaded_path = None
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp()
        downloaded_path = os.path.join(temp_dir, file_name)
        new_file = await context.bot.get_file(file_id)
        await new_file.download_to_drive(downloaded_path)
    except Exception as e:
        logger.error(f"Error downloading image file {file_name}: {e}")
        await send_or_edit_message(update, f"Failed to download your image: {e} 💔 Please try again.")
        return ConversationHandler.END

    await send_or_edit_message(update, "Rotating your image... 🔄")
    try:
        output_format = mime_type.split('/')[-1].upper() # Use original format as output
        rotated_path = await rotate_image(downloaded_path, temp_dir, angle, output_format)
        
        if rotated_path and os.path.exists(rotated_path):
            with open(rotated_path, 'rb') as f:
                await context.bot.send_document(chat_id=update.effective_chat.id, document=f)
            await send_or_edit_message(update, "🎉 Success! Your image has been rotated and sent!")
        else:
            await send_or_edit_message(update, "😔 Oh no! I couldn't rotate your image. Please try again.")
    except Exception as e:
        logger.error(f"Error during image rotation: {e}")
        await send_or_edit_message(update, f"An error occurred during image rotation: {e} 💔")
    finally:
        if downloaded_path and os.path.exists(downloaded_path):
            os.remove(downloaded_path)
        if temp_dir and os.path.exists(temp_dir):
            for f in Path(temp_dir).glob('*'):
                try:
                    f.unlink()
                except Exception as e:
                    logger.warning(f"Could not delete temp file {f}: {e}")
            os.rmdir(temp_dir)
        context.user_data.pop('conversion_type', None)
    return ConversationHandler.END
