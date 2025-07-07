from flask import Flask, request, jsonify, redirect
import os
import logging

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Assuming these modules are accessible in the Vercel environment
from paypal_integration import execute_paypal_payment
from database import update_user_data, get_user_by_paypal_payment_id
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
    
    try:
        user_id = request.args.get('user_id')
        paymentId = request.args.get('paymentId')
        token = request.args.get('token')
        PayerID = request.args.get('PayerID')

        if not all([user_id, paymentId, token, PayerID]):
            logger.warning("Missing required PayPal return parameters.")
            return jsonify({'status': 'error', 'message': 'Missing required parameters.'}), 400

        user_id = int(user_id)

        # Execute the PayPal payment
        success, error_details = await execute_paypal_payment(paymentId, PayerID)

        if success:
            await update_user_data(user_id, {'subscription_status': 'active'})
            await send_telegram_message(user_id, PAYMENT_SUCCESS)
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
            
            await send_telegram_message(user_id, error_message_for_user)
            return jsonify({'status': 'error', 'message': 'Payment execution failed.', 'details': error_details}), 500

    except Exception as e:
        logger.error(f"Error processing PayPal return: {e}", exc_info=True)
        user_id_in_scope = locals().get('user_id')
        if user_id_in_scope:
            await send_telegram_message(user_id_in_scope, PAYMENT_FAILED + f" (Internal Error: {e})")
        return jsonify({'status': 'error', 'message': f'Internal Server Error: {e}'}), 500
