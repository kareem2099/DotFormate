from flask import Flask, request, jsonify, redirect
import os
import logging
import asyncio # Import asyncio for sleep

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Assuming these modules are accessible in the Vercel environment
from paypal_integration import execute_paypal_payment
from database import update_user_data, get_user_by_paypal_payment_id, get_user
from constants import PAYMENT_SUCCESS, PAYMENT_FAILED

app = Flask(__name__)

async def send_telegram_message(chat_id: int, text: str):
    """Sends a message to a Telegram user using the Bot API."""
    import requests # Lazy import requests
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

@app.route('/api/paypal_return', methods=['GET'])
async def paypal_return_handler():
    logger.info(f"PayPal return handler called with method: {request.method}")
    logger.info(f"Request URL: {request.url}")
    
    user_id = None # Initialize user_id to None
    chat_id = None # Initialize chat_id to None
    try:
        # Extract parameters from the URL
        user_id_from_url = request.args.get('user_id')
        paymentId = request.args.get('paymentId')
        token = request.args.get('token')
        PayerID = request.args.get('PayerID')

        logger.info(f"Received PayPal return parameters: user_id={user_id_from_url}, paymentId={paymentId}, token={token}, PayerID={PayerID}")

        if not all([user_id_from_url, paymentId, token, PayerID]):
            logger.warning("Missing required PayPal return parameters.")
            return jsonify({'status': 'error', 'message': 'Missing required parameters.'}), 400

        # Attempt to get user_id from the database using paymentId
        # This is more reliable than user_id from URL as it's linked to the payment creation
        user_data = await get_user_by_paypal_payment_id(paymentId)
        if user_data:
            user_id = user_data.get('user_id')
            chat_id = user_data.get('chat_id') # Get chat_id for sending Telegram message
            logger.info(f"Found user {user_id} with chat_id {chat_id} for payment ID {paymentId}.")
        else:
            # Fallback to user_id from URL if not found in DB (less reliable)
            user_id = int(user_id_from_url)
            # Try to get chat_id from user_id if not found by paymentId
            user_data_by_id = await get_user(user_id)
            chat_id = user_data_by_id.get('chat_id') if user_data_by_id else None
            logger.warning(f"User not found by payment ID {paymentId}. Falling back to user_id from URL: {user_id}. Chat ID: {chat_id}")
            if not chat_id:
                logger.error(f"Could not determine chat_id for user {user_id}. Cannot send Telegram message.")
                return jsonify({'status': 'error', 'message': 'User chat ID not found.'}), 500

        # Introduce a small delay to allow PayPal's systems to propagate the payment status
        await asyncio.sleep(5) # Increased wait time to 5 seconds

        # Execute the PayPal payment
        success, error_details = await execute_paypal_payment(paymentId, PayerID)

        if success:
            await update_user_data(user_id, {'subscription_status': 'active'})
            await send_telegram_message(chat_id, PAYMENT_SUCCESS)
            logger.info(f"PayPal payment {paymentId} successfully processed for user {user_id}.")
            # Redirect user back to Telegram bot
            return redirect(f'tg://resolve?domain=your_bot_username') # Replace with actual bot username
        else:
            error_message_for_user = PAYMENT_FAILED
            if error_details and isinstance(error_details, dict):
                error_name = error_details.get('name', 'Unknown Error')
                error_message = error_details.get('message', 'No specific message.')
                error_message_for_user += f" (Reason: {error_name} - {error_message})"
                logger.error(f"PayPal payment {paymentId} failed execution for user {user_id}. Details: {error_details}")
            else:
                logger.error(f"PayPal payment {paymentId} failed execution for user {user_id}. No specific error details.")
            
            if chat_id:
                await send_telegram_message(chat_id, error_message_for_user)
            else:
                logger.error(f"Chat ID not available for user {user_id}. Cannot send payment failed message.")
            return jsonify({'status': 'error', 'message': 'Payment execution failed.', 'details': error_details}), 500

    except Exception as e:
        logger.error(f"Error processing PayPal return: {e}", exc_info=True)
        # Use the determined chat_id if available, otherwise try user_id from URL
        final_chat_id = chat_id if chat_id else (int(user_id_from_url) if user_id_from_url else None)
        if final_chat_id:
            await send_telegram_message(final_chat_id, PAYMENT_FAILED + f" (Internal Error: {e})")
        return jsonify({'status': 'error', 'message': f'Internal Server Error: {e}'}), 500
