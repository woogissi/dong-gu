FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    curl \
    libreoffice \
    libreoffice-writer \
    fonts-noto-cjk \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --index-url ${PYTORCH_INDEX_URL} torch torchvision
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install pyhwp
RUN pip install pyhwp six lxml

COPY . /app
