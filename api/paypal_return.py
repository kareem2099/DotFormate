import os
import json
import logging
import requests
import asyncio
from urllib.parse import urlparse, parse_qs
from http import HTTPStatus
from vercel_python import Response

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create a console handler to see logs
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

from paypal_integration import execute_paypal_payment
from database import update_user_data
from constants import PAYMENT_SUCCESS, PAYMENT_FAILED

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

def create_success_page(user_id: int):
    """Create a simple HTML success page"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Payment Successful</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: Arial, sans-serif;
                text-align: center;
                margin: 50px;
                background-color: #f0f8ff;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                background-color: white;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            .success {{
                color: #4CAF50;
                font-size: 24px;
                margin-bottom: 20px;
            }}
            .info {{
                color: #666;
                font-size: 16px;
                margin-bottom: 30px;
            }}
            .telegram-link {{
                background-color: #0088cc;
                color: white;
                padding: 12px 24px;
                text-decoration: none;
                border-radius: 5px;
                font-size: 16px;
                display: inline-block;
            }}
            .telegram-link:hover {{
                background-color: #006699;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="success">✅ Payment Successful!</div>
            <div class="info">
                Your payment has been processed successfully. You will receive a confirmation message in your Telegram bot shortly.
            </div>
            <a href="tg://resolve?domain=your_bot_username" class="telegram-link">
                Return to Telegram Bot
            </a>
        </div>
        <script>
            // Auto-redirect to Telegram after 3 seconds
            setTimeout(function() {{
                window.location.href = "tg://resolve?domain=FormaterBot";
            }}, 3000);
        </script>
    </body>
    </html>
    """

def create_error_page(error_message: str):
    """Create a simple HTML error page"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Payment Error</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: Arial, sans-serif;
                text-align: center;
                margin: 50px;
                background-color: #fff8f8;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                background-color: white;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            .error {{
                color: #f44336;
                font-size: 24px;
                margin-bottom: 20px;
            }}
            .info {{
                color: #666;
                font-size: 16px;
                margin-bottom: 30px;
            }}
            .telegram-link {{
                background-color: #0088cc;
                color: white;
                padding: 12px 24px;
                text-decoration: none;
                border-radius: 5px;
                font-size: 16px;
                display: inline-block;
            }}
            .telegram-link:hover {{
                background-color: #006699;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="error">❌ Payment Error</div>
            <div class="info">
                There was an issue processing your payment: {error_message}
                <br><br>
                Please try again or contact support if the problem persists.
            </div>
            <a href="tg://resolve?domain=your_bot_username" class="telegram-link">
                Return to Telegram Bot
            </a>
        </div>
    </body>
    </html>
    """

def handler(request):
    """
    Vercel serverless function handler for PayPal return URL (browser redirect).
    This function is called when PayPal redirects the user's browser back to your app.
    """
    
    async def async_handler():
        logger.info(f"PayPal return handler called with method: {request.method}")
        logger.info(f"Request URL: {getattr(request, 'url', 'URL not available')}")
        
        if request.method != 'GET':
            return Response(
                status_code=HTTPStatus.METHOD_NOT_ALLOWED,
                headers={'Content-Type': 'text/html'},
                body=create_error_page('Method Not Allowed')
            )

        try:
            # Extract query parameters from the request URL
            if hasattr(request, 'url'):
                query_params = parse_qs(urlparse(request.url).query)
            elif hasattr(request, 'args'):
                # Alternative way to get query params
                query_params = dict(request.args)
                # Convert single values to lists for consistency
                query_params = {k: [v] if not isinstance(v, list) else v for k, v in query_params.items()}
            else:
                logger.error("Cannot extract query parameters from request")
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'text/html'},
                    'body': create_error_page('Cannot parse request parameters')
                }
            
            user_id = query_params.get('user_id', [None])[0]
            payment_id = query_params.get('paymentId', [None])[0]
            payer_id = query_params.get('PayerID', [None])[0]
            token = query_params.get('token', [None])[0]

            logger.info(f"Extracted parameters - user_id: {user_id}, payment_id: {payment_id}, payer_id: {payer_id}, token: {token}")

            if not all([user_id, payment_id, payer_id]):
                error_msg = "Missing required parameters in PayPal return URL"
                logger.warning(error_msg)
                
                # Attempt to notify user if user_id is available
                if user_id:
                    try:
                        await send_telegram_message(int(user_id), PAYMENT_FAILED + " (Missing payment details)")
                    except Exception as e:
                        logger.error(f"Failed to send error notification: {e}")
                
                return Response(
                    status_code=HTTPStatus.BAD_REQUEST,
                    headers={'Content-Type': 'text/html'},
                    body=create_error_page(error_msg)
                )

            # Convert user_id to int
            try:
                user_id = int(user_id)
            except ValueError:
                error_msg = "Invalid user ID format"
                logger.error(error_msg)
                return Response(
                    status_code=HTTPStatus.BAD_REQUEST,
                    headers={'Content-Type': 'text/html'},
                    body=create_error_page(error_msg)
                )

            logger.info(f"Processing PayPal payment execution for user {user_id}")
            
            # Execute PayPal payment
            success = await execute_paypal_payment(payment_id, payer_id)

            if success:
                # Update user's subscription status in the database
                try:
                    await update_user_data(user_id, {'subscription_status': 'active'})
                    logger.info(f"Updated user {user_id} subscription status to active")
                except Exception as e:
                    logger.error(f"Failed to update user data: {e}")
                
                # Send success message to Telegram
                try:
                    await send_telegram_message(user_id, PAYMENT_SUCCESS)
                    logger.info(f"Sent success message to user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to send success message: {e}")
                
                logger.info(f"PayPal payment {payment_id} successfully processed for user {user_id}")
                
                return Response(
                    status_code=HTTPStatus.OK,
                    headers={'Content-Type': 'text/html'},
                    body=create_success_page(user_id)
                )
            else:
                # Send failure message to Telegram
                try:
                    await send_telegram_message(user_id, PAYMENT_FAILED)
                    logger.info(f"Sent failure message to user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to send failure message: {e}")
                
                logger.error(f"PayPal payment {payment_id} failed execution for user {user_id}")
                return Response(
                    status_code=HTTPStatus.OK,
                    headers={'Content-Type': 'text/html'},
                    body=create_error_page('Payment execution failed')
                )

        except Exception as e:
            logger.error(f"Error processing PayPal return: {e}", exc_info=True)
            
            # Attempt to notify user if user_id is available
            if 'user_id' in locals() and user_id:
                try:
                    await send_telegram_message(user_id, PAYMENT_FAILED + f" (Error: {str(e)})")
                except Exception as notify_error:
                    logger.error(f"Failed to send error notification: {notify_error}")
            
            return Response(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                headers={'Content-Type': 'text/html'},
                body=create_error_page(f'Internal Server Error: {str(e)}')
            )
    
    # Run the async function
    try:
        return asyncio.run(async_handler())
    except Exception as e:
        logger.error(f"Failed to run async handler: {e}", exc_info=True)
        return Response(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            headers={'Content-Type': 'text/html'},
            body=create_error_page(f'Handler Error: {str(e)}')
        )

# Vercel requires this export
__all__ = ['handler']
