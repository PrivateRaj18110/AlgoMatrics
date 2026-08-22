# AI-CIO market-intelligence pipeline.
#
# A standalone data producer: it runs the AI-CIO pipeline (regime + rankings),
# news, and options / institutional-flow modules on a schedule, writing them into
# a DuckDB file on a shared volume that the platform's API and trading engine read
# (read-only). It has its own, heavier dependency set (hmmlearn / scikit-learn /
# ruptures / datasketch) and is intentionally NOT built on the backend image.
#
# Hermetic by default: DATA_SOURCE=synthetic needs no network. Point it at real
# data (AICIO_DATA_SOURCE=yfinance) only where outbound access exists — and verify
# the first real run, per the AI-CIO README's caveats.
FROM python:3.13-slim

WORKDIR /app

# Build context is the repo root (see docker-compose aicio-pipeline service).
COPY ai_cio_phase1/ai_cio_phase1/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY ai_cio_phase1/ai_cio_phase1/ ./

ENV AICIO_DB_PATH=/data/aicio.duckdb \
    AICIO_DATA_SOURCE=synthetic \
    AICIO_REFRESH_SECONDS=86400

# Order matters: run_pipeline writes the OHLCV that run_market_intel needs to
# build option chains (spot prices), so the pipeline goes first. Options/flow
# then compute and fold into the *next* cycle's ranking (a one-cycle lag on the
# oi_score dimension, by design). A failed cycle logs and retries next interval
# rather than crashing the service.
CMD ["sh", "-c", "mkdir -p /data; while true; do python run_pipeline.py && python run_market_intel.py && python run_news.py || echo 'aicio: pipeline cycle failed, will retry next interval'; echo \"aicio: sleeping ${AICIO_REFRESH_SECONDS}s until next run\"; sleep \"${AICIO_REFRESH_SECONDS}\"; done"]
