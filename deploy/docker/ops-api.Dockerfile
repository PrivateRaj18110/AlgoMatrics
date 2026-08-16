# AlgoMatrics Ops Dashboard — backend image (telemetry ingest + platform proxy)
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first to leverage Docker layer caching.
COPY ops/backend/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy application source.
COPY ops/backend .

# Run as a non-root user.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# Production-style launch (no --reload).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
