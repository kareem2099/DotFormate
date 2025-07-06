import pytesseract
from PIL import Image
import os
import logging

logger = logging.getLogger(__name__)

def perform_ocr(image_path: str) -> str:
    """
    Performs OCR on an image file and returns the extracted text.
    """
    if not os.path.exists(image_path):
        logger.error(f"Image file not found for OCR: {image_path}")
        return ""

    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        logger.info(f"OCR performed successfully on {image_path}")
        return text
    except Exception as e:
        logger.error(f"Error during OCR on {image_path}: {e}")
        return ""
