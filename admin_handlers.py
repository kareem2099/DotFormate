import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import CallbackContext
from database import get_all_users, get_user_count, get_active_users, get_conversion_stats, toggle_user_status, get_pending_manual_payments, update_manual_payment_status, update_user_premium_status, get_user, MongoDBManager
from notification_utils import send_notification_to_channel
from datetime import datetime, timedelta
from r2_utils import delete_file_from_r2 # Import for R2 deletion

logger = logging.getLogger(__name__)

# Admin User IDs (replace with your actual admin IDs or fetch from environment)
import os # Import os for environment variables
ADMIN_USER_IDS = [int(uid) for uid in os.getenv("ADMIN_USER_IDS", "").split(',') if uid.strip().isdigit()]

def is_admin(user_id: int) -> bool:
    """Checks if a user is an admin."""
    return user_id in ADMIN_USER_IDS

async def send_admin_notification(context: CallbackContext, message: str) -> None:
    """Sends a notification message to the admin channel."""
    try:
        await send_notification_to_channel(context, message)
        logger.info(f"Admin notification sent: {message}")
    except Exception as e:
        logger.error(f"Failed to send admin notification: {e}")

async def admin_command_example(update: Update, context: CallbackContext) -> None:
    """Sends a message with admin options."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this command.")
        return

    keyboard = [
        [InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Manage Users", callback_data="admin_manage_users")],
        [InlineKeyboardButton("💰 Pending Payments", callback_data="admin_pending_payments")], # New button
        [InlineKeyboardButton("⚙️ Maintenance", callback_data="admin_maintenance")],
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📜 View Logs", callback_data="admin_logs")],
        [InlineKeyboardButton("💾 Backup DB", callback_data="admin_backup")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Admin Panel:", reply_markup=reply_markup)

async def handle_admin_callbacks(update: Update, context: CallbackContext) -> None:
    """Handles callbacks from the admin panel."""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("You are not authorized to perform this action.")
        return

    data = query.data
    if data == "admin_stats":
        await show_bot_stats(query, context)
    elif data == "admin_manage_users":
        await manage_users(query, context)
    elif data == "admin_pending_payments":
        await show_pending_payments(query, context)
    elif data == "admin_maintenance":
        await query.edit_message_text("Maintenance options coming soon.")
    elif data == "admin_broadcast":
        await query.edit_message_text("Broadcast message feature coming soon.")
    elif data == "admin_logs":
        await query.edit_message_text("Logs viewing feature coming soon.")
    elif data == "admin_backup":
        await query.edit_message_text("Database backup feature coming soon.")
    elif data.startswith("admin_user_toggle_status_"):
        user_id_to_toggle = int(data.replace("admin_user_toggle_status_", ""))
        await toggle_user_active_status(query, context, user_id_to_toggle)
    elif data.startswith("admin_approve_payment_"):
        payment_id = data.replace("admin_approve_payment_", "")
        await approve_manual_payment(query, context, payment_id)
    elif data.startswith("admin_reject_payment_"):
        payment_id = data.replace("admin_reject_payment_", "")
        await reject_manual_payment(query, context, payment_id)
    elif data.startswith("admin_view_payment_file_"):
        r2_url = data.replace("admin_view_payment_file_", "")
        await query.message.reply_document(document=r2_url) # Send the document directly
        await query.edit_message_text(f"Opened file: {r2_url}") # Update the message to show it was opened

async def show_bot_stats(query: CallbackQuery, context: CallbackContext) -> None:
    """Displays various bot statistics."""
    total_users = await get_user_count()
    active_users_7_days = await get_active_users(days=7)
    conversion_stats = await get_conversion_stats()

    stats_message = (
        f"📊 *Bot Statistics* 📊\n\n"
        f"👥 Total Users: `{total_users}`\n"
        f"🟢 Active Users (last 7 days): `{active_users_7_days}`\n"
        f"🔄 Total Conversions: `{conversion_stats.get('total', 0)}`\n"
        f"📄 PDF Conversions: `{conversion_stats.get('pdf', 0)}`\n"
        f"🖼️ Image Conversions: `{conversion_stats.get('image', 0)}`\n"
        f"\n_Stats are approximate and updated periodically._"
    )
    await query.edit_message_text(stats_message, parse_mode='Markdown')

async def manage_users(query: CallbackQuery, context: CallbackContext) -> None:
    """Displays a list of users for management."""
    users = await get_all_users()
    if not users:
        await query.edit_message_text("No users found.")
        return

    message_text = "👥 *User Management* 👥\n\n"
    keyboard = []
    for user in users:
        status = "✅ Active" if user.get("is_active", True) else "🚫 Banned"
        button_text = f"{user.get('username', user['first_name'])} (ID: {user['user_id']}) - {status}"
        callback_data = f"admin_user_toggle_status_{user['user_id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

async def toggle_user_active_status(query: CallbackQuery, context: CallbackContext, user_id_to_toggle: int) -> None:
    """Toggles the active status of a user (ban/unban)."""
    user = await get_user(user_id_to_toggle)
    if not user:
        await query.edit_message_text(f"User {user_id_to_toggle} not found.")
        return

    current_status = user.get("is_active", True)
    new_status = not current_status
    success = await toggle_user_status(user_id_to_toggle, new_status)

    if success:
        status_text = "unbanned" if new_status else "banned"
        await query.edit_message_text(f"User {user_id_to_toggle} has been {status_text}.")
        # Optionally, notify the user about their status change
        try:
            await context.bot.send_message(chat_id=user.get('chat_id'), text=f"Your account has been {status_text} by an administrator.")
        except Exception as e:
            logger.warning(f"Could not notify user {user_id_to_toggle} about status change: {e}")
    else:
        await query.edit_message_text(f"Failed to toggle status for user {user_id_to_toggle}.")

async def handle_users_command(update: Update, context: CallbackContext) -> None:
    """Admin command to list all users."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this command.")
        return
    
    await manage_users(update.message, context) # Reuse manage_users logic

async def handle_logs_command(update: Update, context: CallbackContext) -> None:
    """Admin command to view logs (placeholder)."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this command.")
        return
    await update.message.reply_text("Logs viewing feature coming soon.")

async def handle_backup_command(update: Update, context: CallbackContext) -> None:
    """Admin command to backup database (placeholder)."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this command.")
        return
    await update.message.reply_text("Database backup feature coming soon.")

async def handle_maintenance_command(update: Update, context: CallbackContext) -> None:
    """Admin command for maintenance tasks (placeholder)."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this command.")
        return
    await update.message.reply_text("Maintenance options coming soon.")

async def toggle_maintenance_mode(update: Update, context: CallbackContext) -> None:
    """Placeholder for toggling maintenance mode."""
    # In a real application, this would update a setting in the database
    # and potentially notify users.
    await update.message.reply_text("Maintenance mode toggle functionality is a placeholder. No action taken.")

async def show_pending_payments(query: CallbackQuery, context: CallbackContext) -> None:
    """Displays a list of pending manual payment confirmations for admin review."""
    pending_payments = await get_pending_manual_payments()

    if not pending_payments:
        await query.edit_message_text("No pending manual payments found.")
        return

    message_text = "💰 *Pending Manual Payments* 💰\n\n"
    keyboard = []
    for payment in pending_payments:
        user_id = payment.get('user_id', 'N/A')
        file_name = payment.get('file_name', 'N/A')
        r2_url = payment.get('r2_url', '')
        upload_time = payment.get('upload_time', datetime.utcnow()).strftime('%Y-%m-%d %H:%M')
        premium_type = payment.get('premium_type', 'N/A')
        amount = payment.get('amount', 'N/A')
        payment_id = str(payment['_id']) # MongoDB ObjectId needs to be converted to string

        message_text += (
            f"--- Payment ID: `{payment_id}` ---\n"
            f"👤 User ID: `{user_id}`\n"
            f"📁 File: [{file_name}]({r2_url})\n"
            f"⏰ Upload Time: {upload_time}\n"
            f"✨ Premium Type: {premium_type}\n"
            f"💲 Amount: ${amount}\n\n"
        )
        
        keyboard.append([
            InlineKeyboardButton(f"✅ Approve {user_id}", callback_data=f"admin_approve_payment_{payment_id}"),
            InlineKeyboardButton(f"❌ Reject {user_id}", callback_data=f"admin_reject_payment_{payment_id}"),
            InlineKeyboardButton(f"👁️ View File", callback_data=f"admin_view_payment_file_{r2_url}")
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown', disable_web_page_preview=True)

async def approve_manual_payment(query: CallbackQuery, context: CallbackContext, payment_id: str) -> None:
    """Approves a manual payment, updates user's premium status, and notifies the user."""
    success = await update_manual_payment_status(payment_id, "approved")
    if success:
        # Retrieve payment details to get user_id, premium_type, etc.
        # This requires fetching the payment entry again or passing more data
        # For simplicity, let's assume we can get it from the DB using payment_id
        db_manager = MongoDBManager()
        db = await db_manager.get_db()
        from bson import ObjectId
        payment_entry = await db.manual_payments.find_one({"_id": ObjectId(payment_id)})

        if payment_entry:
            user_id = payment_entry['user_id']
            premium_type = payment_entry.get('premium_type')
            
            # Update user's premium status based on the approved payment
            # Assuming premium_type maps to duration (e.g., "monthly", "yearly")
            # You'll need to define how premium_type translates to expiry dates
            premium_expiry_date = datetime.utcnow() + timedelta(days=30) # Example: 30 days for any premium
            if premium_type == "monthly":
                premium_expiry_date = datetime.utcnow() + timedelta(days=30)
            elif premium_type == "yearly":
                premium_expiry_date = datetime.utcnow() + timedelta(days=365)
            # Add other premium types as needed

            user_premium_updated = await update_user_premium_status(user_id, True, premium_type, premium_expiry_date)
            
            if user_premium_updated:
                await query.edit_message_text(f"Payment {payment_id} approved. User {user_id} premium status updated.")
                # Notify user
                user_data = await get_user(user_id)
                if user_data and user_data.get('chat_id'):
                    await context.bot.send_message(
                        chat_id=user_data['chat_id'],
                        text=f"🎉 Your payment has been successfully approved! Your premium features are now active until {premium_expiry_date.strftime('%Y-%m-%d %H:%M UTC')}. Enjoy!"
                    )
            else:
                await query.edit_message_text(f"Payment {payment_id} approved, but failed to update user {user_id}'s premium status.")
        else:
            await query.edit_message_text(f"Payment {payment_id} approved, but payment entry not found in DB.")
    else:
        await query.edit_message_text(f"Failed to approve payment {payment_id}.")
    await show_pending_payments(query, context) # Refresh the list

async def reject_manual_payment(query: CallbackQuery, context: CallbackContext, payment_id: str) -> None:
    """Rejects a manual payment and notifies the user."""
    success = await update_manual_payment_status(payment_id, "rejected")
    if success:
        await query.edit_message_text(f"Payment {payment_id} rejected.")
        # Notify user
        db_manager = MongoDBManager()
        db = await db_manager.get_db()
        from bson import ObjectId
        payment_entry = await db.manual_payments.find_one({"_id": ObjectId(payment_id)})
        if payment_entry:
            user_id = payment_entry['user_id']
            user_data = await get_user(user_id)
            if user_data and user_data.get('chat_id'):
                await context.bot.send_message(
                    chat_id=user_data['chat_id'],
                    text="💔 Your payment confirmation could not be verified. Please ensure the details are correct and try again, or contact support."
                )
    else:
        await query.edit_message_text(f"Failed to reject payment {payment_id}.")
    await show_pending_payments(query, context) # Refresh the list
