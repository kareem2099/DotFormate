import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from database import get_user_count, get_active_users, get_conversion_stats, get_all_users, toggle_user_status

logger = logging.getLogger(__name__)

ADMIN_COMMANDS = {
    'stats': "📊 Get bot statistics",
    'broadcast': "📢 Send broadcast message",
    'users': "👥 Manage users",
    'maintenance': "🛠 Toggle maintenance mode",
    'logs': "📝 View recent logs",
    'backup': "💾 Create database backup"
}

def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
    # Filter out empty strings from split in case ADMIN_USER_IDS is empty or malformed
    admin_ids = [int(uid.strip()) for uid in admin_ids_str.split(',') if uid.strip().isdigit()]
    return user_id in admin_ids

async def admin_panel(update: Update, context: CallbackContext):
    """Admin control panel with enhanced features."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ *Access Denied*\n\nYou don't have admin privileges.")
        return

    keyboard = [
        [InlineKeyboardButton(ADMIN_COMMANDS['stats'], callback_data="admin_stats")],
        [InlineKeyboardButton(ADMIN_COMMANDS['users'], callback_data="admin_users")],
        [InlineKeyboardButton(ADMIN_COMMANDS['broadcast'], callback_data="admin_broadcast")],
        [InlineKeyboardButton(ADMIN_COMMANDS['maintenance'], callback_data="admin_maintenance")],
        [InlineKeyboardButton(ADMIN_COMMANDS['logs'], callback_data="admin_logs")],
        [InlineKeyboardButton(ADMIN_COMMANDS['backup'], callback_data="admin_backup")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🛠️ *Admin Control Panel* 🛠️\n\n"
        f"🕒 Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        "Select an option below:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def handle_admin_stats(update: Update, context: CallbackContext):
    """Display comprehensive bot statistics."""
    if not is_admin(update.effective_user.id):
        return

    stats = f"""
📊 *Bot Statistics Report* 📊

👥 Users: {get_user_count()}
📈 Active Users (7d): {get_active_users()}
🔄 Total Conversions: {get_conversion_stats()['total']}
📄 PDF Conversions: {get_conversion_stats()['pdf']}
🖼️ Image Conversions: {get_conversion_stats()['image']}
⏳ Uptime: {datetime.now() - context.bot_data.get('start_time', datetime.now())}
"""

    await update.callback_query.edit_message_text(
        stats,
        parse_mode="Markdown"
    )

async def send_admin_notification(context: CallbackContext, message: str, level: str = "INFO"):
    """Enhanced admin notification system with logging levels."""
    notification_bot = context.bot
    ADMIN_NOTIFICATION_CHAT_ID = os.getenv("ADMIN_NOTIFICATION_CHAT_ID")
    
    if not (notification_bot and ADMIN_NOTIFICATION_CHAT_ID):
        logger.warning("Notification system not configured")
        return

    try:
        prefix = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "CRITICAL": "🔥"
        }.get(level.upper(), "📌")

        await notification_bot.send_message(
            chat_id=ADMIN_NOTIFICATION_CHAT_ID,
            text=f"{prefix} *{level}*: {message}",
            parse_mode="Markdown"
        )
        logger.info(f"Admin notification sent ({level}): {message}")
    except Exception as e:
        logger.error(f"Failed to send admin notification: {e}")

async def toggle_maintenance_mode(update: Update, context: CallbackContext):
    """Toggle maintenance mode on/off."""
    if not is_admin(update.effective_user.id):
        if update.callback_query:
            await update.callback_query.edit_message_text("⛔ Access denied. Admin privileges required.")
        else:
            await update.message.reply_text("⛔ Access denied. Admin privileges required.")
        return

    context.bot_data['maintenance_mode'] = not context.bot_data.get('maintenance_mode', False)
    status = "🟢 ON" if context.bot_data['maintenance_mode'] else "🔴 OFF"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            f"🛠 *Maintenance Mode*: {status}\n\n"
            "The bot will now {}accept user commands.".format(
                "not " if context.bot_data['maintenance_mode'] else ""
            ),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"🛠 *Maintenance Mode*: {status}\n\n"
            "The bot will now {}accept user commands.".format(
                "not " if context.bot_data['maintenance_mode'] else ""
            ),
            parse_mode="Markdown"
        )
        
    await send_admin_notification(
        context,
        f"Maintenance mode changed to {status} by {update.effective_user.username}"
    )

async def handle_admin_users(update: Update, context: CallbackContext):
    """Handle user management functionality."""
    if not is_admin(update.effective_user.id):
        return

    keyboard = [
        [InlineKeyboardButton("👥 List All Users", callback_data="list_users")],
        [InlineKeyboardButton("🚫 Ban User", callback_data="ban_user")],
        [InlineKeyboardButton("✅ Unban User", callback_data="unban_user")],
        [InlineKeyboardButton("⬅️ Back", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        "👥 *User Management*\n\n"
        "Select an action below:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def list_all_users(update: Update, context: CallbackContext):
    """List all users with pagination."""
    if not is_admin(update.effective_user.id):
        return

    users = get_all_users()
    
    if not users:
        await update.callback_query.edit_message_text("No users found in database.")
        return

    user_list = "\n".join(
        f"{i+1}. {user['username'] or 'No username'} (ID: {user['user_id']}) - "
        f"{'✅ Active' if user['is_active'] else '🚫 Banned'}"
        for i, user in enumerate(users[:50])  # Show first 50 users
    )
    
    await update.callback_query.edit_message_text(
        f"👥 *User List* (Showing {min(50, len(users))} of {len(users)})\n\n"
        f"{user_list}\n\n"
        "Use /ban [id] or /unban [id] to manage users.",
        parse_mode="Markdown"
    )
