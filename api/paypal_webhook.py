import os
import logging

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

async def send_telegram_message(chat_id: int, text: str):
    """Sends a message to a Telegram user using the Bot API."""
    import requests # Lazy import requests
    import json # Lazy import json
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

async def handler(request):
    """
    Vercel serverless function handler for PayPal webhooks.
    This function will be triggered by PayPal's webhook notifications.
    """
    # Lazy import modules to avoid top-level execution issues
    from paypal_integration import execute_paypal_payment
    from database import update_user_data, get_user_by_paypal_payment_id
    from constants import PAYMENT_SUCCESS, PAYMENT_FAILED
    import json # Ensure json is available if not already imported by send_telegram_message

    if request.method != 'POST':
        return {
            'statusCode': 405,
            'body': 'Method Not Allowed'
        }

    try:
        # Parse request body
        # Vercel's request object for webhooks typically provides the body directly
        body = await request.json()
        
        logger.info(f"Received PayPal webhook: {json.dumps(body)}")

        event_type = body.get('event_type')
        resource = body.get('resource', {})

        if event_type == 'PAYMENT.SALE.COMPLETED':
            payment_id = resource.get('id')
            payer_id = resource.get('payer', {}).get('payer_info', {}).get('payer_id')
            
            user_data = await get_user_by_paypal_payment_id(payment_id)
            user_id = user_data.get('user_id') if user_data else None
            chat_id = user_data.get('chat_id') if user_data else None

            if payment_id and payer_id and user_id and chat_id:
                success = await execute_paypal_payment(payment_id, payer_id)
                if success:
                    await update_user_data(user_id, {'subscription_status': 'active'})
                    await send_telegram_message(chat_id, PAYMENT_SUCCESS)
                    logger.info(f"PayPal payment {payment_id} successfully processed via webhook for user {user_id}.")
                    return {
                        'statusCode': 200,
                        'body': 'Payment processed successfully.'
                    }
                else:
                    await send_telegram_message(chat_id, PAYMENT_FAILED)
                    logger.error(f"PayPal payment {payment_id} failed execution via webhook for user {user_id}.")
                    return {
                        'statusCode': 500,
                        'body': 'Payment execution failed.'
                    }
            else:
                logger.warning(f"Missing payment_id, payer_id, user_id, or chat_id in webhook: {body}")
                # Attempt to notify if chat_id is available from user_data even if other details are missing
                if chat_id:
                    await send_telegram_message(chat_id, PAYMENT_FAILED + " (Missing payment details in webhook)")
                return {
                    'statusCode': 400,
                    'body': 'Missing required payment details or user not found.'
                }
        else:
            logger.info(f"Received non-completion PayPal webhook event: {event_type}")
            return {
                'statusCode': 200,
                'body': f'Event type {event_type} received, no action taken.'
            }

    except json.JSONDecodeError:
        logger.error("Invalid JSON received in webhook request.")
        return {
            'statusCode': 400,
            'body': 'Invalid JSON'
        }
    except Exception as e:
        logger.error(f"Error processing PayPal webhook: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': f'Internal Server Error: {e}'
        }
