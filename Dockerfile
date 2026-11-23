# 1. Build React frontend
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 2. Run FastAPI backend + Tesseract OCR
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/
COPY --from=web /web/dist ./frontend/dist

WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1
# Render sets PORT itself; fall back to Render's default (10000) if it does not.
CMD ["sh", "-c", "echo Starting on port ${PORT:-10000}; uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
