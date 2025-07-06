import requests
import os
import logging

logger = logging.getLogger(__name__)

def download_file_from_url(url: str, destination_path: str) -> bool:
    """
    Downloads a file from a given URL to a specified destination path.
    Returns True on success, False on failure.
    """
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)

        with open(destination_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info(f"Successfully downloaded {url} to {destination_path}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading file from URL {url}: {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during file download: {e}")
        return False
