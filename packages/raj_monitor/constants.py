"""Shared constants for the Raj Monitor platform.

Single source of truth for protocol paths, defaults and limits used across the
SDK, the Local Agent and the backend transport. Editing a value here changes it
everywhere; nothing else should hard-code these numbers.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Versioning
# --------------------------------------------------------------------------- #
SDK_VERSION = "4.0.0"
PROTOCOL_VERSION = 1

# --------------------------------------------------------------------------- #
# Local Agent (SDK -> Agent, localhost only)
# --------------------------------------------------------------------------- #
DEFAULT_AGENT_HOST = "127.0.0.1"
DEFAULT_AGENT_PORT = 8765

# Local HTTP routes exposed by the agent for the SDK.
LOCAL_INGEST_PATH = "/ingest"      # POST a single envelope
LOCAL_HEALTH_PATH = "/health"      # GET agent liveness
LOCAL_STATS_PATH = "/stats"        # GET agent queue/upload stats

# Header carrying the shared local token (SDK <-> Agent).
LOCAL_TOKEN_HEADER = "X-Raj-Local-Token"

# --------------------------------------------------------------------------- #
# Backend (Agent -> FastAPI, HTTPS)
# --------------------------------------------------------------------------- #
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000/api"

AGENT_REGISTER_PATH = "/agent/register"
AGENT_HEARTBEAT_PATH = "/agent/heartbeat"
AGENT_EVENTS_PATH = "/agent/events"
AGENT_METRICS_PATH = "/agent/metrics"
AGENT_TRADES_PATH = "/agent/trades"
AGENT_LOGS_PATH = "/agent/logs"
AGENT_BATCH_PATH = "/agent/batch"

# Header carrying the backend auth token (Agent <-> Backend).
BACKEND_TOKEN_HEADER = "X-Raj-Agent-Token"
AGENT_ID_HEADER = "X-Raj-Agent-Id"

# --------------------------------------------------------------------------- #
# Event "kinds" — the discriminator on every queued item.
# --------------------------------------------------------------------------- #
KIND_START = "start"
KIND_STOP = "stop"
KIND_HEARTBEAT = "heartbeat"
KIND_METRIC = "metric"
KIND_METRICS = "metrics"          # full host metrics snapshot
KIND_TRADE = "trade"
KIND_POSITION = "position"
KIND_EVENT = "event"
KIND_ERROR = "error"
KIND_LOG = "log"

ALL_KINDS = frozenset({
    KIND_START, KIND_STOP, KIND_HEARTBEAT, KIND_METRIC, KIND_METRICS,
    KIND_TRADE, KIND_POSITION, KIND_EVENT, KIND_ERROR, KIND_LOG,
})

# Which kinds route to which backend endpoint when uploaded individually.
KIND_TO_PATH = {
    KIND_HEARTBEAT: AGENT_HEARTBEAT_PATH,
    KIND_METRICS: AGENT_METRICS_PATH,
    KIND_METRIC: AGENT_METRICS_PATH,
    KIND_TRADE: AGENT_TRADES_PATH,
    KIND_POSITION: AGENT_TRADES_PATH,
    KIND_EVENT: AGENT_EVENTS_PATH,
    KIND_ERROR: AGENT_EVENTS_PATH,
    KIND_START: AGENT_EVENTS_PATH,
    KIND_STOP: AGENT_EVENTS_PATH,
    KIND_LOG: AGENT_LOGS_PATH,
}

# --------------------------------------------------------------------------- #
# Severities / levels
# --------------------------------------------------------------------------- #
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"
SEVERITY_CRITICAL = "critical"

# The backend event terminal only models info/warning/critical; "error" maps up.
EVENT_SEVERITIES = ("info", "warning", "critical")

LOG_LEVELS = ("debug", "info", "warn", "error")
EVENT_CATEGORIES = ("trade", "strategy", "machine", "broker", "system", "database", "risk")

# Trade actions supported by monitor.trade(action=...).
TRADE_ACTIONS = ("open", "close", "modify", "pending", "cancelled", "rejected")

# --------------------------------------------------------------------------- #
# Defaults — intervals (seconds)
# --------------------------------------------------------------------------- #
DEFAULT_HEARTBEAT_INTERVAL = 5.0
DEFAULT_METRICS_INTERVAL = 10.0
DEFAULT_UPLOAD_INTERVAL = 3.0

# --------------------------------------------------------------------------- #
# Defaults — queue / batching
# --------------------------------------------------------------------------- #
DEFAULT_QUEUE_MAX_SIZE = 100_000
DEFAULT_BATCH_SIZE = 200
DEFAULT_SDK_QUEUE_SIZE = 10_000

# --------------------------------------------------------------------------- #
# Defaults — retry / circuit breaker
# --------------------------------------------------------------------------- #
DEFAULT_RETRY_COUNT = 5
DEFAULT_BACKOFF_BASE = 0.5
DEFAULT_BACKOFF_MAX = 30.0
DEFAULT_TIMEOUT = 10.0

# Circuit breaker: open after N consecutive failures, recover after cooldown.
DEFAULT_BREAKER_THRESHOLD = 5
DEFAULT_BREAKER_COOLDOWN = 30.0

# --------------------------------------------------------------------------- #
# Defaults — logging
# --------------------------------------------------------------------------- #
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_DIR = "logs"
DEFAULT_LOG_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_LOG_BACKUP_COUNT = 5

# Compress payloads above this size (bytes) before upload.
COMPRESS_MIN_BYTES = 512

# Default on-disk queue database filename (per machine).
DEFAULT_QUEUE_DB = "raj_agent_queue.db"
