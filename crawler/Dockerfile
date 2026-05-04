FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    curl \
    libreoffice \
    libreoffice-writer \
    tesseract-ocr \
    tesseract-ocr-kor \
    fonts-noto-cjk \
    tesseract-ocr \
    tesseract-ocr-kor \
    tesseract-ocr-eng \
    libgl1 \
    libreoffice \
    fonts-nanum \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app
