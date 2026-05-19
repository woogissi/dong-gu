FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    curl \
    openjdk-21-jre \
    && rm -rf /var/lib/apt/lists/*

COPY ./rag/requirements.txt /app/rag/requirements.txt
COPY ./rag/evaluation/autorag/requirements.txt /app/rag/evaluation/autorag/requirements.txt

RUN pip install --no-cache-dir --index-url ${PYTORCH_INDEX_URL} torch
RUN pip install --no-cache-dir -r /app/rag/requirements.txt
RUN pip install --no-cache-dir -r /app/rag/evaluation/autorag/requirements.txt

COPY ./rag /app/rag

CMD ["python", "-m", "rag.evaluation.autorag.scripts.export_corpus_to_autorag", "--check-connection"]
