FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y make pkg-config gcc g++ swig tesseract-ocr libleptonica-dev libtesseract-dev libjbig2dec-dev libopenjp2-7-dev libjpeg-dev libfreetype-dev libgumbo-dev libharfbuzz-dev libpng-dev libmujs-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

WORKDIR /app

CMD ["python", "main.py"]
