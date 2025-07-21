FROM python:3.9-slim-bookworm

RUN apt-get update && apt-get install -y swig tesseract-ocr libleptonica-dev libtesseract-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

WORKDIR /app

CMD ["python", "main.py"]
