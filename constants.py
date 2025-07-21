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
# Maximum file sizes for free users (in MB)
MAX_FREE_IMAGE_SIZE_MB = 10
MAX_FREE_PDF_SIZE_MB = 25
MAX_FREE_WORD_SIZE_MB = 15
MAX_FREE_PPT_SIZE_MB = 30

# Daily conversion limits for free users
MAX_FREE_DAILY_CONVERSIONS = 5 # Example limit

# Maximum file sizes for premium users before R2 upload (in MB)
# Files exceeding these limits for premium users will be uploaded to R2
MAX_PREMIUM_IMAGE_SIZE_MB = 50
MAX_PREMIUM_PDF_SIZE_MB = 100
MAX_PREMIUM_WORD_SIZE_MB = 75
MAX_PREMIUM_PPT_SIZE_MB = 150

# Payment Options
PAYMENT_OPTIONS = {
    "week": {"amount": "7.00", "description": "Weekly Subscription", "type": "weekly"},
    "month": {"amount": "15.00", "description": "Monthly Subscription", "type": "monthly"},
    "half_year": {"amount": "60.00", "description": "Half-Yearly Subscription", "type": "half_yearly"},
    "year": {"amount": "150.00", "description": "Yearly Subscription", "type": "yearly"},
    "source_code": {"amount": "270.00", "description": "Source Code Access", "type": "lifetime"} # Assuming source code access is a lifetime premium
}

# Payment Methods
PAYMENT_METHODS = {
    "paypal": "PayPal",
    "cliq": "Cliq (Jordanian Only)",
    "vodafone_cash": "Vodafone Cash (Egyptian Only)",
    "instapay": "Instapay (Egyptian Only)"
}
