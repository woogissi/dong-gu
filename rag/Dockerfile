FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY ./rag/requirements.txt /app/rag/requirements.txt

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch
RUN pip install --no-cache-dir -r /app/rag/requirements.txt

COPY ./rag /app/rag

ENV PYTHONPATH=/app

CMD ["tail", "-f", "/dev/null"]