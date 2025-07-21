import os
import logging
import tempfile
import subprocess
import shutil # Import shutil for directory removal
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler, filters
import fitz # Import fitz for PDF processing
from database import save_user_info, increment_daily_conversion_count
from admin_handlers import send_admin_notification
from ocr_tool import perform_ocr as process_ocr
from pdf_converter import merge_pdfs, split_pdf, compress_pdf, compress_image
from watermark_tool import (
    add_text_watermark_to_pdf,
    add_text_watermark_to_image,
    add_image_watermark_to_image, # Ensure this is imported
    add_image_watermark_to_pdf # Ensure this is imported
)
from url_downloader import download_file_from_url
from utility_handlers import start, help_command, cancel, send_or_edit_message # Import centralized utilities
from r2_utils import upload_file_to_r2, download_file_from_r2
from datetime import datetime

logger = logging.getLogger(__name__)

# States for the conversation handler
from constants import (
    MAIN_MENU, SELECT_CONVERSION_TYPE, SELECT_PAGES, SELECT_OUTPUT_FORMAT, SELECT_IMAGE_FORMAT,
    OCR_PROCESSING, MERGE_PDF_COLLECTION, SPLIT_PDF_INPUT_PAGES, COMPRESSION_PROCESSING,
    WATERMARK_FILE_INPUT, WATERMARK_TEXT_INPUT, WATERMARK_IMAGE_INPUT, WATERMARK_POSITION_INPUT,
    URL_INPUT, COMPRESS_FILE_PROCESSING, MAX_FREE_DAILY_CONVERSIONS # Import new constant
)
from database import get_user_premium_status, get_daily_conversion_count # Import new functions

# Specialized flow starters
async def ocr_flow_start(update: Update, context: CallbackContext) -> int:
    """Starts the OCR conversation flow."""
    context.user_data['conversion_type'] = 'ocr'
    await send_or_edit_message(update,
        "📄 Please send me the image or PDF file you'd like to extract text from. "
        "For best results, use clear, high-quality images with printed text."
    )
    return OCR_PROCESSING

async def merge_pdf_flow_start(update: Update, context: CallbackContext) -> int:
    """Starts the PDF merging conversation flow."""
    context.user_data['conversion_type'] = 'merge_pdf'
    await send_or_edit_message(update,
        "➕ Please send me the PDF files you'd like to merge, one at a time. "
        "Send all the files first, then type 'done' when you're finished."
    )
    return MERGE_PDF_COLLECTION

async def split_pdf_flow_start(update: Update, context: CallbackContext) -> int:
    """Starts the PDF splitting conversation flow."""
    context.user_data['conversion_type'] = 'split_pdf'
    await send_or_edit_message(update,
        "✂️ Please send me the PDF file you'd like to split. "
        "After sending the file, I'll ask you how you'd like to split it."
    )
    return SPLIT_PDF_INPUT_PAGES

async def compress_flow_start(update: Update, context: CallbackContext) -> int:
    """Starts the file compression conversation flow."""
    context.user_data['conversion_type'] = 'compress'
    await send_or_edit_message(update,
        "🗜️ Please send me the PDF, image, Word, or PowerPoint file you'd like to compress. "
        "I'll optimize it to reduce the file size while maintaining reasonable quality."
    )
    return COMPRESS_FILE_PROCESSING

async def watermark_flow_start(update: Update, context: CallbackContext) -> int:
    """Starts the watermarking conversation flow."""
    context.user_data['conversion_type'] = 'watermark'
    keyboard = [
        [InlineKeyboardButton("Text Watermark", callback_data='watermark_type_text')],
        [InlineKeyboardButton("Image Watermark", callback_data='watermark_type_image')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_or_edit_message(update,
        "✍️ What type of watermark would you like to add?",
        reply_markup=reply_markup
    )
    return WATERMARK_FILE_INPUT

async def url_conversion_flow_start(update: Update, context: CallbackContext) -> int:
    """Starts the URL-based conversion flow."""
    context.user_data['conversion_type'] = 'url_conversion'
    await send_or_edit_message(update,
        "🔗 Please send me the URL of the file you'd like to convert. "
        "I'll download it and then we can proceed with the conversion."
    )
    return URL_INPUT

# Document handlers
async def handle_ocr_document(update: Update, context: CallbackContext) -> int:
    """Handles OCR processing of documents."""
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

    if not (mime_type == 'application/pdf' or mime_type.startswith('image/')):
        await send_or_edit_message(update, "Sorry, I can only perform OCR on images and PDFs.")
        return ConversationHandler.END

    await send_or_edit_message(update, "🔍 Performing OCR on your file... This might take a moment.")

    try:
        temp_dir = tempfile.mkdtemp()
        input_path = os.path.join(temp_dir, file_name)
        
        success, error_message = await download_file_from_r2(r2_object_key, input_path)
        if not success:
            logger.error(f"Error downloading file from R2 for OCR: {error_message}")
            await send_or_edit_message(update, f"Uh oh! 😟 I couldn't access your file from storage: {error_message}. Please try again.")
            return ConversationHandler.END

        extracted_text = ""
        if mime_type == 'application/pdf':
            # Convert PDF to images, then perform OCR on each image
            pdf_doc = fitz.open(input_path)
            image_paths = []
            for page_num in range(pdf_doc.page_count):
                page = pdf_doc.load_page(page_num)
                pix = page.get_pixmap()
                img_path = os.path.join(temp_dir, f"page_{page_num}.png")
                pix.save(img_path)
                image_paths.append(img_path)
            pdf_doc.close()

            for img_path in image_paths:
                extracted_text += process_ocr(img_path) + "\n"
                os.remove(img_path) # Clean up page images
        elif mime_type.startswith('image/'):
            extracted_text = process_ocr(input_path)
        
        if extracted_text.strip():
            await send_or_edit_message(update, f"📝 *OCR Result:*\n\n```\n{extracted_text.strip()}\n```", parse_mode='Markdown')
            user = update.effective_user
            notification_message = (
                f"✅ OCR Conversion Completed ✅\n\n"
                f"👤 User: {user.full_name} (ID: {user.id})\n"
                f"📁 Original File: {file_name}\n"
                f"🆔 Original File ID: {file_id}\n"
                f"☁️ Original R2 Key: {r2_object_key}"
            )
            await send_admin_notification(context, notification_message)
            await send_or_edit_message(update, "🎉 Success! Text extracted and sent!")
            await increment_daily_conversion_count(user_id)
        else:
            await send_or_edit_message(update, "😔 No text could be extracted from the file. Please try with a clearer image or PDF.")
        
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error during OCR processing: {e}")
        await send_or_edit_message(update, f"An error occurred during OCR: {e} 💔 Please try again.")
        return ConversationHandler.END
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Could not delete temp directory {temp_dir}: {e}")

async def handle_merge_pdf_documents(update: Update, context: CallbackContext) -> int:
    """Handles PDF merging process."""
    user_id = update.effective_user.id
    user_data = context.user_data
    
    if 'pdf_r2_keys_to_merge' not in user_data:
        user_data['pdf_r2_keys_to_merge'] = []
        user_data['pdf_names_to_merge'] = []

    uploaded_file_info = context.user_data.get('uploaded_file_info', None)

    if update.message.text and update.message.text.lower() == 'done':
        if not user_data['pdf_r2_keys_to_merge']:
            await send_or_edit_message(update, "Please send at least one PDF file before typing 'done'.")
            return MERGE_PDF_COLLECTION
        
        await send_or_edit_message(update, "Merging your PDFs... This might take a moment. ⏳")
        temp_dir = None
        merged_pdf_path = None
        try:
            temp_dir = tempfile.mkdtemp()
            local_pdf_paths = []
            for r2_key, file_name in zip(user_data['pdf_r2_keys_to_merge'], user_data['pdf_names_to_merge']):
                local_path = os.path.join(temp_dir, file_name)
                success, error_message = await download_file_from_r2(r2_key, local_path)
                if not success:
                    logger.error(f"Error downloading PDF from R2 for merging: {error_message}")
                    await send_or_edit_message(update, f"Uh oh! 😟 I couldn't access one of your PDFs from storage: {error_message}. Please try again.")
                    return ConversationHandler.END
                local_pdf_paths.append(local_path)

            merged_pdf_path = merge_pdfs(local_pdf_paths)
            
            if merged_pdf_path and os.path.exists(merged_pdf_path):
                merged_file_name = f"merged_pdfs_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
                output_r2_key = f"{user_id}/converted/{merged_file_name}"
                public_url, error = upload_file_to_r2(merged_pdf_path, output_r2_key)
                
                if error:
                    logger.error(f"Error uploading merged PDF to R2: {error}")
                    await send_or_edit_message(update, f"Failed to upload merged file to storage: {error}. Please try again.")
                    return ConversationHandler.END
                
                user = update.effective_user
                notification_message = (
                    f"✅ PDF Merge Completed ✅\n\n"
                    f"👤 User: {user.full_name} (ID: {user.id})\n"
                    f"📁 Merged Files: {', '.join(user_data['pdf_names_to_merge'])}\n"
                    f"🔗 Merged File URL: {public_url}"
                )
                await send_admin_notification(context, notification_message)
                await send_or_edit_message(update, f"🎉 Here's your merged PDF file: {public_url}")
                await increment_daily_conversion_count(user_id)
            else:
                await send_or_edit_message(update, "😔 Oh no! I couldn't merge your PDFs. Please try again.")
            
            return ConversationHandler.END
        except Exception as e:
            logger.error(f"Error merging PDFs: {e}")
            await send_or_edit_message(update, f"An error occurred during PDF merging: {e} 💔 Please try again.")
            return ConversationHandler.END
        finally:
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.warning(f"Could not delete temp directory {temp_dir}: {e}")
            user_data.pop('pdf_r2_keys_to_merge', None)
            user_data.pop('pdf_names_to_merge', None)
            context.user_data.pop('uploaded_file_info', None) # Clear any lingering uploaded_file_info
    elif uploaded_file_info and uploaded_file_info['mime_type'] == 'application/pdf':
        user_data['pdf_r2_keys_to_merge'].append(uploaded_file_info['r2_object_key'])
        user_data['pdf_names_to_merge'].append(uploaded_file_info['file_name'])
        await send_or_edit_message(update, f"Received '{uploaded_file_info['file_name']}'. Send another PDF or type 'done' to merge.")
        context.user_data.pop('uploaded_file_info', None) # Consume the uploaded_file_info
        return MERGE_PDF_COLLECTION
    else:
        await send_or_edit_message(update, "Please send a valid PDF file or type 'done' to merge the collected PDFs.")
        return MERGE_PDF_COLLECTION

async def handle_split_pdf_document(update: Update, context: CallbackContext) -> int:
    """Handles PDF splitting process."""
    user_id = update.effective_user.id
    uploaded_file_info = context.user_data.pop('uploaded_file_info', None)
    if not uploaded_file_info or 'r2_object_key' not in uploaded_file_info:
        await send_or_edit_message(update, "Error: File information or R2 key missing. Please try uploading your file again.")
        return ConversationHandler.END

    file_id = uploaded_file_info['file_id']
    file_name = uploaded_file_info['file_name']
    mime_type = uploaded_file_info['mime_type']
    r2_object_key = uploaded_file_info['r2_object_key']

    if mime_type != 'application/pdf':
        await send_or_edit_message(update, "Oops! That doesn't look like a PDF. Please send a valid PDF file for splitting. 📄")
        return ConversationHandler.END

    context.user_data['pdf_r2_object_key'] = r2_object_key
    context.user_data['pdf_file_name'] = file_name
    context.user_data['pdf_file_id'] = file_id # Store for notification

    await send_or_edit_message(update,
        "Great! Please tell me which page numbers or ranges you'd like to split (e.g., '1-3', '5', '1,3,5-7'). "
        "You can also type /cancel if you change your mind. ↩️"
    )
    return SPLIT_PDF_INPUT_PAGES

async def handle_split_pages_input(update: Update, context: CallbackContext) -> int:
    """Handles user input for PDF page ranges to split."""
    user_id = update.effective_user.id
    page_selection_text = update.message.text.lower()
    if page_selection_text == '/cancel':
        return await cancel(update, context)

    context.user_data['page_selection'] = page_selection_text
    
    temp_dir = None
    downloaded_pdf_path = None
    try:
        r2_object_key = context.user_data.get('pdf_r2_object_key')
        pdf_file_name = context.user_data.get('pdf_file_name')

        if not r2_object_key:
            await send_or_edit_message(update, "⚠️ *Oops!* PDF file not found in storage.\n\n"
                                                "Please start over by sending me a valid PDF file first. "
                                                "You can use /start to begin again.\n\n"
                                                "Need help? Try /help for guidance. 📚",
                                                parse_mode='Markdown')
            return ConversationHandler.END

        temp_dir = tempfile.mkdtemp()
        downloaded_pdf_path = os.path.join(temp_dir, pdf_file_name)
        
        success, error_message = await download_file_from_r2(r2_object_key, downloaded_pdf_path)
        if not success:
            logger.error(f"Error downloading PDF from R2 for splitting: {error_message}")
            await send_or_edit_message(update, f"Uh oh! 😟 I couldn't access your PDF from storage: {error_message}. Please try again.")
            return ConversationHandler.END

        split_pdf_paths = split_pdf(downloaded_pdf_path, page_selection_text)
        if not split_pdf_paths:
            await send_or_edit_message(update,
            "❌ *Failed to split PDF*\n\n"
            "Possible reasons:\n"
            "• Invalid page range format\n"
            "• Pages exceed document length\n"
            "• Corrupted PDF file\n\n"
            "Please check your page ranges and try again, or send a different PDF file.\n\n"
            "Example valid formats:\n"
            "`1-5` (pages 1 through 5)\n"
            "`1,3,5` (pages 1, 3 and 5)\n"
            "`1-3,5-7` (multiple ranges)",
            parse_mode='Markdown'
        )
            return ConversationHandler.END

        output_r2_urls = []
        for i, split_path in enumerate(split_pdf_paths):
            output_file_name = f"{Path(pdf_file_name).stem}_split_{i+1}.pdf"
            output_r2_key = f"{user_id}/converted/{datetime.now().strftime('%Y%m%d%H%M%S')}_{output_file_name}"
            public_url, error = upload_file_to_r2(split_path, output_r2_key)
            if error:
                logger.error(f"Error uploading split PDF to R2: {error}")
                await send_or_edit_message(update, f"Failed to upload split PDF to storage: {error}. Please try again.")
                return ConversationHandler.END
            output_r2_urls.append(public_url)
            await send_or_edit_message(update, f"Split PDF part {i+1}: {public_url}")
            os.remove(split_path) # Clean up local split file

        user = update.effective_user
        notification_message = (
            f"✅ PDF Split Completed ✅\n\n"
            f"👤 User: {user.full_name} (ID: {user.id})\n"
            f"📁 Original File: {context.user_data.get('pdf_file_name', 'N/A')}\n"
            f"🆔 Original File ID: {context.user_data.get('pdf_file_id', 'N/A')}\n"
            f"☁️ Original R2 Key: {r2_object_key}\n"
            f"🔗 Split File URLs: {', '.join(output_r2_urls)}"
        )
        await send_admin_notification(context, notification_message)
        await send_or_edit_message(update,
            "🎉 *Success!* PDF split completed!\n\n"
            "Your files have been sent above. Here's what you can do next:\n"
            "• /splitpdf - Split another PDF\n"
            "• /mergepdf - Combine PDFs\n"
            "• /start - See all options\n\n"
            "Happy converting! 😊"
        )
        await increment_daily_conversion_count(user_id)
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error splitting PDF: {e}")
        await send_or_edit_message(update,
            "⚠️ *Something went wrong!*\n\n"
            f"Error details: `{str(e)}`\n\n"
            "Please try again or contact support if the problem persists.\n"
            "You can use /cancel to stop this operation.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    finally:
        if downloaded_pdf_path and os.path.exists(downloaded_pdf_path):
            os.remove(downloaded_pdf_path)
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Could not delete temp directory {temp_dir}: {e}")
        context.user_data.pop('pdf_r2_object_key', None)
        context.user_data.pop('pdf_file_name', None)
        context.user_data.pop('pdf_file_id', None)
        context.user_data.pop('page_selection', None)

async def handle_compression_document(update: Update, context: CallbackContext) -> int:
    """Handles file compression process."""
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

    if not (mime_type == 'application/pdf' or mime_type.startswith('image/') or \
            mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' or \
            mime_type == 'application/vnd.openxmlformats-officedocument.presentationml.presentation'):
        await send_or_edit_message(update, "Sorry, I can only compress PDFs, images, Word, and PowerPoint files.")
        return ConversationHandler.END

    try:
        temp_dir = tempfile.mkdtemp()
        input_path = os.path.join(temp_dir, file_name)
        
        success, error_message = await download_file_from_r2(r2_object_key, input_path)
        if not success:
            logger.error(f"Error downloading file from R2 for compression: {error_message}")
            await send_or_edit_message(update, f"Uh oh! 😟 I couldn't access your file from storage: {error_message}. Please try again.")
            return ConversationHandler.END

        output_path = None
        if mime_type == 'application/pdf':
            output_path = compress_pdf(input_path, None) # Pass None for output_path to let function generate it
        elif mime_type.startswith('image/'):
            output_path = compress_image(input_path, None) # Pass None for output_path to let function generate it
        elif mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            # Convert DOCX to PDF, then compress PDF
            pdf_path = os.path.join(temp_dir, Path(input_path).stem + '.pdf')
            cmd = ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", temp_dir, input_path]
            subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)
            if os.path.exists(pdf_path):
                compressed_pdf_path = compress_pdf(pdf_path, None)
                output_path = compressed_pdf_path
            else:
                raise Exception("Failed to convert DOCX to PDF for compression.")
        elif mime_type == 'application/vnd.openxmlformats-officedocument.presentationml.presentation':
            # Convert PPTX to PDF, then compress PDF
            pdf_path = os.path.join(temp_dir, Path(input_path).stem + '.pdf')
            cmd = ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", temp_dir, input_path]
            subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)
            if os.path.exists(pdf_path):
                compressed_pdf_path = compress_pdf(pdf_path, None)
                output_path = compressed_pdf_path
            else:
                raise Exception("Failed to convert PPTX to PDF for compression.")
        
        if output_path and os.path.exists(output_path):
            output_file_name = Path(output_path).name
            output_r2_key = f"{user_id}/converted/{datetime.now().strftime('%Y%m%d%H%M%S')}_{output_file_name}"
            public_url, error = upload_file_to_r2(output_path, output_r2_key)
            
            if error:
                logger.error(f"Error uploading compressed file to R2: {error}")
                await send_or_edit_message(update, f"Failed to upload compressed file to storage: {error}. Please try again.")
                return ConversationHandler.END
            
            user = update.effective_user
            notification_message = (
                f"✅ File Compression Completed ✅\n\n"
                f"👤 User: {user.full_name} (ID: {user.id})\n"
                f"📁 Original File: {file_name}\n"
                f"🆔 Original File ID: {file_id}\n"
                f"☁️ Original R2 Key: {r2_object_key}\n"
                f"🔗 Compressed File URL: {public_url}"
            )
            await send_admin_notification(context, notification_message)
            await send_or_edit_message(update, f"🎉 Success! Your file has been compressed and is available here: {public_url}")
            await increment_daily_conversion_count(user_id)
        else:
            await send_or_edit_message(update, "😔 Oh no! I couldn't compress your file. Please try again.")
        
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"File compression failed: {e}")
        await send_or_edit_message(update, f"An error occurred during compression: {e} 💔 Please try again.")
        return ConversationHandler.END
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Could not delete temp directory {temp_dir}: {e}")
        context.user_data.pop('uploaded_file_info', None)

async def handle_watermark_file_input(update: Update, context: CallbackContext) -> int:
    """Handles the file input for watermarking."""
    query = update.callback_query
    if query:
        await query.answer()
        context.user_data['watermark_type'] = query.data.replace('watermark_type_', '')
        await send_or_edit_message(update, "Please send the PDF or image file you want to watermark. 🖼️📄")
        return WATERMARK_FILE_INPUT
    
    uploaded_file_info = context.user_data.pop('uploaded_file_info', None)
    if not uploaded_file_info or 'r2_object_key' not in uploaded_file_info:
        await send_or_edit_message(update, "Error: File information or R2 key missing. Please try uploading your file again.")
        return ConversationHandler.END

    file_id = uploaded_file_info['file_id']
    file_name = uploaded_file_info['file_name']
    mime_type = uploaded_file_info['mime_type']
    r2_object_key = uploaded_file_info['r2_object_key']

    if not (mime_type == 'application/pdf' or mime_type.startswith('image/')):
        await send_or_edit_message(update, "Please send a valid PDF or image file.")
        return WATERMARK_FILE_INPUT

    context.user_data['original_file_info'] = {
        'file_id': file_id,
        'file_name': file_name,
        'mime_type': mime_type,
        'r2_object_key': r2_object_key
    }

    if context.user_data['watermark_type'] == 'text':
        await send_or_edit_message(update, "Please send the text you want to use as a watermark.")
        return WATERMARK_TEXT_INPUT
    elif context.user_data['watermark_type'] == 'image':
        await send_or_edit_message(update, "Please send the image you want to use as a watermark. (PNG with transparency is recommended)")
        return WATERMARK_IMAGE_INPUT
    return ConversationHandler.END

async def handle_watermark_type_selection(update: Update, context: CallbackContext) -> int:
    """Handles watermark type selection (text or image)."""
    query = update.callback_query
    await query.answer()
    context.user_data['watermark_type'] = query.data.replace('watermark_type_', '')
    
    if context.user_data['watermark_type'] == 'text':
        await send_or_edit_message(update, "Please send the PDF or image file you want to watermark. 🖼️📄")
        return WATERMARK_FILE_INPUT
    elif context.user_data['watermark_type'] == 'image':
        await send_or_edit_message(update, "Please send the PDF or image file you want to watermark. 🖼️📄")
        return WATERMARK_FILE_INPUT
    return ConversationHandler.END

async def handle_watermark_text_input(update: Update, context: CallbackContext) -> int:
    """Handles watermark text input and applies the watermark."""
    user_id = update.effective_user.id
    watermark_text = update.message.text
    original_file_info = context.user_data.get('original_file_info')

    if not original_file_info or 'r2_object_key' not in original_file_info:
        await send_or_edit_message(update, "Original file information or R2 key not found. Please start over.")
        return ConversationHandler.END

    file_id = original_file_info['file_id']
    file_name = original_file_info['file_name']
    mime_type = original_file_info['mime_type']
    r2_object_key = original_file_info['r2_object_key']

    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp()
        input_path = os.path.join(temp_dir, file_name)
        
        success, error_message = await download_file_from_r2(r2_object_key, input_path)
        if not success:
            logger.error(f"Error downloading original file from R2 for text watermarking: {error_message}")
            await send_or_edit_message(update, f"Uh oh! 😟 I couldn't access your original file from storage: {error_message}. Please try again.")
            return ConversationHandler.END

        output_path = os.path.join(temp_dir, f"watermarked_{file_name}")

        result_path = None
        if mime_type == 'application/pdf':
            result_path = add_text_watermark_to_pdf(input_path, watermark_text, output_path, context, user_id=user_id, file_name=file_name, file_id=file_id)
        elif mime_type.startswith('image/'):
            result_path = add_text_watermark_to_image(input_path, watermark_text, output_path, context, user_id=user_id, file_name=file_name, file_id=file_id)
        else:
            await send_or_edit_message(update, "Unsupported file type for text watermarking.")
            return ConversationHandler.END

        if result_path and os.path.exists(result_path):
            output_file_name = Path(result_path).name
            output_r2_key = f"{user_id}/converted/{datetime.now().strftime('%Y%m%d%H%M%S')}_{output_file_name}"
            public_url, error = upload_file_to_r2(result_path, output_r2_key)
            
            if error:
                logger.error(f"Error uploading watermarked file to R2: {error}")
                await send_or_edit_message(update, f"Failed to upload watermarked file to storage: {error}. Please try again.")
                return ConversationHandler.END
            
            user = update.effective_user
            notification_message = (
                f"✅ Text Watermark Completed ✅\n\n"
                f"👤 User: {user.full_name} (ID: {user.id})\n"
                f"📁 Original File: {file_name}\n"
                f"🆔 Original File ID: {file_id}\n"
                f"☁️ Original R2 Key: {r2_object_key}\n"
                f"🔗 Watermarked File URL: {public_url}"
            )
            await send_admin_notification(context, notification_message)
            await send_or_edit_message(update, f"🎉 Success! Your file has been watermarked and is available here: {public_url}")
            await increment_daily_conversion_count(user_id)
        else:
            await send_or_edit_message(update, "😔 Oh no! I couldn't add the text watermark. Please try again.")
        
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in handle_watermark_text_input: {e}")
        await send_or_edit_message(update, f"An error occurred during watermarking: {e} 💔 Please try again.")
        return ConversationHandler.END
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        context.user_data.clear()

async def handle_watermark_image_input(update: Update, context: CallbackContext) -> int:
    """Handles watermark image input and applies the watermark."""
    user_id = update.effective_user.id
    watermark_image_file_info = context.user_data.pop('uploaded_file_info', None) # This will be the watermark image
    original_file_info = context.user_data.get('original_file_info')

    if not original_file_info or 'r2_object_key' not in original_file_info or \
       not watermark_image_file_info or 'r2_object_key' not in watermark_image_file_info:
        await send_or_edit_message(update, "Original file or watermark image information/R2 key not found. Please start over.")
        return ConversationHandler.END

    original_file_id = original_file_info['file_id']
    original_file_name = original_file_info['file_name']
    original_mime_type = original_file_info['mime_type']
    original_r2_object_key = original_file_info['r2_object_key']

    watermark_file_name = watermark_image_file_info['file_name']
    watermark_mime_type = watermark_image_file_info['mime_type']
    watermark_r2_object_key = watermark_image_file_info['r2_object_key']

    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp()
        input_path = os.path.join(temp_dir, original_file_name)
        watermark_path = os.path.join(temp_dir, watermark_file_name)

        success_original, error_original = await download_file_from_r2(original_r2_object_key, input_path)
        if not success_original:
            logger.error(f"Error downloading original file from R2 for image watermarking: {error_original}")
            await send_or_edit_message(update, f"Uh oh! 😟 I couldn't access your original file from storage: {error_original}. Please try again.")
            return ConversationHandler.END

        success_watermark, error_watermark = await download_file_from_r2(watermark_r2_object_key, watermark_path)
        if not success_watermark:
            logger.error(f"Error downloading watermark image from R2: {error_watermark}")
            await send_or_edit_message(update, f"Uh oh! 😟 I couldn't access your watermark image from storage: {error_watermark}. Please try again.")
            return ConversationHandler.END

        output_path = os.path.join(temp_dir, f"watermarked_{original_file_name}")

        result_path = None
        if original_mime_type == 'application/pdf':
            result_path = add_image_watermark_to_pdf(input_path, watermark_path, output_path, context, user_id=user_id, file_name=original_file_name, file_id=original_file_id)
        elif original_mime_type.startswith('image/'):
            result_path = add_image_watermark_to_image(input_path, watermark_path, output_path, context, user_id=user_id, file_name=original_file_name, file_id=original_file_id)
        else:
            await send_or_edit_message(update, "Unsupported file type for image watermarking.")
            return ConversationHandler.END

        if result_path and os.path.exists(result_path):
            output_file_name = Path(result_path).name
            output_r2_key = f"{user_id}/converted/{datetime.now().strftime('%Y%m%d%H%M%S')}_{output_file_name}"
            public_url, error = upload_file_to_r2(result_path, output_r2_key)
            
            if error:
                logger.error(f"Error uploading watermarked file to R2: {error}")
                await send_or_edit_message(update, f"Failed to upload watermarked file to storage: {error}. Please try again.")
                return ConversationHandler.END
            
            user = update.effective_user
            notification_message = (
                f"✅ Image Watermark Completed ✅\n\n"
                f"👤 User: {user.full_name} (ID: {user.id})\n"
                f"📁 Original File: {original_file_name}\n"
                f"🆔 Original File ID: {original_file_id}\n"
                f"☁️ Original R2 Key: {original_r2_object_key}\n"
                f"🔗 Watermarked File URL: {public_url}"
            )
            await send_admin_notification(context, notification_message)
            await send_or_edit_message(update, f"🎉 Success! Your file has been watermarked and is available here: {public_url}")
            await increment_daily_conversion_count(user_id)
        else:
            await send_or_edit_message(update, "😔 Oh no! I couldn't add the image watermark. Please try again.")
        
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in handle_watermark_image_input: {e}")
        await send_or_edit_message(update, f"An error occurred during watermarking: {e} 💔 Please try again.")
        return ConversationHandler.END
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        context.user_data.clear()

async def handle_watermark_position_input(update: Update, context: CallbackContext) -> int:
    """Handles watermark position selection."""
    # This function is not directly used in the current flow as position is hardcoded or defaulted.
    # If dynamic position selection is added, this would be the handler.
    await send_or_edit_message(update, "Watermark position selection is not yet implemented.")
    return ConversationHandler.END

async def handle_url_input(update: Update, context: CallbackContext) -> int:
    """Handles URL input for conversion."""
    user_id = update.effective_user.id
    user_url = update.message.text
    temp_dir = None
    downloaded_file_path = None

    if not user_url:
        await send_or_edit_message(update, "Please provide a valid URL.")
        return ConversationHandler.END

    user_id = update.effective_user.id
    premium_status = await get_user_premium_status(user_id)
    is_premium = premium_status.get("is_premium", False)

    if not is_premium:
        daily_conversions = await get_daily_conversion_count(user_id)
        if daily_conversions >= MAX_FREE_DAILY_CONVERSIONS:
            await send_or_edit_message(update,
                f"You have reached your daily limit of {MAX_FREE_DAILY_CONVERSIONS} conversions for free users. "
                "Please consider upgrading to premium for unlimited conversions via /payment."
            )
            return ConversationHandler.END

    await send_or_edit_message(update, f"Attempting to download file from URL: {user_url}...")

    try:
        temp_dir = tempfile.mkdtemp()
        # Try to infer file name from URL or use a generic one
        file_name = os.path.basename(user_url.split('?')[0])
        if not file_name or '.' not in file_name:
            file_name = "downloaded_file" # Generic name if no extension is found

        downloaded_file_path = os.path.join(temp_dir, file_name)

        success = download_file_from_url(user_url, downloaded_file_path)

        if success and os.path.exists(downloaded_file_path):
            # Upload to R2
            r2_object_key = f"{user_id}/downloaded/{datetime.now().strftime('%Y%m%d%H%M%S')}_{file_name}"
            public_url, error = upload_file_to_r2(downloaded_file_path, r2_object_key)
            
            if error:
                logger.error(f"Error uploading downloaded file to R2: {error}")
                await send_or_edit_message(update, f"Failed to upload downloaded file to storage: {error}. Please try again.")
                return ConversationHandler.END

            await send_or_edit_message(update, f"Successfully downloaded file from URL and uploaded to storage: {public_url}")
            
            user = update.effective_user
            notification_message = (
                f"✅ File Downloaded from URL and Uploaded to R2 ✅\n\n"
                f"👤 User: {user.full_name} (ID: {user.id})\n"
                f" URL: {user_url}\n"
                f"📁 Downloaded File: {file_name}\n"
                f"☁️ R2 Key: {r2_object_key}\n"
                f"🔗 Public URL: {public_url}"
            )
            await send_admin_notification(context, notification_message)

            # Store info for subsequent conversion steps
            context.user_data['uploaded_file_info'] = {
                'file_id': 'url_downloaded', # Placeholder file_id
                'file_name': file_name,
                'mime_type': 'application/octet-stream', # Generic mime type, could be improved with mimetypes.guess_type
                'file_size': os.path.getsize(downloaded_file_path),
                'r2_object_key': r2_object_key,
                'public_url': public_url
            }
            await send_or_edit_message(update, "File downloaded and stored. You can now choose a conversion option from the main menu.")
            await increment_daily_conversion_count(user_id)
            return ConversationHandler.END
        else:
            await send_or_edit_message(update, "😔 Failed to download the file from the provided URL. Please check the URL and try again.")
            return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error handling URL input: {e}")
        await send_or_edit_message(update, f"An error occurred while processing your URL: {e} 💔 Please try again.")
        return ConversationHandler.END
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Could not delete temp directory {temp_dir}: {e}")
        context.user_data.pop('conversion_type', None) # Clear conversion type after URL handling

# Specialized flow starters
async def ocr_flow_start(update: Update, context: CallbackContext) -> int:
    """Starts the OCR conversation flow."""
    context.user_data['conversion_type'] = 'ocr'
    await send_or_edit_message(update,
        "📄 Please send me the image or PDF file you'd like to extract text from. "
        "For best results, use clear, high-quality images with printed text."
    )
    return OCR_PROCESSING

async def merge_pdf_flow_start(update: Update, context: CallbackContext) -> int:
    """Starts the PDF merging conversation flow."""
    context.user_data['conversion_type'] = 'merge_pdf'
    await send_or_edit_message(update,
        "➕ Please send me the PDF files you'd like to merge, one at a time. "
        "Send all the files first, then type 'done' when you're finished."
    )
    return MERGE_PDF_COLLECTION

async def split_pdf_flow_start(update: Update, context: CallbackContext) -> int:
    """Starts the PDF splitting conversation flow."""
    context.user_data['conversion_type'] = 'split_pdf'
    await send_or_edit_message(update,
        "✂️ Please send me the PDF file you'd like to split. "
        "After sending the file, I'll ask you how you'd like to split it."
    )
    return SPLIT_PDF_INPUT_PAGES

async def compress_flow_start(update: Update, context: CallbackContext) -> int:
    """Starts the file compression conversation flow."""
    context.user_data['conversion_type'] = 'compress'
    await send_or_edit_message(update,
        "🗜️ Please send me the PDF, image, Word, or PowerPoint file you'd like to compress. "
        "I'll optimize it to reduce the file size while maintaining reasonable quality."
    )
    return COMPRESS_FILE_PROCESSING

async def watermark_flow_start(update: Update, context: CallbackContext) -> int:
    """Starts the watermarking conversation flow."""
    context.user_data['conversion_type'] = 'watermark'
    keyboard = [
        [InlineKeyboardButton("Text Watermark", callback_data='watermark_type_text')],
        [InlineKeyboardButton("Image Watermark", callback_data='watermark_type_image')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_or_edit_message(update,
        "✍️ What type of watermark would you like to add?",
        reply_markup=reply_markup
    )
    return WATERMARK_FILE_INPUT

async def url_conversion_flow_start(update: Update, context: CallbackContext) -> int:
    """Starts the URL-based conversion flow."""
    context.user_data['conversion_type'] = 'url_conversion'
    await send_or_edit_message(update,
        "🔗 Please send me the URL of the file you'd like to convert. "
        "I'll download it and then we can proceed with the conversion."
    )
    return URL_INPUT

# Document handlers
async def handle_ocr_document(update: Update, context: CallbackContext) -> int:
    """Handles OCR processing of documents."""
    # Implementation would go here
    pass

async def handle_merge_pdf_documents(update: Update, context: CallbackContext) -> int:
    """Handles PDF merging process."""
    # Implementation would go here
    pass

async def handle_split_pdf_document(update: Update, context: CallbackContext) -> int:
    """Handles PDF splitting process."""
    # Implementation would go here
    pass

async def handle_split_pages_input(update: Update, context: CallbackContext) -> int:
    """Handles user input for PDF page ranges to split."""
    page_selection_text = update.message.text.lower()
    if page_selection_text == '/cancel':
        return await cancel(update, context)

    context.user_data['page_selection'] = page_selection_text
    
    try:
        pdf_path = context.user_data.get('pdf_path')
        if not pdf_path:
            await send_or_edit_message(update,
            "⚠️ *Oops!* PDF file not found.\n\n"
            "Please start over by sending me a valid PDF file first. "
            "You can use /start to begin again.\n\n"
            "Need help? Try /help for guidance. 📚",
            parse_mode='Markdown'
        )
            return ConversationHandler.END

        split_pdf_paths = split_pdf(pdf_path, page_selection_text)
        if not split_pdf_paths:
            await send_or_edit_message(update,
            "❌ *Failed to split PDF*\n\n"
            "Possible reasons:\n"
            "• Invalid page range format\n"
            "• Pages exceed document length\n"
            "• Corrupted PDF file\n\n"
            "Please check your page ranges and try again, or send a different PDF file.\n\n"
            "Example valid formats:\n"
            "`1-5` (pages 1 through 5)\n"
            "`1,3,5` (pages 1, 3 and 5)\n"
            "`1-3,5-7` (multiple ranges)",
            parse_mode='Markdown'
        )
            return ConversationHandler.END

        for i, split_path in enumerate(split_pdf_paths):
            with open(split_path, 'rb') as f:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    caption=f"Split PDF part {i+1}"
                )
            os.remove(split_path)

        await send_or_edit_message(update,
            "🎉 *Success!* PDF split completed!\n\n"
            "Your files have been sent above. Here's what you can do next:\n"
            "• /splitpdf - Split another PDF\n"
            "• /mergepdf - Combine PDFs\n"
            "• /start - See all options\n\n"
            "Happy converting! 😊"
        )
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error splitting PDF: {e}")
        await send_or_edit_message(update,
            "⚠️ *Something went wrong!*\n\n"
            f"Error details: `{str(e)}`\n\n"
            "Please try again or contact support if the problem persists.\n"
            "You can use /cancel to stop this operation.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

async def handle_compression_document(update: Update, context: CallbackContext) -> int:
    """Handles file compression process."""
    temp_dir = None
    try:
        document = update.message.document
        if not document:
            await send_or_edit_message(update, "Please send a document to compress.")
            return ConversationHandler.END

        file_id = document.file_id
        file_name = document.file_name
        mime_type = document.mime_type

        temp_dir = tempfile.mkdtemp()
        input_path = os.path.join(temp_dir, file_name)
        await context.bot.get_file(file_id).download_to_drive(input_path)

        output_path = None
        if mime_type == 'application/pdf':
            output_path = compress_pdf(input_path)
        elif mime_type.startswith('image/'):
            output_path = compress_image(input_path)
        elif mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            # Convert DOCX to PDF, then compress PDF
            pdf_path = os.path.join(temp_dir, Path(input_path).stem + '.pdf')
            subprocess.run(f"libreoffice --headless --convert-to pdf --outdir {temp_dir} {input_path}", shell=True, check=True)
            if os.path.exists(pdf_path):
                compressed_pdf_path = compress_pdf(pdf_path)
                # For now, we'll send the compressed PDF. If the user wants DOCX back,
                # we'd need to convert PDF back to DOCX, which might lose formatting.
                output_path = compressed_pdf_path
            else:
                raise Exception("Failed to convert DOCX to PDF for compression.")
        elif mime_type == 'application/vnd.openxmlformats-officedocument.presentationml.presentation':
            # Convert PPTX to PDF, then compress PDF
            pdf_path = os.path.join(temp_dir, Path(input_path).stem + '.pdf')
            subprocess.run(f"libreoffice --headless --convert-to pdf --outdir {temp_dir} {input_path}", shell=True, check=True)
            if os.path.exists(pdf_path):
                compressed_pdf_path = compress_pdf(pdf_path)
                output_path = compressed_pdf_path
            else:
                raise Exception("Failed to convert PPTX to PDF for compression.")
        else:
            await send_or_edit_message(update, "Sorry, I can only compress PDFs, images, Word, and PowerPoint files.")
            return ConversationHandler.END

        if output_path and os.path.exists(output_path):
            with open(output_path, 'rb') as f:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    caption=f"Here's your compressed file ({Path(output_path).suffix})!"
                )
            await send_or_edit_message(update, "🎉 Success! Your file has been compressed and sent!")
        else:
            await send_or_edit_message(update, "😔 Oh no! I couldn't compress your file. Please try again.")
        
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"File compression failed: {e}")
        await update.message.reply_text(f"An error occurred during compression: {e} 💔 Please try again.")
        return ConversationHandler.END
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Could not delete temp directory {temp_dir}: {e}")

async def handle_watermark_file_input(update: Update, context: CallbackContext) -> int:
    """Handles watermark file input."""
    # Implementation would go here
    pass

async def handle_watermark_type_selection(update: Update, context: CallbackContext) -> int:
    """Handles watermark type selection."""
    # Implementation would go here
    pass

async def handle_watermark_text_input(update: Update, context: CallbackContext) -> int:
    """Handles watermark text input."""
    # Implementation would go here
    pass

async def handle_watermark_image_input(update: Update, context: CallbackContext) -> int:
    """Handles watermark image input."""
    # Implementation would go here
    pass

async def handle_watermark_position_input(update: Update, context: CallbackContext) -> int:
    """Handles watermark position selection."""
    # Implementation would go here
    pass

async def handle_url_input(update: Update, context: CallbackContext) -> int:
    """Handles URL input for conversion."""
    user_url = update.message.text
    temp_dir = None
    downloaded_file_path = None

    if not user_url:
        await send_or_edit_message(update, "Please provide a valid URL.")
        return ConversationHandler.END

    await send_or_edit_message(update, f"Attempting to download file from URL: {user_url}...")

    try:
        temp_dir = tempfile.mkdtemp()
        # Try to infer file name from URL or use a generic one
        file_name = os.path.basename(user_url.split('?')[0])
        if not file_name or '.' not in file_name:
            file_name = "downloaded_file" # Generic name if no extension is found

        downloaded_file_path = os.path.join(temp_dir, file_name)

        success = download_file_from_url(user_url, downloaded_file_path)

        if success and os.path.exists(downloaded_file_path):
            await send_or_edit_message(update, f"Successfully downloaded file to: {file_name}")
            
            user = update.effective_user
            notification_message = (
                f"✅ File Downloaded from URL ✅\n\n"
                f"👤 User: {user.full_name} (ID: {user.id})\n"
                f"🔗 URL: {user_url}\n"
                f"📁 Downloaded File: {file_name}"
            )
            await send_admin_notification(context, notification_message)

            # Here you would typically proceed with conversion options for the downloaded file
            # For now, we just notify and end the conversation.
            await send_or_edit_message(update, "File downloaded. You can now choose a conversion option from the main menu.")
            return ConversationHandler.END
        else:
            await send_or_edit_message(update, "😔 Failed to download the file from the provided URL. Please check the URL and try again.")
            return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error handling URL input: {e}")
        await send_or_edit_message(update, f"An error occurred while processing your URL: {e} 💔 Please try again.")
        return ConversationHandler.END
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Could not delete temp directory {temp_dir}: {e}")
