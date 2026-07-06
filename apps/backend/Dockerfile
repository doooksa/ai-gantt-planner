# Backend image — FastAPI + MCP in one process.
# Pinned to Python 3.12 per the fixed stack.
FROM python:3.12-slim

# - PYTHONUNBUFFERED: logs flush immediately (Render/Compose show them live).
# - PYTHONDONTWRITEBYTECODE: no .pyc clutter in the image.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install deps first so the layer is cached across code changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code (the DB file is created at runtime in this writable dir).
COPY app ./app

# Render injects $PORT; default to 8000 for local `docker run` / compose.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
