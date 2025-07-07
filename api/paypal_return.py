import os
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def handler(request):
    logger.info(f"PayPal return handler called with method: {request.method}")
    logger.info(f"Request URL: {getattr(request, 'url', 'URL not available')}")
    
    if request.method != 'GET':
        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'text/plain'},
            'body': 'Method Not Allowed'
        }

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'text/plain'},
        'body': 'OK - PayPal Return Endpoint Test'
    }

app = handler
