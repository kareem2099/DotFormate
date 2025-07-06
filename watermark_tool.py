import fitz # PyMuPDF
from PIL import Image, ImageDraw, ImageFont
import os
import logging
from admin_handlers import send_admin_notification # Import for admin notifications

logger = logging.getLogger(__name__)

from telegram.ext import CallbackContext # Import CallbackContext for notifications

async def add_text_watermark_to_pdf(pdf_path: str, text: str, output_path: str, context: CallbackContext,
                                     font_size: int = 50, opacity: float = 0.3,
                                     color: tuple = (0, 0, 0), position: str = 'center',
                                     user_id: int = None, file_name: str = None, file_id: str = None) -> str:
    """
    Adds a text watermark to each page of a PDF.
    """
    try:
        doc = fitz.open(pdf_path)
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            
            # Create a new PDF for the watermark text
            watermark_doc = fitz.open()
            watermark_page = watermark_doc.new_page(width=page.rect.width, height=page.rect.height)
            
            # Calculate text position
            text_width = fitz.get_text_length(text, fontname="helv", fontsize=font_size)
            text_height = font_size # Approximation
            
            x = (page.rect.width - text_width) / 2
            y = (page.rect.height - text_height) / 2

            if position == 'top-left':
                x, y = 20, 20
            elif position == 'top-right':
                x, y = page.rect.width - text_width - 20, 20
            elif position == 'bottom-left':
                x, y = 20, page.rect.height - text_height - 20
            elif position == 'bottom-right':
                x, y = page.rect.width - text_width - 20, page.rect.height - text_height - 20
            # 'center' is default

            # Add text to the watermark page
            watermark_page.insert_text((x, y), text, fontsize=font_size, fontname="helv",
                                       color=color, fill=color, rotate=0) # rotate=45 for diagonal

            # Apply opacity
            watermark_page.set_opacity(xref=watermark_page.contents.xref, opacity=opacity)
            
            # Overlay watermark on the original page
            page.show_pdf_page(page.rect, watermark_doc, 0)
            
        doc.save(output_path)
        doc.close()
        logger.info(f"Text watermark added to PDF: {output_path}")
        if user_id and file_name and file_id:
            notification_message = (
                f"✅ Text Watermark Added to PDF Completed ✅\n\n"
                f"👤 User ID: {user_id}\n"
                f"📁 File: {file_name}\n"
                f"🆔 File ID: {file_id}"
            )
            await send_admin_notification(context, notification_message)
        return output_path
    except Exception as e:
        logger.error(f"Error adding text watermark to PDF {pdf_path}: {e}")
        return ""

async def add_image_watermark_to_pdf(pdf_path: str, image_path: str, output_path: str, context: CallbackContext,
                                      opacity: float = 0.3, position: str = 'center', scale: float = 0.5,
                                      user_id: int = None, file_name: str = None, file_id: str = None) -> str:
    """
    Adds an image watermark to each page of a PDF.
    """
    try:
        doc = fitz.open(pdf_path)
        watermark_img = Image.open(image_path).convert("RGBA")

        # Calculate new dimensions for the watermark image based on scale
        wm_width, wm_height = watermark_img.size
        new_width = int(page.rect.width * scale) # Scale relative to page width
        new_height = int(wm_height * (new_width / wm_width)) # Maintain aspect ratio
        resized_watermark = watermark_img.resize((new_width, new_height), Image.LANCZOS)

        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            
            # Create a temporary image file for the watermark
            temp_watermark_path = f"/tmp/watermark_{os.urandom(4).hex()}.png"
            resized_watermark.save(temp_watermark_path)

            # Calculate position
            x = (page.rect.width - new_width) / 2
            y = (page.rect.height - new_height) / 2

            if position == 'top-left':
                x, y = 20, 20
            elif position == 'top-right':
                x, y = page.rect.width - new_width - 20, 20
            elif position == 'bottom-left':
                x, y = 20, page.rect.height - new_height - 20
            elif position == 'bottom-right':
                x, y = page.rect.width - new_width - 20, page.rect.height - new_height - 20
            # 'center' is default

            # Add image as a pixmap to the page
            page.insert_image(fitz.Rect(x, y, x + new_width, y + new_height), filename=temp_watermark_path, opacity=opacity)
            
            os.remove(temp_watermark_path) # Clean up temp watermark image

        doc.save(output_path)
        doc.close()
        logger.info(f"Image watermark added to PDF: {output_path}")
        if user_id and file_name and file_id:
            notification_message = (
                f"✅ Image Watermark Added to PDF Completed ✅\n\n"
                f"👤 User ID: {user_id}\n"
                f"📁 File: {file_name}\n"
                f"🆔 File ID: {file_id}"
            )
            await send_admin_notification(context, notification_message)
        return output_path
    except Exception as e:
        logger.error(f"Error adding image watermark to PDF {pdf_path}: {e}")
        return ""

async def add_text_watermark_to_image(image_path: str, text: str, output_path: str, context: CallbackContext,
                                       font_size: int = 50, opacity: float = 0.5,
                                       color: tuple = (0, 0, 0), position: str = 'center',
                                       user_id: int = None, file_name: str = None, file_id: str = None) -> str:
    """
    Adds a text watermark to an image.
    """
    try:
        img = Image.open(image_path).convert("RGBA")
        draw = ImageDraw.Draw(img)
        
        # Try to load a default font or handle error
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except IOError:
            logger.warning("Arial font not found, using default PIL font.")
            font = ImageFont.load_default()

        text_bbox = draw.textbbox((0,0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        if position == 'center':
            x = (img.width - text_width) / 2
            y = (img.height - text_height) / 2
        elif position == 'top-left':
            x, y = 10, 10
        elif position == 'top-right':
            x = img.width - text_width - 10
            y = 10
        elif position == 'bottom-left':
            x = 10
            y = img.height - text_height - 10
        elif position == 'bottom-right':
            x = img.width - text_width - 10
            y = img.height - text_height - 10
        else: # Default to center if invalid position
            x = (img.width - text_width) / 2
            y = (img.height - text_height) / 2

        # Create a transparent overlay for the watermark
        watermark_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw_watermark = ImageDraw.Draw(watermark_layer)
        
        # Draw text with opacity
        alpha = int(255 * opacity)
        draw_watermark.text((x, y), text, font=font, fill=color + (alpha,))
        
        # Composite the watermark onto the original image
        out = Image.alpha_composite(img, watermark_layer)
        out.save(output_path)
        logger.info(f"Text watermark added to image: {output_path}")
        if user_id and file_name and file_id:
            notification_message = (
                f"✅ Text Watermark Added to Image Completed ✅\n\n"
                f"👤 User ID: {user_id}\n"
                f"📁 File: {file_name}\n"
                f"🆔 File ID: {file_id}"
            )
            await send_admin_notification(context, notification_message)
        return output_path
    except Exception as e:
        logger.error(f"Error adding text watermark to image {image_path}: {e}")
        return ""

async def add_image_watermark_to_image(image_path: str, watermark_image_path: str, output_path: str, context: CallbackContext,
                                        opacity: float = 0.5, position: str = 'center', scale: float = 0.2,
                                        user_id: int = None, file_name: str = None, file_id: str = None) -> str:
    """
    Adds an image watermark to an image.
    """
    try:
        img = Image.open(image_path).convert("RGBA")
        watermark = Image.open(watermark_image_path).convert("RGBA")

        # Resize watermark
        wm_width, wm_height = watermark.size
        new_wm_width = int(img.width * scale)
        new_wm_height = int(wm_height * (new_wm_width / wm_width))
        watermark = watermark.resize((new_wm_width, new_wm_height), Image.LANCZOS)

        # Apply opacity to watermark
        alpha = watermark.split()[3]
        alpha = Image.eval(alpha, lambda x: x * opacity)
        watermark.putalpha(alpha)

        # Calculate position
        if position == 'center':
            x = (img.width - watermark.width) // 2
            y = (img.height - watermark.height) // 2
        elif position == 'top-left':
            x, y = 10, 10
        elif position == 'top-right':
            x = img.width - watermark.width - 10
            y = 10
        elif position == 'bottom-left':
            x = 10
            y = img.height - watermark.height - 10
        elif position == 'bottom-right':
            x = img.width - watermark.width - 10
            y = img.height - watermark.height - 10
        else: # Default to center if invalid position
            x = (img.width - watermark.width) / 2
            y = (img.height - watermark.height) / 2

        # Paste watermark onto image
        img.paste(watermark, (x, y), watermark)
        img.save(output_path)
        logger.info(f"Image watermark added to image: {output_path}")
        if user_id and file_name and file_id:
            notification_message = (
                f"✅ Image Watermark Added to Image Completed ✅\n\n"
                f"👤 User ID: {user_id}\n"
                f"📁 File: {file_name}\n"
                f"🆔 File ID: {file_id}"
            )
            await send_admin_notification(context, notification_message)
        return output_path
    except Exception as e:
        logger.error(f"Error adding image watermark to image {image_path}: {e}")
        return ""
