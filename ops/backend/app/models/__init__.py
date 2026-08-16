"""SQLAlchemy ORM models for the persisted telemetry entities.

Importing this package registers every model on ``Base.metadata`` so Alembic
autogenerate and ``create_all`` see the full schema. The five live entities
(machines, events, logs, trades, metrics) plus the idempotency table are mapped
here; strategies/brokers/accounts/alerts remain mock and are intentionally not
persisted in this milestone.
"""

from app.models.base import Base, utcnow
from app.models.dead_letter import DeadLetter
from app.models.dedup import IngestDedup
from app.models.eod import EodDataset, EodDatasetFile
from app.models.event import Event
from app.models.log import Log
from app.models.machine import Machine
from app.models.metric import Metric
from app.models.quant import QuantReport
from app.models.session import TradingSession
from app.models.sync_state import SyncState
from app.models.trade import Trade

__all__ = [
    "Base",
    "utcnow",
    "Machine",
    "Event",
    "Log",
    "Trade",
    "Metric",
    "QuantReport",
    "IngestDedup",
    "EodDataset",
    "EodDatasetFile",
    "SyncState",
    "TradingSession",
    "DeadLetter",
]
