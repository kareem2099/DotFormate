import logging
from datetime import datetime # Import datetime for timestamp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler
from database import save_user_info, get_user # Import get_user
from constants import MAIN_MENU
from notification_utils import send_notification_to_channel
from user_content_logger import log_incoming_message # Import the new user content logger

logger = logging.getLogger(__name__)

async def send_or_edit_message(update: Update, text: str, reply_markup: InlineKeyboardMarkup = None, parse_mode: str = None):
    """Sends a new message or edits an existing one based on the update type, returning the sent/edited message."""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        return await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    else:
        return await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)

async def start(update: Update, context: CallbackContext) -> int:
    """Send a welcome message and main menu when the command /start is issued or 'Back to Main Menu' is selected."""
    user = update.effective_user
    chat_id = update.effective_chat.id # Get the chat_id
    is_new_user = await save_user_info(
        user_id=user.id,
        chat_id=chat_id, # Pass chat_id to save_user_info
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    if is_new_user:
        notification_message = (
            f"🎉 *New User Joined!* 🎉\n\n"
            f"👤 User: {user.first_name} {user.last_name or ''} (ID: {user.id})\n"
            f"@{user.username or 'N/A'}\n"
            f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        await send_notification_to_channel(notification_message, parse_mode='Markdown')
        logger.info(f"New user notification sent for user ID: {user.id}")

    keyboard = [
        [InlineKeyboardButton("PDF Conversions", callback_data='pdf_conversions_menu')],
        [InlineKeyboardButton("PNG Conversions", callback_data='png_conversions_menu')],
        [InlineKeyboardButton("JPG Conversions", callback_data='jpg_conversions_menu')],
        [InlineKeyboardButton("WEBP Conversions", callback_data='webp_conversions_menu')],
        [InlineKeyboardButton("TIFF Conversions", callback_data='tiff_conversions_menu')],
        [InlineKeyboardButton("Word Conversions", callback_data='docx_conversions_menu')],
        [InlineKeyboardButton("PowerPoint Conversions", callback_data='pptx_conversions_menu')],
        [InlineKeyboardButton("Help", callback_data='help_command')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_message = '👋 Hello there! I\'m your friendly file converter bot. Choose a file type below to get started with your conversions! 👇'
    await send_or_edit_message(update, welcome_message, reply_markup=reply_markup)
    
    logger.info("Start command/callback received. Entering MAIN_MENU state.")
    return MAIN_MENU

async def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued or 'Help' is selected from menu."""
    logger.info("Help command/callback received.")
    help_text = (
        'Need a hand? I\'m here to help! 🤖\n\n'
        'Here are the commands you can use:\n'
        '✨ /start - Brings up the main menu to start a new conversion.\n'
        '❓ /help - Shows this helpful message again.\n'
        '📄 /ocr - Extract text from images or PDFs.\n'
        '➕ /mergepdf - Combine multiple PDFs into one.\n'
        '✂️ /splitpdf - Split a PDF into multiple files.\n'
        '🗜️ /compress - Reduce the file size of PDFs or images.\n'
        '✍️ /watermark - Add text or image watermarks to files.\n'
        '🔗 /url - Convert files directly from a URL.\n'
        '❌ /cancel - Stops the current operation.\n\n'
        'Just follow the simple on-screen instructions after picking a conversion type. Happy converting! 😊'
    )
    await send_or_edit_message(update, help_text)

async def cancel(update: Update, context: CallbackContext) -> int:
    """Cancels and ends the conversation."""
    user = update.effective_user
    logger.info("User %s canceled the conversation.", user.first_name)
    await send_or_edit_message(update, "Operation cancelled. Type /start to begin again. 👋")
    context.user_data.clear() # Clear user data for a clean slate
    return ConversationHandler.END

async def _get_file_info_from_update(update: Update, context: CallbackContext):
    """Helper function to extract file info (id, name, mime_type, size) from update or user_data."""
    file_id = None
    file_name = None
    mime_type = None
    file_size = None # Initialize file_size
    user_id = update.effective_user.id
    message_id = update.effective_message.message_id
    text_content = update.effective_message.text

    # Prioritize newly uploaded files from the message
    if update.message and update.message.document:
        file_id = update.message.document.file_id
        file_name = update.message.document.file_name
        mime_type = update.message.document.mime_type
        file_size = update.message.document.file_size # Get file size for documents
        logger.info(f"Processing newly uploaded document: {file_name}, MIME type: {mime_type}, Size: {file_size} bytes")
        await log_incoming_message(
            user_id=user_id,
            message_id=message_id,
            message_type="document",
            text_content=text_content,
            file_id=file_id,
            file_size=file_size,
            file_name=file_name,
            context=context
        )
    elif update.message and update.message.photo:
        # For photos, Telegram sends multiple sizes; pick the largest one
        largest_photo = update.message.photo[-1]
        file_id = largest_photo.file_id
        file_name = f"image_{file_id}.jpeg" # Assuming JPEG for photos, can be adjusted
        mime_type = "image/jpeg"
        file_size = largest_photo.file_size # Get file size for photos
        logger.info(f"Processing newly uploaded photo: {file_name}, MIME type: {mime_type}, Size: {file_size} bytes")
        await log_incoming_message(
            user_id=user_id,
            message_id=message_id,
            message_type="photo",
            text_content=text_content,
            file_id=file_id,
            file_size=file_size,
            file_name=file_name,
            context=context
        )
    elif update.message and update.message.text:
        logger.info(f"Processing incoming text message from user {user_id}: {text_content}")
        await log_incoming_message(
            user_id=user_id,
            message_id=message_id,
            message_type="text",
            text_content=text_content
        )
    elif 'uploaded_file_info' in context.user_data:
        # If no new file in message, check for pre-uploaded file info in user_data
        uploaded_file_info = context.user_data['uploaded_file_info']
        file_id = uploaded_file_info['file_id']
        file_name = uploaded_file_info['file_name']
        mime_type = uploaded_file_info['mime_type']
        file_size = uploaded_file_info.get('file_size') # Retrieve file size if present
        logger.info(f"Processing pre-stored file from user_data: {file_name}, MIME type: {mime_type}, Size: {file_size} bytes")
        # Note: For pre-stored files, they are typically already handled by the initial upload handler.
        # We might not need to log them again here as "incoming" if they were already logged when first received.
        # This part depends on the exact flow of your bot. For now, I'll assume this is a re-processing step
        # and won't log it as a new incoming message to avoid duplicates.
    
    return file_id, file_name, mime_type, file_size

async def balance_command(update: Update, context: CallbackContext) -> None:
    """Handles the /balance command, showing the user's referral balance."""
    user_id = update.effective_user.id
    user = await get_user(user_id)

    if not user:
        await update.message.reply_text("I couldn't find your user data. Please try /start first.")
        return

    referral_balance = user.get('referral_balance', 0.0)
    message_text = (
        f"💰 Your current referral balance is: *${referral_balance:.2f}*.\n\n"
        "Keep inviting friends to earn more rewards!"
    )
    await update.message.reply_text(message_text, parse_mode='Markdown')
