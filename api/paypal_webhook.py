from flask import Flask, request, jsonify
import os
import logging
import requests
import json

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

@app.route('/api/paypal_webhook', methods=['POST'])
async def paypal_webhook_handler():
    """
    Vercel serverless function handler for PayPal webhooks.
    This function will be triggered by PayPal's webhook notifications.
    """
    try:
        # Parse request body
        body = request.json
        
        logger.info(f"Received PayPal webhook: {json.dumps(body)}")

        event_type = body.get('event_type')
        resource = body.get('resource', {})
        payment_state = resource.get('state') # Get the payment state

        # Handle PAYMENTS.PAYMENT.CREATED event
        if event_type == 'PAYMENTS.PAYMENT.CREATED':
            payment_id = resource.get('id')
            payer_id = resource.get('payer', {}).get('payer_info', {}).get('payer_id')
            
            user_data = await get_user_by_paypal_payment_id(payment_id)
            user_id = user_data.get('user_id') if user_data else None
            chat_id = user_data.get('chat_id') if user_data else None

            if payment_id and payer_id and user_id and chat_id:
                if payment_state == 'approved' or payment_state == 'created':
                    success = await execute_paypal_payment(payment_id, payer_id)
                    if success:
                        await update_user_data(user_id, {'subscription_status': 'active'})
                        await send_telegram_message(chat_id, PAYMENT_SUCCESS)
                        logger.info(f"PayPal payment {payment_id} successfully processed via webhook for user {user_id}.")
                        return jsonify({'status': 'success', 'message': 'Payment processed successfully.'}), 200
                    else:
                        await send_telegram_message(chat_id, PAYMENT_FAILED)
                        logger.error(f"PayPal payment {payment_id} failed execution via webhook for user {user_id}.")
                        return jsonify({'status': 'error', 'message': 'Payment execution failed.'}), 500
                elif payment_state == 'failed':
                    await send_telegram_message(chat_id, PAYMENT_FAILED + " (Payment failed at PayPal)")
                    logger.warning(f"PayPal payment {payment_id} failed at PayPal for user {user_id}. State: {payment_state}")
                    return jsonify({'status': 'info', 'message': 'Payment failed at PayPal, no execution needed.'}), 200
                else:
                    logger.info(f"Received PAYMENTS.PAYMENT.CREATED webhook with unhandled state: {payment_state} for payment {payment_id}")
                    return jsonify({'status': 'info', 'message': f'Event type {event_type} with state {payment_state} received, no action taken.'}), 200
            else:
                logger.warning(f"Missing payment_id, payer_id, user_id, or chat_id in webhook: {body}")
                if chat_id:
                    await send_telegram_message(chat_id, PAYMENT_FAILED + " (Missing payment details in webhook)")
                return jsonify({'status': 'error', 'message': 'Missing required payment details or user not found.'}), 400
        else:
            logger.info(f"Received unhandled PayPal webhook event: {event_type}")
            return jsonify({'status': 'info', 'message': f'Event type {event_type} received, no action taken.'}), 200

    except json.JSONDecodeError:
        logger.error("Invalid JSON received in webhook request.")
        return jsonify({'status': 'error', 'message': 'Invalid JSON'}), 400
    except Exception as e:
        logger.error(f"Error processing PayPal webhook: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': f'Internal Server Error: {e}'}), 500
