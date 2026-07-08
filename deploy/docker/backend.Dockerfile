FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock* ./
COPY backend backend
COPY packages packages
COPY agents agents
RUN uv sync --no-dev

FROM python:3.13-slim AS runtime
RUN groupadd --system app && useradd --system --gid app --home /app app \
    && mkdir -p /app && chown app:app /app
WORKDIR /app
COPY --from=builder --chown=app:app /app /app
COPY --chown=app:app scripts scripts
COPY --chmod=0755 deploy/docker/entrypoint.sh /usr/local/bin/entrypoint.sh
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend/src
# Writable directories for uploads and strategy artifacts (image is otherwise read-only).
RUN mkdir -p /app/var/uploads /app/var/artifacts && chown -R app:app /app/var
USER app
EXPOSE 8000
ENTRYPOINT ["entrypoint.sh"]
CMD ["api"]
