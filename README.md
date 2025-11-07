# Formate

A powerful Telegram bot for file format conversions, built with Python. Convert PDFs, images, documents, and more with ease. Features premium subscriptions, referral system, and comprehensive file processing capabilities.

## 🚀 Features

### File Conversion Types
- **PDF Conversions**: PDF to images (PNG/JPG/WebP/TIFF), images to PDF
- **Document Conversions**: DOCX to PDF, PDF to DOCX, PPTX to PDF, PDF to PPTX
- **Image Processing**: Resize, rotate, compress images
- **PDF Operations**: Merge multiple PDFs, split PDFs, compress PDFs
- **OCR**: Extract text from images and PDFs
- **Watermarking**: Add text or image watermarks to files
- **URL Downloads**: Download and convert content from URLs

### Core Features
- **Premium Subscriptions**: Weekly, monthly, half-yearly, and yearly plans
- **Referral System**: Earn rewards by inviting users
- **Payment Integration**: PayPal, Cliq, Vodafone Cash, InstaPay
- **File Size Limits**: Different limits for free and premium users
- **Cloud Storage**: Automatic upload of large files to R2 storage
- **Admin Panel**: User management, logs, backups, maintenance
- **Daily Cleanup**: Automatic removal of old files from storage

### User Features
- Balance tracking
- Conversion history
- Support for multiple file formats
- Real-time processing status
- Error handling and notifications

## 📋 Requirements

- Python 3.8+
- MongoDB
- Telegram Bot Token
- PayPal API credentials (for payments)
- AWS R2 credentials (for cloud storage)

## 🛠️ Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/kareem2099/formate.git
   cd formate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Tesseract OCR:**
   ```bash
   # Ubuntu/Debian
   sudo apt-get install tesseract-ocr

   # macOS
   brew install tesseract

   # Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki
   ```

4. **Set up environment variables:**
   Create a `.env` file in the root directory with the following variables:
   ```env
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   ADMIN_USER_IDS=123456789,987654321
   MONGODB_URI=mongodb://localhost:27017/formate
   PAYPAL_CLIENT_ID=your_paypal_client_id
   PAYPAL_CLIENT_SECRET=your_paypal_client_secret
   R2_ACCESS_KEY_ID=your_r2_access_key
   R2_SECRET_ACCESS_KEY=your_r2_secret_key
   R2_BUCKET_NAME=your_r2_bucket
   R2_ENDPOINT_URL=https://your-account.r2.cloudflarestorage.com
   NOTIFICATION_CHANNEL_ID=@your_channel_username
   ```

5. **Initialize the database:**
   The bot will automatically create required collections on first run.

## 🚀 Running the Bot

1. **Start the bot:**
   ```bash
   python main.py
   ```

2. **Start the PayPal webhook server (optional):**
   ```bash
   python api/paypal_webhook.py
   ```
   Access at `http://localhost:5000`

## 📖 Usage

### For Users
1. Start a chat with the bot on Telegram
2. Send `/start` to see the main menu
3. Choose your conversion type
4. Upload files or provide URLs
5. Select options and receive converted files

### Available Commands
- `/start` - Start the bot and show main menu
- `/help` - Show help and available commands
- `/balance` - Check your balance
- `/referral` - View referral information
- `/payment` - Access payment options

### Conversion Commands
- `/pdf2png` - Convert PDF to PNG images
- `/png2pdf` - Convert PNG images to PDF
- `/jpg2pdf` - Convert JPG images to PDF
- `/webp2pdf` - Convert WebP images to PDF
- `/tiff2pdf` - Convert TIFF images to PDF
- `/docx2pdf` - Convert DOCX to PDF
- `/pdf2docx` - Convert PDF to DOCX
- `/pptx2pdf` - Convert PPTX to PDF
- `/pdf2pptx` - Convert PDF to PPTX
- `/ocr` - Extract text from images/PDFs
- `/mergepdf` - Merge multiple PDFs
- `/splitpdf` - Split PDF into multiple files
- `/compress` - Compress files
- `/watermark` - Add watermarks to files
- `/url` - Download and convert from URLs

### Admin Commands
- `/admin` - Access admin menu
- `/users` - View user statistics
- `/logs` - View system logs
- `/backup` - Create database backup
- `/maintenance` - Maintenance mode toggle
- `/pendingpayments` - View pending payments

## 🔧 Configuration

### File Size Limits
- **Free Users**: 10MB images, 25MB PDFs, 15MB Word docs, 30MB PowerPoint
- **Premium Users**: 50MB images, 100MB PDFs, 75MB Word docs, 150MB PowerPoint

### Premium Features
- Higher file size limits
- Unlimited daily conversions
- Priority processing
- Advanced options

### Referral System
- Earn credits by inviting new users
- Track referrals and earnings

## 💰 Payment & Premium

- **Subscription Plans**: Week ($7), Month ($15), Half-year ($60), Year ($150)
- **Lifetime Access**: Source code access ($270)
- **Payment Methods**: PayPal, Cliq (Jordan), Vodafone Cash (Egypt), InstaPay (Egypt)
- **Premium Benefits**: Higher limits, unlimited conversions, priority support

## 🔒 Security

- User authentication via Telegram
- Admin-only commands
- File validation and sanitization
- Secure payment processing
- Automatic cleanup of old files

## 🗄️ Database

Uses MongoDB with collections for:
- users
- conversions
- payments
- referrals
- files

## 🐳 Docker Support

A Dockerfile is provided for containerized deployment.

```bash
docker build -t formate .
docker run -p 5000:5000 formate
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📝 License

[Add your license information here]

## 📞 Support

For support, contact the bot administrators or create an issue on GitHub.

## 🙏 Acknowledgments

- Built with [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- PDF processing with [PyMuPDF](https://pymupdf.readthedocs.io/)
- Image processing with [Pillow](https://python-pillow.org/)
- OCR with [Tesseract](https://github.com/tesseract-ocr/tesseract)
- Cloud storage with [AWS SDK](https://aws.amazon.com/sdk-for-python/)
- Payments with [PayPal SDK](https://developer.paypal.com/)
