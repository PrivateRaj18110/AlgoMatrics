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

# The canonical monitoring.v1 schema, which the receiver refuses to accept any
# message without.
#
# It lives at the repository root, outside ops/backend, so the COPY above does
# not bring it. Without it the container has no contract to validate against and
# every monitoring message is refused — while /api/health, which the liveness
# and readiness probes use, keeps reporting the pod healthy. The failure is
# therefore silent, which is why the schema ships explicitly rather than being
# left to a path fallback.
#
# Byte-for-byte: message_id is a content address over canonical JSON and the
# request digest is a SHA-256 of exact bytes, so any rewriting here would break
# both. `.gitattributes` marks this tree -text for the same reason, and COPY
# preserves the bytes.
COPY schemas/monitoring-v1 ./schemas/monitoring-v1

# Run as a non-root user.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# Production-style launch (no --reload).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
