import os
import json
import logging
import requests # For direct Telegram API calls
from urllib.parse import urlparse, parse_qs
import sys

# Add the parent directory to the Python path to allow imports from the root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

try:
    from paypal_integration import execute_paypal_payment
    from database import update_user_data, get_user_by_paypal_payment_id
    from constants import PAYMENT_SUCCESS, PAYMENT_FAILED
except ImportError as e:
    logger.error(f"Failed to import necessary modules for paypal_return: {e}. Simulating functions.")
    async def execute_paypal_payment(payment_id: str, payer_id: str):
        logger.info(f"Simulating execute_paypal_payment for {payment_id} with {payer_id}")
        return True # Simulate success
    async def update_user_data(user_id, data):
        logger.info(f"Simulating update_user_data for user {user_id} with {data}")
        pass
    async def get_user_by_paypal_payment_id(payment_id: str):
        logger.info(f"Simulating get_user_by_paypal_payment_id for {payment_id}")
        return {'user_id': 12345, 'chat_id': 67890} # Simulate a user
    PAYMENT_SUCCESS = "Payment simulated as successful."
    PAYMENT_FAILED = "Payment simulated as failed."

async def send_telegram_message(chat_id: int, text: str):
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

async def handler(request):
    """
    Vercel serverless function handler for PayPal return URL (browser redirect).
    This function is called when PayPal redirects the user's browser back to your app.
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
        payment_id = query_params.get('paymentId', [None])[0]
        payer_id = query_params.get('PayerID', [None])[0]

        logger.info(f"PayPal return handler received: user_id={user_id}, payment_id={payment_id}, payer_id={payer_id}")

        if not all([user_id, payment_id, payer_id]):
            logger.warning("Missing required parameters in PayPal return URL.")
            # Attempt to notify user if user_id is available
            if user_id:
                await send_telegram_message(int(user_id), PAYMENT_FAILED + " (Missing payment details)")
            return {
                'statusCode': 400,
                'body': 'Missing required payment details.'
            }

        # Convert user_id to int
        user_id = int(user_id)

        success = await execute_paypal_payment(payment_id, payer_id)

        if success:
            # Update user's subscription status in the database
            await update_user_data(user_id, {'subscription_status': 'active'})
            await send_telegram_message(user_id, PAYMENT_SUCCESS)
            logger.info(f"PayPal payment {payment_id} successfully processed for user {user_id}.")
            
            # Redirect user back to Telegram bot
            # Replace YOUR_BOT_USERNAME with your actual bot's username
            return {
                'statusCode': 302,
                'headers': {
                    'Location': f'tg://resolve?domain=YOUR_BOT_USERNAME' # Or a simple HTML success page
                }
            }
        else:
            await send_telegram_message(user_id, PAYMENT_FAILED)
            logger.error(f"PayPal payment {payment_id} failed execution for user {user_id}.")
            return {
                'statusCode': 302,
                'headers': {
                    'Location': f'tg://resolve?domain=YOUR_BOT_USERNAME' # Or a simple HTML failure page
                }
            }

    except Exception as e:
        logger.error(f"Error processing PayPal return: {e}", exc_info=True)
        # Attempt to notify user if user_id is available
        if 'user_id' in locals() and user_id:
            await send_telegram_message(user_id, PAYMENT_FAILED + f" (Error: {e})")
        return {
            'statusCode': 500,
            'body': f'Internal Server Error: {e}'
        }
