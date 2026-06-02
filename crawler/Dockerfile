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
    # Playwright Chromium 런타임 의존성 (--with-deps 미사용: slim 이미지에 없는 폰트 패키지 회피)
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    libxext6 \
    libxi6 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --index-url ${PYTORCH_INDEX_URL} torch torchvision
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install pyhwp
RUN pip install pyhwp six lxml

# JS 동적 렌더링 페이지 재크롤용 헤드리스 Chromium 설치.
# OS 의존성은 위 apt-get 블록에서 직접 설치했으므로 --with-deps 는 사용하지 않는다.
# CRAWLER_ENABLE_JS_RENDER=1 일 때만 런타임에 사용된다.
RUN python -m playwright install chromium

COPY . /app
