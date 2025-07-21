import fitz # PyMuPDF
import os
import zipfile
import logging
from PIL import Image
from pathlib import Path

logger = logging.getLogger(__name__)

def convert_pdf_to_images(pdf_path: str, page_selection: str, output_format: str = 'png') -> list:
    """
    Converts specified pages of a PDF to images (PNG, JPG, TIFF, WEBP).
    Returns a list of paths to the generated image files.
    
    Args:
        pdf_path: Path to input PDF file
        page_selection: Pages to convert ('all' or specific pages like '1-3,5')
        output_format: Output format ('png', 'jpg', 'tiff', 'webp')
    """
    image_paths = []
    supported_formats = ['png', 'jpg', 'tiff', 'webp']
    if output_format.lower() not in supported_formats:
        logger.error(f"Unsupported output format: {output_format}. Using PNG.")
        output_format = 'png'
    try:
        doc = fitz.open(pdf_path)
        pages_to_convert = []

        if page_selection.lower() == 'all':
            pages_to_convert = list(range(doc.page_count))
        else:
            # Parse page ranges (e.g., "1-3,5")
            parts = page_selection.split(',')
            for part in parts:
                part = part.strip()
                if '-' in part:
                    start, end = map(int, part.split('-'))
                    pages_to_convert.extend(range(start - 1, end)) # -1 because fitz is 0-indexed
                elif part.isdigit():
                    pages_to_convert.append(int(part) - 1) # -1 because fitz is 0-indexed

        for page_num in sorted(list(set(pages_to_convert))): # Use set to remove duplicates, then sort
            if 0 <= page_num < doc.page_count:
                page = doc.load_page(page_num)
                pix = page.get_pixmap()
                output_path = f"/tmp/{os.path.basename(pdf_path).replace('.pdf', '')}_page_{page_num + 1}.{output_format}"
                if output_format == 'jpg':
                    pix.pil_save(output_path, format='JPEG', quality=95)
                elif output_format == 'tiff':
                    pix.pil_save(output_path, format='TIFF')
                elif output_format == 'webp':
                    pix.pil_save(output_path, format='WEBP', quality=95)
                else: # Default to PNG
                    pix.save(output_path)
                image_paths.append(output_path)
            else:
                logger.warning(f"Page {page_num + 1} is out of bounds for PDF {pdf_path}")

        doc.close()
    except Exception as e:
        logger.error(f"Error converting PDF {pdf_path} to PNG: {e}")
        return []
    return image_paths

def create_zip_archive(file_paths: list, original_file_name: str, output_dir: str) -> str:
    """
    Creates a ZIP archive from a list of file paths.
    Returns the path to the created ZIP file.
    
    Args:
        file_paths: List of paths to files to be included in the zip.
        original_file_name: The original name of the file (e.g., "document.pdf") to derive the zip name.
        output_dir: The directory where the zip file should be created.
    """
    zip_file_name = f"{Path(original_file_name).stem}_converted.zip"
    zip_file_path = os.path.join(output_dir, zip_file_name)
    try:
        with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in file_paths:
                zipf.write(file_path, os.path.basename(file_path))
        return zip_file_path
    except Exception as e:
        logger.error(f"Error creating ZIP archive: {e}")
        return ""

def convert_image_format(input_path: str, output_format: str) -> str:
    """
    Converts an image file to another format (PNG, JPG, WEBP).
    Returns the path to the converted image file.
    """
    if not os.path.exists(input_path):
        return ""

    output_path = f"/tmp/{os.path.basename(input_path).rsplit('.', 1)[0]}.{output_format}"
    
    try:
        img = Image.open(input_path).convert('RGB')
        if output_format == 'jpg':
            img.save(output_path, 'JPEG', quality=95)
        elif output_format == 'webp':
            img.save(output_path, 'WEBP', quality=95)
        else:  # Default to PNG
            img.save(output_path, 'PNG')
        return output_path
    except Exception as e:
        logger.error(f"Error converting image format: {e}")
        return ""

def convert_images_to_pdf(image_paths: list) -> str:
    """
    Converts a list of images (PNG, JPG, TIFF, WEBP) to a single PDF file.
    Returns the path to the created PDF file.
    """
    if not image_paths:
        return ""

    output_pdf_path = f"/tmp/converted_images_{os.urandom(4).hex()}.pdf"
    try:
        images = []
        for path in image_paths:
            img = Image.open(path).convert('RGB')
            images.append(img)

        if images:
            images[0].save(output_pdf_path, save_all=True, append_images=images[1:])
            return output_pdf_path
        else:
            return ""
    except Exception as e:
        logger.error(f"Error converting images to PDF: {e}")
        return ""

def merge_pdfs(pdf_paths: list) -> str:
    """
    Merges multiple PDF files into a single PDF file.
    Returns the path to the created merged PDF file.
    """
    if not pdf_paths:
        return ""

    merged_pdf_path = f"/tmp/merged_pdf_{os.urandom(4).hex()}.pdf"
    try:
        result_doc = fitz.open()
        for pdf_path in pdf_paths:
            doc = fitz.open(pdf_path)
            result_doc.insert_pdf(doc)
            doc.close()
        result_doc.save(merged_pdf_path)
        result_doc.close()
        logger.info(f"PDFs merged successfully to: {merged_pdf_path}")
        return merged_pdf_path
    except Exception as e:
        logger.error(f"Error merging PDFs: {e}")
        return ""

def split_pdf(pdf_path: str, page_ranges: str) -> list:
    """
    Splits a PDF into multiple PDF files based on specified page ranges.
    Returns a list of paths to the created split PDF files.
    """
    split_pdf_paths = []
    try:
        doc = fitz.open(pdf_path)
        
        parts = page_ranges.split(',')
        for i, part in enumerate(parts):
            part = part.strip()
            start_page, end_page = -1, -1
            if '-' in part:
                start, end = map(int, part.split('-'))
                start_page = start - 1
                end_page = end - 1
            elif part.isdigit():
                start_page = int(part) - 1
                end_page = int(part) - 1
            
            if 0 <= start_page <= end_page < doc.page_count:
                output_split_path = f"/tmp/{os.path.basename(pdf_path).replace('.pdf', '')}_split_{i+1}.pdf"
                new_doc = fitz.open()
                new_doc.insert_pdf(doc, from_page=start_page, to_page=end_page)
                new_doc.save(output_split_path)
                new_doc.close()
                split_pdf_paths.append(output_split_path)
            else:
                logger.warning(f"Invalid page range for splitting: {part}. Skipping.")
        
        doc.close()
    except Exception as e:
        logger.error(f"Error splitting PDF {pdf_path}: {e}")
        return []
    return split_pdf_paths

def compress_pdf(pdf_path: str, output_path: str, quality: int = 75) -> str:
    """
    Compresses a PDF file by reducing image quality.
    Returns the path to the compressed PDF file.
    """
    try:
        doc = fitz.open(pdf_path)
        # Output path for the compressed PDF
        if not output_path:
            output_path = f"/tmp/{os.path.basename(pdf_path).replace('.pdf', '')}_compressed.pdf"
        
        # Save with garbage collection and compression
        doc.save(output_path, 
                 garbage=3,  # Clean up unused objects
                 deflate=True, # Compress streams
                 clean=True, # Clean up document structure
                 pretty=True, # Make output readable (optional, can increase size slightly)
                 # For image compression, iterate through images and re-save them with lower quality
                 # This is more complex and often handled by a separate tool or a more advanced save option
                 # For basic compression, the above save options are a good start.
                 # To truly compress images within, you'd need to extract, compress, and re-insert.
                 # PyMuPDF's save method with 'garbage' and 'deflate' often provides good results.
                 # For more aggressive image compression, you might need to iterate pages and pixmaps.
                 # Example for image compression (more advanced):
                 # for p in doc:
                 #     for img in p.get_images():
                 #         xref = img[0]
                 #         smask = img[1]
                 #         # ... process image and replace ...
                )
        doc.close()
        logger.info(f"PDF compressed successfully to: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error compressing PDF {pdf_path}: {e}")
        return ""

def compress_image(image_path: str, output_path: str, quality: int = 75) -> str:
    """
    Compresses an image file by reducing its quality.
    Returns the path to the compressed image file.
    """
    if not os.path.exists(image_path):
        return ""

    if not output_path:
        base, ext = os.path.splitext(os.path.basename(image_path))
        output_path = f"/tmp/{base}_compressed{ext}"

    try:
        img = Image.open(image_path)
        # Determine format for saving based on original extension or desired output
        format = img.format if img.format else 'PNG' # Default to PNG if unknown
        if format == 'JPEG' or format == 'JPG':
            img.save(output_path, 'JPEG', quality=quality, optimize=True)
        elif format == 'PNG':
            img.save(output_path, 'PNG', optimize=True) # PNG compression is lossless, quality parameter is ignored
        elif format == 'WEBP':
            img.save(output_path, 'WEBP', quality=quality, optimize=True)
        elif format == 'TIFF':
            img.save(output_path, 'TIFF', compression='tiff_lzw') # LZW is a common lossless compression for TIFF
        else:
            img.save(output_path) # Fallback for other formats

        logger.info(f"Image compressed successfully to: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error compressing image {image_path}: {e}")
        return ""
