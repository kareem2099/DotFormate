import os
import paypalrestsdk
from telegram import Update
from telegram.ext import CallbackContext
from database import get_user, update_user_data
import os
import paypalrestsdk
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler
from telegram.error import BadRequest # Import BadRequest
from database import get_user, update_user_data
from constants import (
    PAYMENT_SUCCESS, PAYMENT_FAILED, PAYMENT_PENDING,
    PAYMENT_OPTIONS, PAYMENT_METHODS,
    SELECT_PAYMENT_OPTION, SELECT_PAYMENT_METHOD, MAIN_MENU
)

logger = logging.getLogger(__name__)

# Configure PayPal SDK
paypalrestsdk.configure({
    "mode": os.getenv("PAYPAL_MODE"),
    "client_id": os.getenv("PAYPAL_CLIENT_ID"),
    "client_secret": os.getenv("PAYPAL_CLIENT_SECRET")
})

async def create_paypal_payment(user_id: int, amount: str, description: str):
    """
    Creates a PayPal payment and returns the approval URL.
    """
    payment = paypalrestsdk.Payment({
        "intent": "sale",
        "payer": {
            "payment_method": "paypal"
        },
        "redirect_urls": {
            "return_url": f"https://your_bot_webhook_url/paypal_return?user_id={user_id}", # Placeholder, needs to be a real webhook
            "cancel_url": f"https://your_bot_webhook_url/paypal_cancel?user_id={user_id}"  # Placeholder
        },
        "transactions": [{
            "item_list": {
                "items": [{
                    "name": description,
                    "sku": "item",
                    "price": amount,
                    "currency": "USD",
                    "quantity": "1"
                }]
            },
            "amount": {
                "total": amount,
                "currency": "USD"
            },
            "description": description
        }]
    })

    if payment.create():
        for link in payment.links:
            if link.rel == "approval_url":
                return link.href
    logger.info(f"Failed to create PayPal payment: {payment.error}")
    return None

async def execute_paypal_payment(payment_id: str, payer_id: str):
    """
    Executes a PayPal payment.
    """
    payment = paypalrestsdk.Payment.find(payment_id)
    if payment.execute({"payer_id": payer_id}):
        return True
    logger.error(f"Failed to execute PayPal payment: {payment.error}")
    return False

async def handle_payment_command(update: Update, context: CallbackContext):
    """
    Starts the payment flow by presenting subscription options.
    """
    logger.info(f"User {update.effective_user.id} initiated /payment command.")
    keyboard = []
    for key, value in PAYMENT_OPTIONS.items():
        keyboard.append([InlineKeyboardButton(f"{value['description']} - ${value['amount']}", callback_data=f"payment_option_{key}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please choose a payment option:", reply_markup=reply_markup)
    return SELECT_PAYMENT_OPTION

async def handle_payment_option_selection(update: Update, context: CallbackContext):
    """
    Handles the user's selection of a payment option and presents payment methods.
    """
    query = update.callback_query
    await query.answer()
    
    option_key = query.data.replace("payment_option_", "")
    selected_option = PAYMENT_OPTIONS.get(option_key)
    logger.info(f"User {query.from_user.id} selected payment option: {option_key}")

    if not selected_option:
        logger.warning(f"Invalid payment option selected by user {query.from_user.id}: {option_key}")
        await query.edit_message_text("Invalid payment option. Please try again.")
        return MAIN_MENU

    context.user_data['selected_payment_option'] = selected_option

    keyboard = []
    for key, value in PAYMENT_METHODS.items():
        keyboard.append([InlineKeyboardButton(value, callback_data=f"payment_method_{key}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await query.edit_message_text(
            f"You selected: {selected_option['description']} (${selected_option['amount']}).\n"
            "Please choose your preferred payment method:",
            reply_markup=reply_markup
        )
        logger.info(f"Successfully edited message for payment option selection for user {query.from_user.id}.")
    except BadRequest as e:
        logger.error(f"BadRequest when editing message for payment option selection for user {query.from_user.id}: {e}")
        # If edit fails, send a new message instead of failing silently
        await query.message.reply_text("An error occurred while updating the message. Please try again.", reply_markup=reply_markup)
        return SELECT_PAYMENT_METHOD # Stay in the same state to allow re-selection
    except Exception as e:
        logger.error(f"Unexpected error when editing message for payment option selection for user {query.from_user.id}: {e}")
        await query.message.reply_text("An unexpected error occurred. Please try again.", reply_markup=reply_markup)
        return SELECT_PAYMENT_METHOD # Stay in the same state to allow re-selection
    return SELECT_PAYMENT_METHOD

async def handle_payment_method_selection(update: Update, context: CallbackContext):
    """
    Handles the user's selection of a payment method and initiates the payment.
    """
    query = update.callback_query
    await query.answer()

    method_key = query.data.replace("payment_method_", "")
    selected_method = PAYMENT_METHODS.get(method_key)
    selected_option = context.user_data.get('selected_payment_option')
    logger.info(f"User {query.from_user.id} selected payment method: {method_key}")

    if not selected_method or not selected_option:
        logger.warning(f"Invalid payment method or option for user {query.from_user.id}. Method: {method_key}, Option: {selected_option}")
        await query.edit_message_text("Invalid payment method or option. Please try again.")
        return MAIN_MENU

    user_id = query.from_user.id
    amount = selected_option['amount']
    description = selected_option['description']

    if method_key == "paypal":
        approval_url = await create_paypal_payment(user_id, amount, description)
        if approval_url:
            try:
                await query.edit_message_text(
                    f"Please click the link to complete your PayPal payment: {approval_url}\n"
                    "After completing the payment, you will be notified here."
                )
                logger.info(f"Successfully edited message for PayPal payment link for user {user_id}.")
            except BadRequest as e:
                logger.error(f"BadRequest when editing message for PayPal payment link for user {user_id}: {e}")
                await query.message.reply_text("An error occurred while updating the message. Please try again.")
                return ConversationHandler.END # End conversation if we can't edit
            except Exception as e:
                logger.error(f"Unexpected error when editing message for PayPal payment link for user {user_id}: {e}")
                await query.message.reply_text("An unexpected error occurred. Please try again.")
                return ConversationHandler.END # End conversation if we can't edit
        else:
            await query.edit_message_text("Failed to create PayPal payment. Please try again later.")
    elif method_key in ["cliq", "vodafone_cash", "we_pay", "instapay"]:
        # For non-PayPal methods, provide instructions
        message = f"To complete your payment of ${amount} for {description} via {selected_method}:\n\n"
        if method_key == "cliq":
            message += "Please send the amount to our Cliq account: [Your Cliq Number/ID]\n"
            message += "After sending, please reply to this message with a screenshot of the transaction or the transaction ID for verification."
        elif method_key == "vodafone_cash":
            message += "Please send the amount to our Vodafone Cash number: [Your Vodafone Cash Number]\n"
            message += "After sending, please reply to this message with a screenshot of the transaction or the transaction ID for verification."
        elif method_key == "we_pay":
            message += "Please send the amount to our We Pay number: [Your We Pay Number]\n"
            message += "After sending, please reply to this message with a screenshot of the transaction or the transaction ID for verification."
        elif method_key == "instapay":
            message += "Please send the amount to our Instapay ID: [Your Instapay ID]\n"
            message += "After sending, please reply to this message with a screenshot of the transaction or the transaction ID for verification."
        
        try:
            await query.edit_message_text(message)
            logger.info(f"Successfully edited message for manual payment instructions for user {user_id}.")
        except BadRequest as e:
            logger.error(f"BadRequest when editing message for manual payment instructions for user {user_id}: {e}")
            await query.message.reply_text("An error occurred while updating the message. Please try again.")
            return ConversationHandler.END # End conversation if we can't edit
        except Exception as e:
            logger.error(f"Unexpected error when editing message for manual payment instructions for user {user_id}: {e}")
            await query.message.reply_text("An unexpected error occurred. Please try again.")
            return ConversationHandler.END # End conversation if we can't edit
    else:
        logger.warning(f"Unsupported payment method selected by user {user_id}: {method_key}")
        await query.edit_message_text("Unsupported payment method. Please try again.")

    return ConversationHandler.END # End conversation for now, or transition to a waiting state


async def paypal_return_handler(update: Update, context: CallbackContext):
    """
    Handles the return from PayPal after a user approves a payment.
    This would typically be a webhook endpoint. For a Telegram bot,
    this might be simulated or require a separate web server.
    """
    # This handler would be triggered by a webhook from PayPal.
    # For now, it's a placeholder.
    # In a real scenario, you'd parse the request from PayPal,
    # extract payment_id and payer_id, and then execute the payment.
    
    # Example of how you might get data if it was a callback query (less ideal for webhooks)
    query = update.callback_query
    if query:
        user_id = int(query.data.split('_')[1]) # Assuming data format like "paypal_return_USER_ID_PAYMENT_ID_PAYER_ID"
        payment_id = query.data.split('_')[2]
        payer_id = query.data.split('_')[3]
        logger.info(f"PayPal return callback received for user {user_id}, payment {payment_id}")
    else:
        logger.warning("PayPal return handler called without callback query data.")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Payment confirmation is usually handled automatically. "
                 "If you completed the payment, please wait for confirmation."
        )
        return

    success = await execute_paypal_payment(payment_id, payer_id)

    if success:
        # Update user's balance or subscription status in the database
        # For example: await update_user_data(user_id, {'balance': new_balance})
        logger.info(f"PayPal payment {payment_id} successful for user {user_id}.")
        await context.bot.send_message(chat_id=user_id, text=PAYMENT_SUCCESS)
    else:
        logger.error(f"PayPal payment {payment_id} failed for user {user_id}.")
        await context.bot.send_message(chat_id=user_id, text=PAYMENT_FAILED)

async def paypal_cancel_handler(update: Update, context: CallbackContext):
    """
    Handles the cancellation from PayPal after a user cancels a payment.
    This would typically be a webhook endpoint.
    """
    # This handler would be triggered by a webhook from PayPal.
    # For now, it's a placeholder.
    query = update.callback_query
    if query:
        user_id = int(query.data.split('_')[1]) # Assuming data format like "paypal_cancel_USER_ID"
        logger.info(f"PayPal cancel callback received for user {user_id}.")
    else:
        logger.warning("PayPal cancel handler called without callback query data.")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Payment cancellation is usually handled automatically. "
                 "If you cancelled, no action is needed."
        )
        return

    await context.bot.send_message(chat_id=user_id, text=PAYMENT_PENDING) # Or a specific cancellation message

async def handle_payment_confirmation_file(update: Update, context: CallbackContext) -> int:
    """
    Handles incoming files (screenshots/documents) for manual payment confirmation.
    """
    logger.info(f"User {update.effective_user.id} sent a file for payment confirmation.")
    
    file_id = None
    file_name = None
    mime_type = None

    if update.message.document:
        file_id = update.message.document.file_id
        file_name = update.message.document.file_name
        mime_type = update.message.document.mime_type
    elif update.message.photo:
        file_id = update.message.photo[-1].file_id # Get the largest photo
        file_name = f"photo_{file_id}.jpg" # Generic name for photos
        mime_type = "image/jpeg" # Assume JPEG for simplicity
    
    if not file_id:
        await update.message.reply_text("Please send a valid image or document for payment confirmation.")
        return SELECT_PAYMENT_METHOD # Stay in payment flow

    temp_dir = None
    downloaded_path = None
    try:
        temp_dir = tempfile.mkdtemp()
        downloaded_path = os.path.join(temp_dir, file_name)
        new_file = await context.bot.get_file(file_id)
        await new_file.download_to_drive(downloaded_path)

        user = update.effective_user
        notification_message = (
            f"💰 New Payment Confirmation Received 💰\n\n"
            f"👤 User: {user.full_name} (ID: {user.id})\n"
            f"📁 File: {file_name}\n"
            f"🆔 File ID: {file_id}\n"
            f"MIME Type: {mime_type}\n\n"
            f"Please review the attached file for payment verification."
        )
        await send_admin_notification(context, notification_message, document_path=downloaded_path)
        
        await update.message.reply_text(
            "Thank you! Your payment confirmation has been received. "
            "We will verify it shortly and update your subscription status. "
            "You will receive a notification once confirmed. ⏳"
        )
        return ConversationHandler.END # End the conversation after receiving confirmation
    except Exception as e:
        logger.error(f"Error handling payment confirmation file: {e}")
        await update.message.reply_text(f"An error occurred while processing your payment confirmation: {e} 💔 Please try again.")
        return ConversationHandler.END
    finally:
        if downloaded_path and os.path.exists(downloaded_path):
            os.remove(downloaded_path)
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Could not delete temp directory {temp_dir}: {e}")
