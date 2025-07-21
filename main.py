import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters, CallbackQueryHandler, CallbackContext

# Load environment variables from .env file
load_dotenv()

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Import states from constants
from constants import (
    MAIN_MENU, SELECT_CONVERSION_TYPE, SELECT_PAGES, SELECT_OUTPUT_FORMAT, SELECT_IMAGE_FORMAT,
    OCR_PROCESSING, MERGE_PDF_COLLECTION, SPLIT_PDF_INPUT_PAGES, COMPRESSION_PROCESSING,
    WATERMARK_FILE_INPUT, WATERMARK_TEXT_INPUT, WATERMARK_IMAGE_INPUT, WATERMARK_POSITION_INPUT,
    URL_INPUT, COMPRESS_FILE_PROCESSING, RESIZE_INPUT, ROTATE_INPUT, PAYMENT_INPUT,
    SELECT_PAYMENT_OPTION, SELECT_PAYMENT_METHOD
)

# Import handlers from various modules
from utility_handlers import start, help_command, cancel, balance_command # Centralized utility functions
from referral_system import handle_referral_start, referral_command
from paypal_integration import (
    handle_payment_command, handle_payment_option_selection, handle_payment_method_selection,
    paypal_return_handler, paypal_cancel_handler, handle_payment_confirmation_file # Import new handler
)
from file_handlers import (
    handle_document_type,
    select_pages, select_output_format, handle_specific_pages_input,
    resize_image_start, handle_resize_input, rotate_image_start, handle_rotate_input
)
from conversation_handlers import (
    ocr_flow_start, handle_ocr_document,
    merge_pdf_flow_start, handle_merge_pdf_documents,
    split_pdf_flow_start, handle_split_pdf_document, handle_split_pages_input,
    compress_flow_start, handle_compression_document,
    watermark_flow_start, handle_watermark_file_input, handle_watermark_type_selection,
    handle_watermark_text_input, handle_watermark_image_input, handle_watermark_position_input,
    url_conversion_flow_start, handle_url_input
)
from admin_handlers import is_admin # Keep is_admin if still used, remove send_admin_notification
from menu_handlers import (
    pdf_conversions_menu, png_conversions_menu, jpg_conversions_menu,
    webp_conversions_menu, tiff_conversions_menu, docx_conversions_menu, pptx_conversions_menu, handle_menu_callbacks,
    pdf_to_images_flow_start, png_to_pdf_flow_start, png_to_image_flow_start,
    jpg_to_pdf_flow_start, jpg_to_image_flow_start, webp_to_pdf_flow_start,
    webp_to_image_flow_start, tiff_to_pdf_flow_start, tiff_to_image_flow_start
)
from commands import ( # Import all command handlers from commands.py
    set_bot_commands, admin_command_example,
    handle_users_command, handle_logs_command, handle_backup_command, handle_maintenance_command, handle_pending_payments_command
)

# Import document converters
from docx_converter import handle_docx_to_pdf, handle_pdf_to_docx
from pptx_converter import handle_pptx_to_pdf, handle_pdf_to_pptx
from r2_utils import delete_file_from_r2
from database import get_old_r2_files, mark_r2_file_as_deleted
from datetime import datetime, timedelta
from notification_utils import send_notification_to_channel # Import for notifications
import traceback # Import traceback for detailed error logging


async def daily_r2_cleanup_job(context: CallbackContext):
    """
    Job function to periodically clean up old files from R2 storage.
    It queries the database for files older than 1 week and deletes them from R2.
    """
    logger.info("Starting daily R2 cleanup job.")
    
    # Define cutoff time (e.g., 1 week ago)
    cutoff_time = datetime.utcnow() - timedelta(weeks=1)
    
    files_to_delete_metadata = await get_old_r2_files(cutoff_time)
    
    if not files_to_delete_metadata:
        logger.info("No old R2 files found for cleanup.")
        return

    logger.info(f"Found {len(files_to_delete_metadata)} old R2 files to delete.")
    
    for file_meta in files_to_delete_metadata:
        r2_object_key = file_meta['r2_object_key']
        user_id = file_meta['user_id']
        
        success, error_message = delete_file_from_r2(r2_object_key)
        
        if success:
            await mark_r2_file_as_deleted(r2_object_key)
            logger.info(f"Successfully deleted R2 object '{r2_object_key}' and marked in DB for user {user_id}.")
            # Optionally, notify the user that their file has been deleted
            # try:
            #     await context.bot.send_message(chat_id=user_id, text=f"Your file '{r2_object_key.split('/')[-1]}' has been removed from storage as per our 1-week policy.")
            # except Exception as e:
            #     logger.warning(f"Could not send R2 cleanup notification to user {user_id}: {e}")
        else:
            logger.error(f"Failed to delete R2 object '{r2_object_key}': {error_message}")
            # Notify about persistent deletion failures
            notification_message = (
                f"⚠️ *R2 Cleanup Failure!* ⚠️\n\n"
                f"🚨 Failed to delete R2 object: `{r2_object_key}`\n"
                f"Error: {error_message}"
            )
            await send_notification_to_channel(notification_message, parse_mode='Markdown')

    logger.info("R2 cleanup job finished.")


async def start_command_handler(update: Update, context: CallbackContext) -> int:
    """Handles the /start command, including referral logic."""
    # First, try to handle referral. If it returns a state, the conversation continues there.
    # Otherwise, proceed with the regular start command.
    referral_result = await handle_referral_start(update, context)
    if referral_result is not None: # handle_referral_start might return a state or ConversationHandler.END
        return referral_result
    
    # If referral_result is None, it means handle_referral_start didn't take over the conversation,
    # so proceed with the regular start command.
    return await start(update, context)

def main():
    """Start the bot."""
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not found in .env file. Please set it and restart the bot.")
        return
    logger.info("TELEGRAM_BOT_TOKEN loaded successfully.")

    # Build the Application
    logger.info("Building Telegram Application...")
    application = Application.builder().token(telegram_bot_token).build()
    logger.info("Telegram Application built successfully.")

    # Add the error handler
    application.add_error_handler(error_handler)

    # Add command handlers
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("referral", referral_command))
    application.add_handler(CommandHandler("balance", balance_command)) # New balance command
    application.add_handler(CommandHandler("payment", handle_payment_command)) # New payment command
    
    # Admin command handlers with filter
    # Get admin user IDs from environment variable and create a filter
    admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
    admin_ids = [int(uid.strip()) for uid in admin_ids_str.split(',') if uid.strip().isdigit()]
    admin_filter = filters.User(user_id=admin_ids)
    
    # Admin commands
    application.add_handler(CommandHandler("admin", admin_command_example, filters=admin_filter))
    application.add_handler(CommandHandler("stats", 
        lambda u,c: u.message.reply_text("📊 Bot statistics feature coming soon!"),
        filters=admin_filter))
    application.add_handler(CommandHandler("broadcast", 
        lambda u,c: u.message.reply_text("📢 Broadcast feature coming soon!"),
        filters=admin_filter))
    application.add_handler(CommandHandler("userswitch", 
        lambda u,c: set_bot_commands(c.application, None),
        filters=admin_filter))
    application.add_handler(CommandHandler("users", handle_users_command, filters=admin_filter))
    application.add_handler(CommandHandler("logs", handle_logs_command, filters=admin_filter))
    application.add_handler(CommandHandler("backup", handle_backup_command, filters=admin_filter))
    application.add_handler(CommandHandler("maintenance", handle_maintenance_command, filters=admin_filter))
    application.add_handler(CommandHandler("pendingpayments", handle_pending_payments_command, filters=admin_filter)) # New admin command
    application.add_handler(CommandHandler("cancel", cancel)) # Global cancel command
    
    # Add conversation handler for file processing
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_command_handler), # Use the new async handler
            # Removed broad CallbackQueryHandler from entry_points to avoid interference
            CommandHandler("pdf2png", pdf_to_images_flow_start),
            CommandHandler("png2pdf", png_to_pdf_flow_start),
            CommandHandler("jpg2pdf", jpg_to_pdf_flow_start),
            CommandHandler("webp2pdf", webp_to_pdf_flow_start),
            CommandHandler("tiff2pdf", tiff_to_pdf_flow_start),
            CommandHandler("docx2pdf", handle_docx_to_pdf),
            CommandHandler("pdf2docx", handle_pdf_to_docx),
            CommandHandler("pptx2pdf", handle_pptx_to_pdf),
            CommandHandler("pdf2pptx", handle_pdf_to_pptx),
            CommandHandler("ocr", ocr_flow_start),
            CommandHandler("mergepdf", merge_pdf_flow_start),
            CommandHandler("splitpdf", split_pdf_flow_start),
            CommandHandler("compress", compress_flow_start),
            CommandHandler("watermark", watermark_flow_start),
            CommandHandler("url", url_conversion_flow_start),
            CommandHandler("payment", handle_payment_command), # New payment command entry point
        ],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(handle_menu_callbacks, pattern='^(pdf_conversions_menu|png_conversions_menu|jpg_conversions_menu|webp_conversions_menu|tiff_conversions_menu|docx_conversions_menu|pptx_conversions_menu|help_command|start|pdf_to_|png_to_|jpg_to_|webp_to_|tiff_to_|docx_to_|pptx_to_|ocr_start|merge_pdf_start|split_pdf_start|compress_pdf_start|compress_image_start|watermark_start|url_conversion_start|payment_option_).*$'),
            ],
            SELECT_CONVERSION_TYPE: [
                MessageHandler(filters.Document.ALL | filters.PHOTO | (filters.TEXT & ~filters.COMMAND), handle_document_type)
            ],
            SELECT_PAGES: [
                CallbackQueryHandler(select_pages, pattern='^(all|specific)$'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_specific_pages_input)
            ],
            SELECT_OUTPUT_FORMAT: [CallbackQueryHandler(select_output_format, pattern='^(individual|zip|cancel)$')],
            OCR_PROCESSING: [
                MessageHandler(filters.Document.ALL | filters.PHOTO, handle_ocr_document)
            ],
            MERGE_PDF_COLLECTION: [
                MessageHandler(filters.Document.MimeType("application/pdf") | filters.TEXT, handle_merge_pdf_documents)
            ],
            SPLIT_PDF_INPUT_PAGES: [
                MessageHandler(filters.Document.MimeType("application/pdf"), handle_split_pdf_document),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_split_pages_input)
            ],
            COMPRESS_FILE_PROCESSING: [
                MessageHandler(filters.Document.ALL | filters.PHOTO, handle_compression_document)
            ],
            WATERMARK_FILE_INPUT: [
                MessageHandler(filters.Document.ALL | filters.PHOTO, handle_watermark_file_input)
            ],
            WATERMARK_TEXT_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_watermark_text_input)
            ],
            WATERMARK_IMAGE_INPUT: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_watermark_image_input)
            ],
            WATERMARK_POSITION_INPUT: [
                CallbackQueryHandler(handle_watermark_position_input, pattern='^(top-left|top-right|bottom-left|bottom-right|center)$')
            ],
            URL_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url_input)
            ],
            RESIZE_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_resize_input)
            ],
            ROTATE_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rotate_input)
            ],
            PAYMENT_INPUT: [
                MessageHandler(filters.Document.ALL | filters.PHOTO, handle_payment_confirmation_file),
                # This state might also handle text messages for transaction IDs if needed
            ],
            SELECT_PAYMENT_OPTION: [
                CallbackQueryHandler(handle_payment_option_selection, pattern='^payment_option_.*$')
            ],
            SELECT_PAYMENT_METHOD: [
                CallbackQueryHandler(handle_payment_method_selection, pattern='^payment_method_.*$')
            ]
        },
        fallbacks=[CommandHandler("start", start), CommandHandler("cancel", cancel)]
    )
    application.add_handler(conv_handler)

    # Set bot commands
    logger.info("Scheduling set_bot_commands to run once.")
    application.job_queue.run_once(
        lambda ctx: set_bot_commands(ctx.job.data), 
        0, 
        data=application
    )

    # Schedule daily R2 cleanup job
    # Run daily at a specific time, e.g., 03:00 AM UTC
    application.job_queue.run_daily(
        daily_r2_cleanup_job,
        time=datetime.strptime('03:00', '%H:%M').time(),
        days=(0, 1, 2, 3, 4, 5, 6), # Every day of the week
        name='Daily R2 Cleanup'
    )
    logger.info("Scheduled daily R2 cleanup job for 03:00 AM UTC.")

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    logger.info("Starting bot polling. Press Ctrl-C to stop.")
    application.run_polling()
    logger.info("Bot polling stopped gracefully.")

async def error_handler(update: object, context: CallbackContext) -> None:
    """Log the error and send a telegram message to notify the admin."""
    logger.error("Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns a list of strings, we join them here.
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Build the message with as much information as possible
    message = (
        f"🔥 *An error occurred!* 🔥\n\n"
        f"🚨 *Error:* `{context.error}`\n\n"
        f"⚡️ *Update:* `{update}`\n\n"
        f"```python\n{tb_string[:1000]}...\n```" # Limit traceback to 1000 chars
    )
    
    # Send notification to the channel
    await send_notification_to_channel(message, parse_mode='Markdown')

    # Optionally, notify the user who caused the error
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "Oops! Something went wrong while processing your request. "
            "Our team has been notified and is looking into it. Please try again later! 💔"
        )

if __name__ == '__main__':
    main()
