import os
import logging
import tempfile
import subprocess
import shutil # Import shutil for directory removal
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler, filters
import fitz # Import fitz for PDF processing
from database import save_user_info
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

logger = logging.getLogger(__name__)

# States for the conversation handler
from constants import (
    MAIN_MENU, SELECT_CONVERSION_TYPE, SELECT_PAGES, SELECT_OUTPUT_FORMAT, SELECT_IMAGE_FORMAT,
    OCR_PROCESSING, MERGE_PDF_COLLECTION, SPLIT_PDF_INPUT_PAGES, COMPRESSION_PROCESSING,
    WATERMARK_FILE_INPUT, WATERMARK_TEXT_INPUT, WATERMARK_IMAGE_INPUT, WATERMARK_POSITION_INPUT,
    URL_INPUT, COMPRESS_FILE_PROCESSING
)

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
    temp_dir = None
    file_id = None
    file_name = None
    mime_type = None

    try:
        document = update.message.document
        photo = update.message.photo
        
        if document:
            file_id = document.file_id
            file_name = document.file_name
            mime_type = document.mime_type
        elif photo:
            # Get the largest photo size
            file_id = photo[-1].file_id
            file_name = f"photo_{file_id}.jpg" # Assign a generic name for photos
            mime_type = "image/jpeg" # Assume JPEG for simplicity, can be refined

        if not file_id:
            await send_or_edit_message(update, "Please send an image or PDF file for OCR.")
            return ConversationHandler.END

        await send_or_edit_message(update, "🔍 Performing OCR on your file... This might take a moment.")

        temp_dir = tempfile.mkdtemp()
        input_path = os.path.join(temp_dir, file_name)
        await context.bot.get_file(file_id).download_to_drive(input_path)

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
        else:
            await send_or_edit_message(update, "Sorry, I can only perform OCR on images and PDFs.")
            return ConversationHandler.END

        if extracted_text.strip():
            await send_or_edit_message(update, f"📝 *OCR Result:*\n\n```\n{extracted_text.strip()}\n```", parse_mode='Markdown')
            user = update.effective_user
            notification_message = (
                f"✅ OCR Conversion Completed ✅\n\n"
                f"👤 User: {user.full_name} (ID: {user.id})\n"
                f"📁 File: {file_name}\n"
                f"🆔 File ID: {file_id}"
            )
            await send_admin_notification(context, notification_message)
            await send_or_edit_message(update, "🎉 Success! Text extracted and sent!")
        else:
            await send_or_edit_message(update, "😔 No text could be extracted from the file. Please try with a clearer image or PDF.")
        
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error during OCR processing: {e}")
        await send_or_edit_message(update, f"An error occurred during OCR: {e} 💔 Please try again.")
        return ConversationHandler.END
    finally:
        if file_id and input_path and os.path.exists(input_path):
            os.remove(input_path)
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Could not delete temp directory {temp_dir}: {e}")

async def handle_merge_pdf_documents(update: Update, context: CallbackContext) -> int:
    """Handles PDF merging process."""
    user_data = context.user_data
    
    if 'pdf_paths_to_merge' not in user_data:
        user_data['pdf_paths_to_merge'] = []
        user_data['pdf_names_to_merge'] = []
        user_data['temp_dirs_to_clean'] = [] # To keep track of temp directories for cleanup

    document = update.message.document
    if not document or document.mime_type != 'application/pdf':
        if update.message.text and update.message.text.lower() == 'done':
            if not user_data['pdf_paths_to_merge']:
                await send_or_edit_message(update, "Please send at least one PDF file before typing 'done'.")
                return MERGE_PDF_COLLECTION
            
            await send_or_edit_message(update, "Merging your PDFs... This might take a moment. ⏳")
            merged_pdf_path = None
            try:
                merged_pdf_path = merge_pdfs(user_data['pdf_paths_to_merge'])
                
                if merged_pdf_path and os.path.exists(merged_pdf_path):
                    merged_file_name = f"merged_pdfs_{update.effective_user.id}.pdf"
                    with open(merged_pdf_path, 'rb') as f:
                        await context.bot.send_document(
                            chat_id=update.effective_chat.id,
                            document=f,
                            filename=merged_file_name,
                            caption="🎉 Here's your merged PDF file!"
                        )
                    user = update.effective_user
                    notification_message = (
                        f"✅ PDF Merge Completed ✅\n\n"
                        f"👤 User: {user.full_name} (ID: {user.id})\n"
                        f"📁 Merged Files: {', '.join(user_data['pdf_names_to_merge'])}\n"
                        f"🆔 Merged File Name: {merged_file_name}" # No file_id for newly created file
                    )
                    await send_admin_notification(context, notification_message)
                    await send_or_edit_message(update, "✨ Your PDFs have been successfully merged and sent!")
                else:
                    await send_or_edit_message(update, "😔 Oh no! I couldn't merge your PDFs. Please try again.")
                
                return ConversationHandler.END
            except Exception as e:
                logger.error(f"Error merging PDFs: {e}")
                await send_or_edit_message(update, f"An error occurred during PDF merging: {e} 💔 Please try again.")
                return ConversationHandler.END
            finally:
                # Clean up all temporary files and directories
                if merged_pdf_path and os.path.exists(merged_pdf_path):
                    os.remove(merged_pdf_path)
                for path in user_data['pdf_paths_to_merge']:
                    if os.path.exists(path):
                        os.remove(path)
                for temp_dir in user_data['temp_dirs_to_clean']:
                    if os.path.exists(temp_dir):
                        try:
                            shutil.rmtree(temp_dir)
                        except Exception as e:
                            logger.warning(f"Could not delete temp directory {temp_dir}: {e}")
                user_data.pop('pdf_paths_to_merge', None)
                user_data.pop('pdf_names_to_merge', None)
                user_data.pop('temp_dirs_to_clean', None)
        else:
            await send_or_edit_message(update, "Please send a valid PDF file or type 'done' to merge the collected PDFs.")
            return MERGE_PDF_COLLECTION

    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, document.file_name)
    await document.get_file().download_to_drive(file_path)
    
    user_data['pdf_paths_to_merge'].append(file_path)
    user_data['pdf_names_to_merge'].append(document.file_name)
    user_data['temp_dirs_to_clean'].append(temp_dir) # Add this temp dir to cleanup list

    await send_or_edit_message(update, f"Received '{document.file_name}'. Send another PDF or type 'done' to merge.")
    return MERGE_PDF_COLLECTION

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

        user = update.effective_user
        notification_message = (
            f"✅ PDF Split Completed ✅\n\n"
            f"👤 User: {user.full_name} (ID: {user.id})\n"
            f"📁 File: {context.user_data.get('pdf_file_name', 'N/A')}\n" # Assuming pdf_file_name is stored
            f"🆔 File ID: {context.user_data.get('pdf_file_id', 'N/A')}" # Assuming pdf_file_id is stored
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
        if 'pdf_path' in context.user_data and context.user_data['pdf_path'] and os.path.exists(context.user_data['pdf_path']):
            os.remove(context.user_data['pdf_path'])
            del context.user_data['pdf_path'] # Clean up user_data

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
            user = update.effective_user
            notification_message = (
                f"✅ File Compression Completed ✅\n\n"
                f"👤 User: {user.full_name} (ID: {user.id})\n"
                f"📁 File: {file_name}\n"
                f"🆔 File ID: {file_id}"
            )
            await send_admin_notification(context, notification_message)
            await send_or_edit_message(update, "🎉 Success! Your file has been compressed and sent!")
        else:
            await send_or_edit_message(update, "😔 Oh no! I couldn't compress your file. Please try again.")
        
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"File compression failed: {e}")
        await send_or_edit_message(update, f"An error occurred during compression: {e} 💔 Please try again.")
        return ConversationHandler.END
    finally:
        if 'pdf_path' in locals() and pdf_path and os.path.exists(pdf_path):
            os.remove(pdf_path)
        if 'input_path' in locals() and input_path and os.path.exists(input_path):
            os.remove(input_path) # Ensure original downloaded file is removed
        if 'temp_dir' in locals() and temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Could not delete temp directory {temp_dir}: {e}")

async def handle_watermark_file_input(update: Update, context: CallbackContext) -> int:
    """Handles the file input for watermarking."""
    query = update.callback_query
    if query:
        await query.answer()
        context.user_data['watermark_type'] = query.data.replace('watermark_type_', '')
        await send_or_edit_message(update, "Please send the PDF or image file you want to watermark. 🖼️📄")
        return WATERMARK_FILE_INPUT
    
    document = update.message.document
    photo = update.message.photo

    file_id = None
    file_name = None
    mime_type = None

    if document:
        file_id = document.file_id
        file_name = document.file_name
        mime_type = document.mime_type
    elif photo:
        file_id = photo[-1].file_id
        file_name = f"photo_{file_id}.jpg"
        mime_type = "image/jpeg"

    if not file_id:
        await send_or_edit_message(update, "Please send a valid PDF or image file.")
        return WATERMARK_FILE_INPUT

    context.user_data['original_file_info'] = {
        'file_id': file_id,
        'file_name': file_name,
        'mime_type': mime_type
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
    watermark_text = update.message.text
    original_file_info = context.user_data.get('original_file_info')

    if not original_file_info:
        await send_or_edit_message(update, "Original file information not found. Please start over.")
        return ConversationHandler.END

    file_id = original_file_info['file_id']
    file_name = original_file_info['file_name']
    mime_type = original_file_info['mime_type']
    user_id = update.effective_user.id

    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp()
        input_path = os.path.join(temp_dir, file_name)
        await context.bot.get_file(file_id).download_to_drive(input_path)

        output_path = os.path.join(temp_dir, f"watermarked_{file_name}")

        if mime_type == 'application/pdf':
            result_path = add_text_watermark_to_pdf(input_path, watermark_text, output_path, context, user_id=user_id, file_name=file_name, file_id=file_id)
        elif mime_type.startswith('image/'):
            result_path = add_text_watermark_to_image(input_path, watermark_text, output_path, context, user_id=user_id, file_name=file_name, file_id=file_id)
        else:
            await send_or_edit_message(update, "Unsupported file type for text watermarking.")
            return ConversationHandler.END

        if result_path and os.path.exists(result_path):
            with open(result_path, 'rb') as f:
                await context.bot.send_document(chat_id=update.effective_chat.id, document=f, caption="Here's your watermarked file!")
            await send_or_edit_message(update, "🎉 Success! Your file has been watermarked and sent!")
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
    watermark_image_file = update.message.document or update.message.photo[-1]
    original_file_info = context.user_data.get('original_file_info')

    if not original_file_info or not watermark_image_file:
        await send_or_edit_message(update, "Original file or watermark image not found. Please start over.")
        return ConversationHandler.END

    original_file_id = original_file_info['file_id']
    original_file_name = original_file_info['file_name']
    original_mime_type = original_file_info['mime_type']
    user_id = update.effective_user.id

    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp()
        input_path = os.path.join(temp_dir, original_file_name)
        await context.bot.get_file(original_file_id).download_to_drive(input_path)

        watermark_path = os.path.join(temp_dir, watermark_image_file.file_name or f"watermark_{watermark_image_file.file_id}.png")
        await context.bot.get_file(watermark_image_file.file_id).download_to_drive(watermark_path)

        output_path = os.path.join(temp_dir, f"watermarked_{original_file_name}")

        if original_mime_type == 'application/pdf':
            result_path = add_image_watermark_to_pdf(input_path, watermark_path, output_path, context, user_id=user_id, file_name=original_file_name, file_id=original_file_id)
        elif original_mime_type.startswith('image/'):
            result_path = add_image_watermark_to_image(input_path, watermark_path, output_path, context, user_id=user_id, file_name=original_file_name, file_id=original_file_id)
        else:
            await send_or_edit_message(update, "Unsupported file type for image watermarking.")
            return ConversationHandler.END

        if result_path and os.path.exists(result_path):
            with open(result_path, 'rb') as f:
                await context.bot.send_document(chat_id=update.effective_chat.id, document=f, caption="Here's your watermarked file!")
            await send_or_edit_message(update, "🎉 Success! Your file has been watermarked and sent!")
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
