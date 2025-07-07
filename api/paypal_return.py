from flask import Flask, request, jsonify
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = Flask(__name__)

@app.route('/api/paypal_return', methods=['GET'])
def paypal_return_handler():
    logger.info(f"PayPal return handler called with method: {request.method}")
    logger.info(f"Request URL: {request.url}")
    
    # You can access query parameters like this:
    # user_id = request.args.get('user_id')
    # paymentId = request.args.get('paymentId')
    # token = request.args.get('token')
    # PayerID = request.args.get('PayerID')

    # Add your PayPal return logic here
    # For example, verify the payment with PayPal API

    return jsonify({'status': 'OK', 'message': 'PayPal Return Endpoint Test'})
