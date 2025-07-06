from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, ConversationHandler
import logging

# Import centralized utilities and constants
from utility_handlers import start, help_command, send_or_edit_message
from constants import MAIN_MENU, SELECT_CONVERSION_TYPE, SELECT_PAGES, SELECT_OUTPUT_FORMAT, SELECT_IMAGE_FORMAT

# Import flow starters from conversation_handlers
from conversation_handlers import (
    ocr_flow_start, merge_pdf_flow_start, split_pdf_flow_start,
    compress_flow_start, watermark_flow_start, url_conversion_flow_start,
    handle_watermark_type_selection, handle_watermark_position_input
)

# Import specific conversion handlers from docx_converter and pptx_converter
from docx_converter import handle_docx_to_pdf, handle_pdf_to_docx
from pptx_converter import handle_pptx_to_pdf, handle_pdf_to_pptx

# Import payment handlers
from paypal_integration import handle_payment_option_selection

logger = logging.getLogger(__name__)

# Menu configurations
MENU_CONFIGS = {
    'pdf': {
        'title': 'PDF',
        'emoji': '📄',
        'conversions': [
            ('PNG', 'png', '🖼️'),
            ('JPG', 'jpg', '📸'),
            ('WEBP', 'webp', '🌐'),
            ('TIFF', 'tiff', '📁'),
            ('Word', 'docx', '📝'),
            ('PowerPoint', 'pptx', '📊')
        ]
    },
    'docx': {
        'title': 'Word',
        'emoji': '📝',
        'conversions': [
            ('PDF', 'pdf', '📄'),
            ('PNG', 'png', '🖼️'),
            ('JPG', 'jpg', '📸'),
            ('WEBP', 'webp', '🌐'),
            ('TIFF', 'tiff', '📁'),
            ('PowerPoint', 'pptx', '📊')
        ]
    },
    'pptx': {
        'title': 'PowerPoint',
        'emoji': '📊',
        'conversions': [
            ('PDF', 'pdf', '📄'),
            ('PNG', 'png', '🖼️'),
            ('JPG', 'jpg', '📸'),
            ('WEBP', 'webp', '🌐'),
            ('TIFF', 'tiff', '📁'),
            ('Word', 'docx', '📝')
        ]
    },
    'png': {
        'title': 'PNG',
        'emoji': '🖼️',
        'conversions': [
            ('PDF', 'pdf', '📄'),
            ('JPG', 'jpg', '📸'),
            ('WEBP', 'webp', '🌐'),
            ('TIFF', 'tiff', '📁')
        ]
    },
    'jpg': {
        'title': 'JPG',
        'emoji': '📸',
        'conversions': [
            ('PDF', 'pdf', '📄'),
            ('PNG', 'png', '🖼️'),
            ('WEBP', 'webp', '🌐'),
            ('TIFF', 'tiff', '📁')
        ]
    },
    'webp': {
        'title': 'WEBP',
        'emoji': '🌐',
        'conversions': [
            ('PDF', 'pdf', '📄'),
            ('PNG', 'png', '🖼️'),
            ('JPG', 'jpg', '📸'),
            ('TIFF', 'tiff', '📁')
        ]
    },
    'tiff': {
        'title': 'TIFF',
        'emoji': '📁',
        'conversions': [
            ('PDF', 'pdf', '📄'),
            ('PNG', 'png', '🖼️'),
            ('JPG', 'jpg', '📸'),
            ('WEBP', 'webp', '🌐')
        ]
    }
}

async def create_conversion_menu(update: Update, context: CallbackContext, format_type: str) -> int:
    """Creates a conversion menu for the specified format type."""
    logger.info(f"create_conversion_menu called for {format_type}.")
    
    if format_type not in MENU_CONFIGS:
        logger.error(f"Invalid format type: {format_type}")
        return MAIN_MENU
    
    config = MENU_CONFIGS[format_type]
    keyboard = []
    
    # Add conversion options
    for name, code, emoji in config['conversions']:
        button_text = f"{config['title']} to {name} {emoji}"
        callback_data = f"{format_type}_to_{code}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    # Add specific feature buttons based on format_type
    if format_type == 'pdf':
        keyboard.append([InlineKeyboardButton("➕ Merge PDFs", callback_data='merge_pdf_start')])
        keyboard.append([InlineKeyboardButton("✂️ Split PDF", callback_data='split_pdf_start')])
        keyboard.append([InlineKeyboardButton("🗜️ Compress PDF", callback_data='compress_pdf_start')])
        keyboard.append([InlineKeyboardButton("✍️ Watermark PDF", callback_data='watermark_start')])
        keyboard.append([InlineKeyboardButton("📄 Extract Text (OCR)", callback_data='ocr_start')])
    elif format_type in ['png', 'jpg', 'webp', 'tiff']:
        keyboard.append([InlineKeyboardButton("📏 Resize Image", callback_data='resize_image_start')])
        keyboard.append([InlineKeyboardButton("🔄 Rotate Image", callback_data='rotate_image_start')])
        keyboard.append([InlineKeyboardButton("🗜️ Compress Image", callback_data='compress_image_start')])
        keyboard.append([InlineKeyboardButton("✍️ Watermark Image", callback_data='watermark_start')])
        keyboard.append([InlineKeyboardButton("📄 Extract Text (OCR)", callback_data='ocr_start')])
    elif format_type in ['docx', 'pptx']:
        keyboard.append([InlineKeyboardButton("🗜️ Compress File", callback_data='compress_file_start')])
        keyboard.append([InlineKeyboardButton("✍️ Watermark File", callback_data='watermark_start')])
        keyboard.append([InlineKeyboardButton("📄 Extract Text (OCR)", callback_data='ocr_start')])

    # Add general utility buttons
    keyboard.append([InlineKeyboardButton("🔗 Convert from URL", callback_data='url_conversion_start')])
    keyboard.append([InlineKeyboardButton("⬅️ Back to Main Menu", callback_data='start')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = f"Choose your desired {config['title']} conversion type or action: 👇"
    
    await send_or_edit_message(update, message_text, reply_markup=reply_markup)
    logger.info(f"create_conversion_menu returning MAIN_MENU for {format_type}.")
    return MAIN_MENU

# Individual menu functions using the generic creator
async def pdf_conversions_menu(update: Update, context: CallbackContext) -> int:
    """Displays the PDF conversion options."""
    return await create_conversion_menu(update, context, 'pdf')

async def png_conversions_menu(update: Update, context: CallbackContext) -> int:
    """Displays the PNG conversion options."""
    return await create_conversion_menu(update, context, 'png')

async def jpg_conversions_menu(update: Update, context: CallbackContext) -> int:
    """Displays the JPG conversion options."""
    return await create_conversion_menu(update, context, 'jpg')

async def webp_conversions_menu(update: Update, context: CallbackContext) -> int:
    """Displays the WEBP conversion options."""
    return await create_conversion_menu(update, context, 'webp')

async def tiff_conversions_menu(update: Update, context: CallbackContext) -> int:
    """Displays the TIFF conversion options."""
    return await create_conversion_menu(update, context, 'tiff')

async def docx_conversions_menu(update: Update, context: CallbackContext) -> int:
    """Displays the DOCX conversion options."""
    return await create_conversion_menu(update, context, 'docx')

async def pptx_conversions_menu(update: Update, context: CallbackContext) -> int:
    """Displays the PPTX conversion options."""
    return await create_conversion_menu(update, context, 'pptx')

async def start_conversion_flow(update: Update, context: CallbackContext, source_format: str, target_format: str) -> int:
    """Initiates a conversion flow for the specified formats."""
    logger.info(f"start_conversion_flow called for {source_format} to {target_format}.")
    
    # Set up context data
    context.user_data['conversion_type'] = f'{source_format}_to_{target_format}'
    context.user_data['input_image_format'] = source_format
    context.user_data['output_image_format'] = target_format
    
    # Get format configurations
    source_config = MENU_CONFIGS.get(source_format, {})
    source_emoji = source_config.get('emoji', '📄')
    source_name = source_config.get('title', source_format.upper())
    
    target_config = MENU_CONFIGS.get(target_format, {})
    target_name = target_config.get('title', target_format.upper())
    
    # Create appropriate message based on conversion type
    if target_format == 'pdf':
        if source_format in ['docx', 'pptx']:
            # Document to PDF
            message = f"You've selected {source_name} to PDF! 📄 Please send me the {source_name} file you want to convert. 📤"
        else:
            # Multiple images to PDF
            message = f"You've selected {source_name} to PDF! 📄 Please send me all the {source_name} images you want to combine into a PDF. You can send them one by one! {source_emoji}"
    elif source_format == 'pdf':
        # PDF to images or documents
        message = f"You've selected PDF to {target_name}! 🎉 Please send me the PDF file you want to convert. 📤"
    else:
        # Image to image conversion
        message = f"You've selected {source_name} to {target_name}! ✨ Please send me the {source_name} images you want to convert. You can send multiple! 📤"
    
    # Send message
    await send_or_edit_message(update, message)
    logger.info(f"start_conversion_flow returning SELECT_CONVERSION_TYPE for {source_format} to {target_format}.")
    return SELECT_CONVERSION_TYPE

# Individual flow starters using the generic function
async def pdf_to_images_flow_start(update: Update, context: CallbackContext) -> int:
    """Initiates the PDF to Images conversion flow."""
    if update.callback_query:
        target_format = update.callback_query.data.split('_to_')[1]
    else:
        target_format = update.message.text.split('/pdf2')[1]
    
    return await start_conversion_flow(update, context, 'pdf', target_format)

async def png_to_pdf_flow_start(update: Update, context: CallbackContext) -> int:
    """Initiates PNG to PDF conversion flow."""
    return await start_conversion_flow(update, context, 'png', 'pdf')

async def png_to_image_flow_start(update: Update, context: CallbackContext) -> int:
    """Initiates PNG to other image format conversion flow."""
    if update.callback_query:
        target_format = update.callback_query.data.split('_to_')[1]
    else:
        target_format = update.message.text.split('_to_')[1] if '_to_' in update.message.text else 'unknown'
    
    return await start_conversion_flow(update, context, 'png', target_format)

async def jpg_to_pdf_flow_start(update: Update, context: CallbackContext) -> int:
    """Initiates JPG to PDF conversion flow."""
    return await start_conversion_flow(update, context, 'jpg', 'pdf')

async def jpg_to_image_flow_start(update: Update, context: CallbackContext) -> int:
    """Initiates JPG to other image format conversion flow."""
    if update.callback_query:
        target_format = update.callback_query.data.split('_to_')[1]
    else:
        target_format = update.message.text.split('_to_')[1] if '_to_' in update.message.text else 'unknown'
    
    return await start_conversion_flow(update, context, 'jpg', target_format)

async def webp_to_pdf_flow_start(update: Update, context: CallbackContext) -> int:
    """Initiates WEBP to PDF conversion flow."""
    return await start_conversion_flow(update, context, 'webp', 'pdf')

async def webp_to_image_flow_start(update: Update, context: CallbackContext) -> int:
    """Initiates WEBP to other image format conversion flow."""
    if update.callback_query:
        target_format = update.callback_query.data.split('_to_')[1]
    else:
        target_format = update.message.text.split('_to_')[1] if '_to_' in update.message.text else 'unknown'
    
    return await start_conversion_flow(update, context, 'webp', target_format)

async def tiff_to_pdf_flow_start(update: Update, context: CallbackContext) -> int:
    """Initiates TIFF to PDF conversion flow."""
    return await start_conversion_flow(update, context, 'tiff', 'pdf')

async def tiff_to_image_flow_start(update: Update, context: CallbackContext) -> int:
    """Initiates TIFF to other image format conversion flow."""
    if update.callback_query:
        target_format = update.callback_query.data.split('_to_')[1]
    else:
        target_format = update.message.text.split('_to_')[1] if '_to_' in update.message.text else 'unknown'
    
    return await start_conversion_flow(update, context, 'tiff', target_format)

# Pattern-based handlers
PATTERN_HANDLERS = {
    'pdf_to_': pdf_to_images_flow_start,
    'png_to_': png_to_image_flow_start,
    'jpg_to_': jpg_to_image_flow_start,
    'webp_to_': webp_to_image_flow_start,
    'tiff_to_': tiff_to_image_flow_start,
    'docx_to_': start_conversion_flow,
    'pptx_to_': start_conversion_flow,
}

async def handle_menu_callbacks(update: Update, context: CallbackContext) -> int:
    """Handles all callback queries from the main menu and sub-menus."""
    logger.info("handle_menu_callbacks function entered.")
    
    if not update.callback_query:
        logger.warning("handle_menu_callbacks called without callback_query.")
        if update.message:
            await send_or_edit_message(update, "Please use the menu buttons to interact with me.")
        return MAIN_MENU
    
    query = update.callback_query
    await query.answer()
    callback_data = query.data
    
    logger.info(f"handle_menu_callbacks called with callback_data: {callback_data}")
    
    try:
        # Define callback handlers mapping here to avoid module-level imports
        CALLBACK_HANDLERS = {
            'pdf_conversions_menu': pdf_conversions_menu,
            'png_conversions_menu': png_conversions_menu,
            'jpg_conversions_menu': jpg_conversions_menu,
            'webp_conversions_menu': webp_conversions_menu,
            'tiff_conversions_menu': tiff_conversions_menu,
            'docx_conversions_menu': docx_conversions_menu,
            'pptx_conversions_menu': pptx_conversions_menu,
            'help_command': help_command,
            'start': start,
            'png_to_pdf': png_to_pdf_flow_start,
            'jpg_to_pdf': jpg_to_pdf_flow_start,
            'webp_to_pdf': webp_to_pdf_flow_start,
            'tiff_to_pdf': tiff_to_pdf_flow_start,
            'docx_to_pdf': lambda u, c: start_conversion_flow(u, c, 'docx', 'pdf'),
            'pdf_to_docx': lambda u, c: start_conversion_flow(u, c, 'pdf', 'docx'),
            'docx_to_png': lambda u, c: start_conversion_flow(u, c, 'docx', 'png'),
            'docx_to_jpg': lambda u, c: start_conversion_flow(u, c, 'docx', 'jpg'),
            'docx_to_webp': lambda u, c: start_conversion_flow(u, c, 'docx', 'webp'),
            'docx_to_tiff': lambda u, c: start_conversion_flow(u, c, 'docx', 'tiff'),
            'docx_to_pptx': lambda u, c: start_conversion_flow(u, c, 'docx', 'pptx'),
            'pptx_to_pdf': lambda u, c: start_conversion_flow(u, c, 'pptx', 'pdf'),
            'pdf_to_pptx': lambda u, c: start_conversion_flow(u, c, 'pdf', 'pptx'),
            'pptx_to_png': lambda u, c: start_conversion_flow(u, c, 'pptx', 'png'),
            'pptx_to_jpg': lambda u, c: start_conversion_flow(u, c, 'pptx', 'jpg'),
            'pptx_to_webp': lambda u, c: start_conversion_flow(u, c, 'pptx', 'webp'),
            'pptx_to_tiff': lambda u, c: start_conversion_flow(u, c, 'pptx', 'tiff'),
            'pptx_to_docx': lambda u, c: start_conversion_flow(u, c, 'pptx', 'docx'),
            'ocr_start': ocr_flow_start,
            'merge_pdf_start': merge_pdf_flow_start,
            'split_pdf_start': split_pdf_flow_start,
            'compress_pdf_start': compress_flow_start,
            'compress_image_start': compress_flow_start,
            'watermark_start': watermark_flow_start,
            'url_conversion_start': url_conversion_flow_start,
            'watermark_type_text': handle_watermark_type_selection,
            'watermark_type_image': handle_watermark_type_selection,
            'top-left': handle_watermark_position_input,
            'top-right': handle_watermark_position_input,
            'center': handle_watermark_position_input,
            'bottom-left': handle_watermark_position_input,
            'bottom-right': handle_watermark_position_input,
        }

        # Add payment option handler dynamically
        if callback_data.startswith('payment_option_'):
            logger.info(f"Calling payment option handler for {callback_data}.")
            return await handle_payment_option_selection(update, context)

        # Check direct callback handlers first
        if callback_data in CALLBACK_HANDLERS:
            logger.info(f"Calling direct handler for {callback_data}.")
            return await CALLBACK_HANDLERS[callback_data](update, context)
        
        # Check pattern-based handlers
        for pattern, handler in PATTERN_HANDLERS.items():
            if callback_data.startswith(pattern):
                logger.info(f"Calling pattern handler for {callback_data} (pattern: {pattern}).")
                return await handler(update, context)
        
        # No handler found
        logger.warning(f"No handler found for callback_data: {callback_data}. Returning to MAIN_MENU.")
        await send_or_edit_message(update, "Invalid selection. Please choose from the menu.")
        return MAIN_MENU
        
    except Exception as e:
        logger.error(f"Error in handle_menu_callbacks for callback_data '{callback_data}': {e}")
        await send_or_edit_message(update, "An error occurred while processing your request. Please try again or type /start.")
        return ConversationHandler.END
