import logging
import uuid
from telegram import Update
from telegram.ext import CallbackContext, ConversationHandler
from urllib.parse import urlencode

from database import save_user_info, get_user, increment_referrals_count

logger = logging.getLogger(__name__)

import os
BOT_USERNAME = os.getenv("BOT_USERNAME")

async def generate_unique_referral_code():
    """Generates a unique referral code."""
    while True:
        code = str(uuid.uuid4().hex)[:8] # Generate a short, unique code
        # In a real application, you'd check if this code already exists in the DB
        # For simplicity, we'll assume UUID collision is rare enough for now.
        # If you have a large user base, you might need a more robust check here.
        # For example:
        # existing_user = await get_user_by_referral_code(code)
        # if not existing_user:
        #     return code
        return code

async def handle_referral_start(update: Update, context: CallbackContext) -> None:
    """
    Handles the /start command, checking for a referral code.
    This function should be called by the main /start handler.
    """
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name
    last_name = update.effective_user.last_name

    # Check if the user already exists in the database
    existing_user = await get_user(user_id)

    referred_by_user_id = None
    referral_code_for_new_user = None

    if context.args and len(context.args) > 0:
        # Deep linking: /start referral_code
        referrer_code = context.args[0]
        referrer_user = None
        
        # Find the referrer by their referral code
        # This requires a new function in database.py: get_user_by_referral_code
        # For now, we'll simulate finding the referrer.
        # In a real scenario, you'd query the database for a user with this referral_code
        # For example: referrer_user = await get_user_by_referral_code(referrer_code)
        
        # Placeholder: In a real system, you'd fetch the referrer from DB
        # For demonstration, let's assume referrer_code is the referrer's user_id for simplicity
        # This is NOT how referral codes usually work, but for a quick demo, it's fine.
        # A proper implementation would involve a lookup by the actual referral_code.
        
        referrer_user = await get_user_by_referral_code(referrer_code)

        if referrer_user and referrer_user['user_id'] != user_id: # Prevent self-referral
            referred_by_user_id = referrer_user['user_id']
            logger.info(f"User {user_id} was referred by user {referred_by_user_id} with code {referrer_code}")
            
            # Increment referrer's count
            await increment_referrals_count(referred_by_user_id)
            
            # Notify referrer (optional)
            if context.bot:
                try:
                    await context.bot.send_message(
                        chat_id=referred_by_user_id,
                        text=f"🎉 Great news! Your friend @{username or first_name} just joined using your referral link!"
                    )
                except Exception as e:
                    logger.warning(f"Could not notify referrer {referred_by_user_id}: {e}")
        else:
            logger.info(f"Invalid or self-referral code received: {referrer_code}")

    if not existing_user:
        referral_code_for_new_user = await generate_unique_referral_code()
        logger.info(f"New user {user_id} assigned referral code: {referral_code_for_new_user}")
    elif not existing_user.get('referral_code'):
        # Assign a referral code if the existing user doesn't have one
        referral_code_for_new_user = await generate_unique_referral_code()
        logger.info(f"Existing user {user_id} assigned new referral code: {referral_code_for_new_user}")
    else:
        referral_code_for_new_user = existing_user['referral_code'] # Keep existing code

    # Save/update user info with referral data
    await save_user_info(
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        referral_code=referral_code_for_new_user,
        referred_by=referred_by_user_id
    )

async def referral_command(update: Update, context: CallbackContext) -> int:
    """Handles the /referral command, sending the user their referral link."""
    user_id = update.effective_user.id
    user = await get_user(user_id)

    if not user or not user.get('referral_code'):
        # This should ideally not happen if handle_referral_start is always called
        # but as a fallback, generate one now.
        referral_code = await generate_unique_referral_code()
        await save_user_info(
            user_id=user_id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name,
            referral_code=referral_code
        )
        user = await get_user(user_id) # Re-fetch user with new code
    else:
        referral_code = user['referral_code']

    # Construct the referral link
    # Ensure BOT_USERNAME is correctly set
    if BOT_USERNAME == "your_bot_username":
        await update.message.reply_text(
            "Please set your bot's username in `referral_system.py` to generate a proper referral link."
        )
        return ConversationHandler.END

    referral_link = f"https://t.me/{BOT_USERNAME}?start={referral_code}"
    referrals_count = user.get('referrals_count', 0)

    message_text = (
        f"✨ Your personal referral code is: `{referral_code}`\n\n"
        f"🔗 Share this link with your friends:\n`{referral_link}`\n\n"
        f"👥 You have successfully referred: *{referrals_count}* users!\n\n"
        "Every friend who joins using your link helps you unlock future rewards! 🎁"
    )
    await update.message.reply_text(message_text, parse_mode='Markdown')
    return ConversationHandler.END

# Helper function for get_user_by_referral_code (should be in database.py)
async def get_user_by_referral_code(referral_code: str):
    from database import MongoDBManager
    db_manager = MongoDBManager()
    db = db_manager.get_db()
    if db is None:
        logger.error("Database connection not available to get user by referral code.")
        return None
    try:
        return db.users.find_one({"referral_code": referral_code})
    except Exception as e:
        logger.error(f"Error getting user by referral code {referral_code}: {e}")
        return None
