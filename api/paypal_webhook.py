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
from database import update_user_data, get_user_by_paypal_payment_id, get_user, increment_referral_balance, update_user_premium_status
from constants import PAYMENT_SUCCESS, PAYMENT_FAILED
from datetime import datetime, timedelta
from notification_utils import send_notification_to_channel # Import for notifications

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
                    success, error_details = await execute_paypal_payment(payment_id, payer_id)
                    if success:
                        premium_type = user_data.get('premium_type_from_payment')
                        premium_expiry_date = None
                        is_premium = True

                        if premium_type == "weekly":
                            premium_expiry_date = datetime.utcnow() + timedelta(weeks=1)
                        elif premium_type == "monthly":
                            premium_expiry_date = datetime.utcnow() + timedelta(days=30) # Approx month
                        elif premium_type == "half_yearly":
                            premium_expiry_date = datetime.utcnow() + timedelta(days=182) # Approx half year
                        elif premium_type == "yearly":
                            premium_expiry_date = datetime.utcnow() + timedelta(days=365) # Approx year
                        elif premium_type == "lifetime":
                            premium_expiry_date = None # Lifetime premium, no expiry date

                        await update_user_premium_status(user_id, is_premium, premium_type, premium_expiry_date)
                        await send_telegram_message(chat_id, PAYMENT_SUCCESS)
                        logger.info(f"PayPal payment {payment_id} successfully processed via webhook for user {user_id}. Premium type: {premium_type}, Expiry: {premium_expiry_date}")

                        # Send notification to admin channel for new premium purchase
                        payment_amount_obj = resource.get('transactions', [{}])[0].get('amount', {})
                        payment_value = float(payment_amount_obj.get('total', '0.0'))
                        notification_message = (
                            f"✅ *New Premium Purchase!* ✅\n\n"
                            f"👤 User ID: {user_id}\n"
                            f"💳 Payment ID: {payment_id}\n"
                            f"✨ Premium Type: {premium_type}\n"
                            f"💲 Amount: ${payment_value:.2f}\n"
                            f"🗓️ Expiry: {premium_expiry_date.strftime('%Y-%m-%d %H:%M:%S UTC') if premium_expiry_date else 'Lifetime'}"
                        )
                        await send_notification_to_channel(notification_message, parse_mode='Markdown')

                        # Check if the user was referred and award the referrer
                        referred_user_data = await get_user(user_id)
                        referred_by_user_id = referred_user_data.get('referred_by')
                        
                        if referred_by_user_id:
                            referral_reward = payment_value * 0.20 # 20% of the payment

                            if referral_reward > 0:
                                await increment_referral_balance(referred_by_user_id, referral_reward)
                                referrer_user = await get_user(referred_by_user_id)
                                referrer_username = referrer_user.get('username') or referrer_user.get('first_name')
                                if referrer_user and referrer_user.get('chat_id'):
                                    await send_telegram_message(
                                        referrer_user['chat_id'],
                                        f"🎉 Great news! Your referred friend just made a payment of ${payment_value:.2f} and you earned ${referral_reward:.2f} in referral rewards! Your new balance is ${referrer_user.get('referral_balance', 0.0) + referral_reward:.2f}."
                                    )
                                logger.info(f"Awarded {referral_reward:.2f} to referrer {referred_by_user_id} for payment {payment_id}.")
                                # Also send notification to admin channel for referral reward
                                referral_notification_message = (
                                    f"🎁 *Referral Reward Earned!* 🎁\n\n"
                                    f"👤 Referrer User ID: {referred_by_user_id} (@{referrer_username or 'N/A'})\n"
                                    f"💸 Reward Amount: ${referral_reward:.2f}\n"
                                    f"🔗 Referred User ID: {user_id}\n"
                                    f"💳 Payment ID: {payment_id}"
                                )
                                await send_notification_to_channel(referral_notification_message, parse_mode='Markdown')
                        
                        return jsonify({'status': 'success', 'message': 'Payment processed successfully.'}), 200
                    else:
                        await send_telegram_message(chat_id, f"{PAYMENT_FAILED} Details: {error_details.get('message', 'Unknown error')}")
                        logger.error(f"PayPal payment {payment_id} failed execution via webhook for user {user_id}. Error: {error_details}")
                        # Notification for failed execution
                        notification_message = (
                            f"❌ *PayPal Payment Execution Failed!* ❌\n\n"
                            f"👤 User ID: {user_id}\n"
                            f"💳 Payment ID: {payment_id}\n"
                            f"🚨 Error: {error_details.get('name', 'N/A')} - {error_details.get('message', 'Unknown error')}"
                        )
                        await send_notification_to_channel(notification_message, parse_mode='Markdown')
                        return jsonify({'status': 'error', 'message': 'Payment execution failed.', 'details': error_details}), 500
                elif payment_state == 'failed':
                    await send_telegram_message(chat_id, PAYMENT_FAILED + " (Payment failed at PayPal)")
                    logger.warning(f"PayPal payment {payment_id} failed at PayPal for user {user_id}. State: {payment_state}")
                    # Notification for payment failed at PayPal
                    notification_message = (
                        f"⚠️ *PayPal Payment Failed at PayPal!* ⚠️\n\n"
                        f"👤 User ID: {user_id}\n"
                        f"💳 Payment ID: {payment_id}\n"
                        f"📊 State: {payment_state}"
                    )
                    await send_notification_to_channel(notification_message, parse_mode='Markdown')
                    return jsonify({'status': 'info', 'message': 'Payment failed at PayPal, no execution needed.'}), 200
                else:
                    logger.info(f"Received PAYMENTS.PAYMENT.CREATED webhook with unhandled state: {payment_state} for payment {payment_id}")
                    # Notification for unhandled state
                    notification_message = (
                        f"ℹ️ *Unhandled PayPal Payment State* ℹ️\n\n"
                        f"💳 Payment ID: {payment_id}\n"
                        f"📊 State: {payment_state}\n"
                        f"EventType: {event_type}"
                    )
                    await send_notification_to_channel(notification_message, parse_mode='Markdown')
                    return jsonify({'status': 'info', 'message': f'Event type {event_type} with state {payment_state} received, no action taken.'}), 200
            else:
                logger.warning(f"Missing payment_id, payer_id, user_id, or chat_id in webhook: {body}")
                if chat_id:
                    await send_telegram_message(chat_id, PAYMENT_FAILED + " (Missing payment details in webhook)")
                # Notification for missing payment details
                notification_message = (
                    f"🚨 *Missing PayPal Webhook Details!* 🚨\n\n"
                    f"Payload: `{json.dumps(body)}`"
                )
                await send_notification_to_channel(notification_message, parse_mode='Markdown')
                return jsonify({'status': 'error', 'message': 'Missing required payment details or user not found.'}), 400
        else:
            logger.info(f"Received unhandled PayPal webhook event: {event_type}")
            # Notification for unhandled event type
            notification_message = (
                f"ℹ️ *Unhandled PayPal Webhook Event!* ℹ️\n\n"
                f"Event Type: {event_type}\n"
                f"Payload: `{json.dumps(body)}`"
            )
            await send_notification_to_channel(notification_message, parse_mode='Markdown')
            return jsonify({'status': 'info', 'message': f'Event type {event_type} received, no action taken.'}), 200

    except json.JSONDecodeError:
        logger.error("Invalid JSON received in webhook request.")
        # Notification for invalid JSON
        notification_message = (
            f"🚨 *Invalid JSON in PayPal Webhook!* 🚨\n\n"
            f"Received non-JSON payload."
        )
        await send_notification_to_channel(notification_message, parse_mode='Markdown')
        return jsonify({'status': 'error', 'message': 'Invalid JSON'}), 400
    except Exception as e:
        logger.error(f"Error processing PayPal webhook: {e}", exc_info=True)
        # Notification for general error
        notification_message = (
            f"🔥 *Critical Error in PayPal Webhook!* 🔥\n\n"
            f"🚨 Error: {type(e).__name__}: {e}\n"
            f"Traceback: (See logs for full traceback)\n"
            f"Payload: `{json.dumps(body)}`"
        )
        await send_notification_to_channel(notification_message, parse_mode='Markdown')
        return jsonify({'status': 'error', 'message': f'Internal Server Error: {e}'}), 500
