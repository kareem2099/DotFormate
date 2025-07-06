# States for the conversation handler
MAIN_MENU, SELECT_CONVERSION_TYPE, SELECT_PAGES, SELECT_OUTPUT_FORMAT, SELECT_IMAGE_FORMAT, \
OCR_PROCESSING, MERGE_PDF_COLLECTION, SPLIT_PDF_INPUT_PAGES, COMPRESSION_PROCESSING, \
WATERMARK_FILE_INPUT, WATERMARK_TEXT_INPUT, WATERMARK_IMAGE_INPUT, WATERMARK_POSITION_INPUT, \
URL_INPUT, DOCX_CONVERSION, PPTX_CONVERSION, COMPRESS_FILE_PROCESSING, \
RESIZE_INPUT, ROTATE_INPUT, PAYMENT_INPUT, SELECT_PAYMENT_OPTION, SELECT_PAYMENT_METHOD = range(22)

PAYMENT_SUCCESS = "✅ Payment successful! Thank you for your support."
PAYMENT_FAILED = "❌ Payment failed. Please try again or contact support."
PAYMENT_PENDING = "⏳ Your payment is pending. We will notify you once it's confirmed."

# Payment Options
PAYMENT_OPTIONS = {
    "week": {"amount": "5.00", "description": "Weekly Subscription"},
    "month": {"amount": "15.00", "description": "Monthly Subscription"},
    "half_year": {"amount": "60.00", "description": "Half-Yearly Subscription"},
    "year": {"amount": "150.00", "description": "Yearly Subscription"},
    "source_code": {"amount": "270.00", "description": "Source Code Access"}
}

# Payment Methods
PAYMENT_METHODS = {
    "paypal": "PayPal",
    "cliq": "Cliq (Jordanian Only)",
    "vodafone_cash": "Vodafone Cash (Egyptian Only)",
    "we_pay": "We Pay (Egyptian Only)",
    "instapay": "Instapay (Egyptian Only)"
}
