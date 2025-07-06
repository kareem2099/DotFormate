import os
import json
import logging
import requests # For direct Telegram API calls
from urllib.parse import urlparse, parse_qs
# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from database import update_user_data, get_user_by_paypal_payment_id
from constants import PAYMENT_PENDING, PAYMENT_FAILED

def send_telegram_message(chat_id: int, text: str):
    """Sends a message to a Telegram user using the Bot API."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set in environment variables.")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status() # Raise an exception for HTTP errors
        logger.info(f"Telegram message sent to {chat_id}: {text}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Telegram message to {chat_id}: {e}")
        return False

def handler(request):
    """
    Vercel serverless function handler for PayPal cancel URL (browser redirect).
    This function is called when PayPal redirects the user's browser back after cancellation.
    """
    if request.method != 'GET':
        return {
            'statusCode': 405,
            'body': 'Method Not Allowed'
        }

    try:
        # Extract query parameters from the request URL
        query_params = parse_qs(urlparse(request.url).query)
        
        user_id = query_params.get('user_id', [None])[0]
        # PayPal cancel URL might not always include paymentId or PayerID,
        # but user_id should be present if we passed it.

        logger.info(f"PayPal cancel handler received: user_id={user_id}")

        if not user_id:
            logger.warning("Missing user_id in PayPal cancel URL.")
            return {
                'statusCode': 400,
                'body': 'Missing user ID.'
            }

        # Convert user_id to int
        user_id = int(user_id)

        # Notify the user about the cancellation
        send_telegram_message(user_id, PAYMENT_PENDING + " (Payment cancelled by user.)")
        logger.info(f"PayPal payment cancelled notification sent for user {user_id}.")
        
        # Redirect user back to Telegram bot
        # Replace YOUR_BOT_USERNAME with your actual bot's username
        return {
            'statusCode': 302,
            'headers': {
                'Location': f'tg://resolve?domain=your_bot_username' # Or a simple HTML cancellation page
            }
        }

    except Exception as e:
        logger.error(f"Error processing PayPal cancel: {e}", exc_info=True)
        # Attempt to notify user if user_id is available
        if 'user_id' in locals() and user_id:
            send_telegram_message(user_id, PAYMENT_FAILED + f" (Error: {e})")
        return {
            'statusCode': 500,
            'body': f'Internal Server Error: {e}'
        }
