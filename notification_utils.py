import os
import logging
from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

# Initialize the notification bot with the specific token from .env
NOTIFICATION_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN_Notifications")
NOTIFICATION_CHAT_ID = os.getenv("ADMIN_NOTIFICATION_CHAT_ID")

notification_bot = None
if NOTIFICATION_BOT_TOKEN:
    try:
        notification_bot = Bot(token=NOTIFICATION_BOT_TOKEN)
        logger.info("Notification bot initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize notification bot: {e}")
else:
    logger.warning("TELEGRAM_BOT_TOKEN_Notifications not found in environment variables. Notifications will not be sent.")

async def send_notification_to_channel(message: str, parse_mode: str = None):
    """
    Sends a notification message to the predefined Telegram channel.
    """
    if not notification_bot:
        logger.warning("Notification bot not initialized. Cannot send notification.")
        return

    if not NOTIFICATION_CHAT_ID:
        logger.warning("NOTIFICATION_CHAT_ID not set. Cannot send notification.")
        return

    try:
        await notification_bot.send_message(
            chat_id=NOTIFICATION_CHAT_ID,
            text=message,
            parse_mode=parse_mode
        )
        logger.info(f"Notification sent to channel {NOTIFICATION_CHAT_ID}.")
    except TelegramError as e:
        logger.error(f"Failed to send notification to channel {NOTIFICATION_CHAT_ID}: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while sending notification: {e}")
