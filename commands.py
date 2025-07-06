from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext
import os
import logging
from admin_handlers import is_admin, handle_admin_users, toggle_maintenance_mode # Import centralized is_admin and admin handlers

logger = logging.getLogger(__name__)

# Define user commands
USER_COMMANDS = [
    BotCommand("start", "🚀 Start the bot and see all conversion options"),
    BotCommand("help", "❓ Get help on how to use this bot"),
    BotCommand("pdf2png", "📄➡️🖼️ Convert a PDF file to PNG images"),
    BotCommand("png2pdf", "🖼️➡️📄 Convert PNG images to a PDF file"),
    BotCommand("jpg2pdf", "📸➡️📄 Convert JPG images to a PDF file"),
    BotCommand("webp2pdf", "🌐➡️📄 Convert WEBP images to a PDF file"),
    BotCommand("tiff2pdf", "📁➡️📄 Convert TIFF images to a PDF file"),
    BotCommand("docx2pdf", "📝➡️📄 Convert Word to PDF"),
    BotCommand("pdf2docx", "📄➡️📝 Convert PDF to Word"),
    BotCommand("pptx2pdf", "📊➡️📄 Convert PowerPoint to PDF"),
    BotCommand("pdf2pptx", "📄➡️📊 Convert PDF to PowerPoint"),
    BotCommand("ocr", "📄 Extract text from images or PDFs"),
    BotCommand("mergepdf", "➕ Combine multiple PDFs into one"),
    BotCommand("splitpdf", "✂️ Split a PDF into multiple files"),
    BotCommand("compress", "🗜️ Reduce the file size of PDFs or images"),
    BotCommand("watermark", "✍️ Add text or image watermarks to files"),
    BotCommand("url", "🔗 Convert files directly from a URL"),
    BotCommand("cancel", "❌ Cancel the current operation"),
    BotCommand("referral", "🎁 Get your referral link and track invites"),
    BotCommand("payment", "💳 Make a payment or donation")
]

# Define admin-only commands
ADMIN_ONLY_COMMANDS = [
    BotCommand("admin", "🛠️ Access admin control panel"),
    BotCommand("stats", "📊 View bot statistics"),
    BotCommand("broadcast", "📢 Send message to all users"),
    BotCommand("users", "👥 Manage users (ban/unban)"),
    BotCommand("logs", "📝 View system logs"),
    BotCommand("backup", "💾 Create database backup"),
    BotCommand("maintenance", "⚙️ Toggle maintenance mode"),
    BotCommand("userswitch", "👥 Switch to user commands")
]

async def set_bot_commands(application, user_id=None):
    """Sets the bot's commands based on user role."""
    try:
        # Set default commands for all users
        await application.bot.set_my_commands(USER_COMMANDS)
        logger.info("User commands set successfully.")

        # If user_id is provided and is admin, set admin-only commands
        if user_id and is_admin(user_id):
            await application.bot.set_my_commands(
                ADMIN_ONLY_COMMANDS,
                scope={"type": "chat", "chat_id": user_id}
            )
            logger.info(f"Admin commands set for user {user_id}")

    except Exception as e:
        logger.error(f"Error setting bot commands: {e}")

async def admin_command_example(update, context):
    """Admin control panel command."""
    if is_admin(update.effective_user.id):
        # Update commands for this admin user (admin-only commands)
        await set_bot_commands(context.application, update.effective_user.id)
        
        # Show full admin control panel
        keyboard = [
            [InlineKeyboardButton("📊 Bot Statistics", callback_data="admin_stats")],
            [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")],
            [InlineKeyboardButton("👥 Show User Commands", callback_data="show_user_commands")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🛠️ *Admin Control Panel* 🛠️\n\n"
            "Select an option below:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("You are not authorized to use this command.")

async def handle_users_command(update: Update, context: CallbackContext):
    """Handle /users command for user management."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Access denied. Admin privileges required.")
        return
    
    await handle_admin_users(update, context)

async def handle_logs_command(update: Update, context: CallbackContext):
    """Handle /logs command for viewing system logs."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Access denied. Admin privileges required.")
        return
    
    # Basic implementation - can be enhanced with log file viewing
    await update.message.reply_text(
        "📝 *System Logs*\n\n"
        "Recent logs will be displayed here.\n"
        "Implementation in progress...",
        parse_mode="Markdown"
    )

async def handle_backup_command(update: Update, context: CallbackContext):
    """Handle /backup command for database backups."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Access denied. Admin privileges required.")
        return
    
    # Basic implementation - can be enhanced with actual backup
    await update.message.reply_text(
        "💾 *Database Backup*\n\n"
        "Backup functionality coming soon.\n"
        "Implementation in progress...",
        parse_mode="Markdown"
    )

async def handle_maintenance_command(update: Update, context: CallbackContext):
    """Handle /maintenance command for maintenance mode."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Access denied. Admin privileges required.")
        return
    
    await toggle_maintenance_mode(update, context)
