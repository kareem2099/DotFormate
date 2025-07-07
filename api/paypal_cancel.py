from flask import Flask, request, jsonify, redirect
import os
import json
import logging
import requests
from urllib.parse import urlparse, parse_qs

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Assuming database and constants are accessible or will be mocked/handled appropriately in a real deployment
# from database import update_user_data, get_user_by_paypal_payment_id
# from constants import PAYMENT_PENDING, PAYMENT_FAILED

app = Flask(__name__)

# Placeholder for send_telegram_message and constants if not directly imported
# In a real scenario, ensure these are properly imported or defined.
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
        response.raise_for_status()
        logger.info(f"Telegram message sent to {chat_id}: {text}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Telegram message to {chat_id}: {e}")
        return False

PAYMENT_PENDING = "Your payment is pending."
PAYMENT_FAILED = "Your payment has failed."


@app.route('/api/paypal_cancel', methods=['GET'])
async def paypal_cancel_handler():
    """
    Vercel serverless function handler for PayPal cancel URL (browser redirect).
    This function handles the request when PayPal redirects the user's browser back after cancellation.
    """
    try:
        # Extract query parameters from the request
        query_params = request.args
        
        user_id = query_params.get('user_id')
        # PayPal cancel URL might not always include paymentId or PayerID,
        # but user_id should be present if we passed it.

        logger.info(f"PayPal cancel handler received: user_id={user_id}")

        if not user_id:
            logger.warning("Missing user_id in PayPal cancel URL.")
            return jsonify({'status': 'error', 'message': 'Missing user ID.'}), 400

        # Convert user_id to int
        user_id = int(user_id)

        # Notify the user about the cancellation
        await send_telegram_message(user_id, PAYMENT_PENDING + " (Payment cancelled by user.)")
        logger.info(f"PayPal payment cancelled notification sent for user {user_id}.")
        
        # Redirect user back to Telegram bot
        # Replace YOUR_BOT_USERNAME with your actual bot's username
        return redirect(f'tg://resolve?domain=your_bot_username')  # Or a simple HTML cancellation page

    except Exception as e:
        logger.error(f"Error processing PayPal cancel: {e}", exc_info=True)
        # Attempt to notify user if user_id is available
        if 'user_id' in locals() and user_id:
            await send_telegram_message(user_id, PAYMENT_FAILED + f" (Error: {e})")
        return jsonify({'status': 'error', 'message': f'Internal Server Error: {e}'}), 500
