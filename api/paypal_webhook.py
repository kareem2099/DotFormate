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
    logger.error(f"Failed to import necessary modules for paypal_webhook: {e}. Simulating functions.")
    async def execute_paypal_payment(payment_id: str, payer_id: str):
        logging.info(f"Simulating execute_paypal_payment for {payment_id} with {payer_id}")
        return True # Simulate success
    async def update_user_data(user_id, data):
        logging.info(f"Simulating update_user_data for user {user_id} with {data}")
        pass
    async def get_user_by_paypal_payment_id(payment_id: str):
        logging.info(f"Simulating get_user_by_paypal_payment_id for {payment_id}")
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
    Vercel serverless function handler for PayPal webhooks.
    This function will be triggered by PayPal's webhook notifications.
    """
    if request.method != 'POST':
        return {
            'statusCode': 405,
            'body': 'Method Not Allowed'
        }

    try:
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

async def handler(request):
    """
    Vercel serverless function handler for PayPal webhooks.
    This function will be triggered by PayPal's webhook notifications.
    """
    if request.method != 'POST':
        return {
            'statusCode': 405,
            'body': 'Method Not Allowed'
        }

    try:
        # Vercel's request object might provide JSON directly or require parsing
        # This depends on the Vercel Python runtime version and configuration.
        # For simplicity, assuming request.json() or request.get_json() is available.
        # If not, you'd read request.body and parse it.
        body = await request.json() # Or request.get_json() or json.loads(request.body.decode('utf-8'))
        logger.info(f"Received PayPal webhook: {json.dumps(body)}")

        event_type = body.get('event_type')
        resource = body.get('resource', {})

        if event_type == 'PAYMENT.SALE.COMPLETED':
            payment_id = resource.get('id')
            payer_id = resource.get('payer', {}).get('payer_info', {}).get('payer_id')
            
            # You need a way to link this payment_id back to a user_id in your database.
            # This is crucial. The `create_paypal_payment` function currently passes user_id
            # in the return_url, but webhooks don't use that.
            # You'd typically store payment_id -> user_id mapping in your database
            # when you create the payment.
            
            # For this example, we'll assume user_id can be retrieved.
            # In a real system, you'd query your database:
            # user_id = get_user_id_from_payment_id(payment_id)
            user_id = 12345 # Placeholder: Replace with actual user ID retrieval logic

            if payment_id and payer_id and user_id:
                success = await execute_paypal_payment(payment_id, payer_id)
                if success:
                    await update_user_data(user_id, {'subscription_status': 'active'})
                    # You would need to send a message to the user via your Telegram bot.
                    # This requires your bot's token and chat_id.
                    # This part cannot be directly handled by a simple Vercel function
                    # without access to your Telegram bot's API.
                    # You might need to queue a message or call a separate bot API endpoint.
                    logger.info(f"PayPal payment {payment_id} successfully processed via webhook for user {user_id}.")
                    # await context.bot.send_message(chat_id=user_id, text=PAYMENT_SUCCESS) # This won't work directly here
                    return {
                        'statusCode': 200,
                        'body': 'Payment processed successfully.'
                    }
                else:
                    logger.error(f"PayPal payment {payment_id} failed execution via webhook for user {user_id}.")
                    # await context.bot.send_message(chat_id=user_id, text=PAYMENT_FAILED) # This won't work directly here
                    return {
                        'statusCode': 500,
                        'body': 'Payment execution failed.'
                    }
            else:
                logger.warning(f"Missing payment_id, payer_id, or user_id in webhook: {body}")
                return {
                    'statusCode': 400,
                    'body': 'Missing required payment details.'
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

# For local testing, you can run a simple HTTP server
if __name__ == '__main__':
    class PayPalWebhookHandler(BaseHTTPRequestHandler):
        async def do_POST(self):
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            # Simulate Vercel's request object
            class MockRequest:
                def __init__(self, body_data):
                    self._body_data = body_data
                
                async def json(self):
                    return json.loads(self._body_data.decode('utf-8'))
                
                @property
                def method(self):
                    return 'POST'

            mock_request = MockRequest(post_data)
            response = await handler(mock_request)
            
            self.send_response(response['statusCode'])
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response['body']).encode('utf-8'))

    # This part is for local testing only. Vercel handles the server.
    # You would run this locally to test the webhook logic.
    # Example: python -m http.server 8000
    # Then use ngrok or similar to expose it publicly for PayPal to hit.
    # httpd = HTTPServer(('localhost', 8000), PayPalWebhookHandler)
    # logger.info("Starting local PayPal webhook server on port 8000...")
    # httpd.serve_forever()
    pass # Do not run a local server in a Vercel environment
