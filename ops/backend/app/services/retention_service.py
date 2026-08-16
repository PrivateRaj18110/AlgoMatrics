"""Disabled-by-default retention for the AWS ops data plane.

This module deliberately lives outside request handling. Retention is
destructive, so operators run it as an explicit job/CLI with dry-run support.
The policies are separate because telemetry, operational events, dead letters,
sessions, raw EOD bytes and derived analytics do not share one safe lifetime.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.database.session import database_enabled, get_sessionmaker
from app.models import (
    DeadLetter,
    EodDataset,
    EodDatasetFile,
    Event,
    Log,
    Metric,
    QuantReport,
    Trade,
    TradingSession,
    utcnow,
)
from app.storage import get_dataset_storage

TERMINAL_EOD_STATUSES = {"COMPLETE", "FAILED", "QUARANTINED", "CONFLICT"}
CLOSED_SESSION_STATUSES = {"closed", "completed", "aborted", "failed", "stopped"}


@dataclass(frozen=True)
class RetentionOutcome:
    policy: str
    retentionDays: int
    cutoff: str | None
    matched: int
    deleted: int
    dryRun: bool
    note: str | None = None


def _cutoff(days: int):
    return utcnow() - timedelta(days=days)


def _disabled(policy: str, days: int, dry_run: bool) -> RetentionOutcome:
    return RetentionOutcome(policy, days, None, 0, 0, dry_run, "disabled")


def _count(session, table, where_clause) -> int:
    return int(
        session.execute(select(func.count()).select_from(table).where(where_clause)).scalar_one()
    )


def _delete(session, table, where_clause) -> int:
    result = session.execute(table.__table__.delete().where(where_clause))
    return int(result.rowcount or 0)


def _simple_table_retention(
    *,
    policy: str,
    table,
    time_column,
    days: int,
    dry_run: bool,
) -> RetentionOutcome:
    if days <= 0:
        return _disabled(policy, days, dry_run)
    cutoff = _cutoff(days)
    where_clause = time_column < cutoff
    session = get_sessionmaker()()
    try:
        matched = _count(session, table, where_clause)
        deleted = 0 if dry_run else _delete(session, table, where_clause)
        if not dry_run:
            session.commit()
        return RetentionOutcome(policy, days, cutoff.isoformat(), matched, deleted, dry_run)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _telemetry_retention(settings: Settings, dry_run: bool) -> list[RetentionOutcome]:
    days = settings.telemetry_retention_days
    return [
        _simple_table_retention(
            policy="telemetry.metrics",
            table=Metric,
            time_column=Metric.time,
            days=days,
            dry_run=dry_run,
        ),
        _simple_table_retention(
            policy="telemetry.trades",
            table=Trade,
            time_column=Trade.time,
            days=days,
            dry_run=dry_run,
        ),
        _simple_table_retention(
            policy="telemetry.logs",
            table=Log,
            time_column=Log.time,
            days=days,
            dry_run=dry_run,
        ),
    ]


def _session_retention(settings: Settings, dry_run: bool) -> RetentionOutcome:
    days = settings.session_retention_days
    if days <= 0:
        return _disabled("sessions", days, dry_run)
    cutoff = _cutoff(days)
    effective_time = func.coalesce(
        TradingSession.ended_at,
        TradingSession.last_event_at,
        TradingSession.updated_at,
        TradingSession.created_at,
    )
    where_clause = (
        TradingSession.status.in_(CLOSED_SESSION_STATUSES)
        & (effective_time < cutoff)
    )
    session = get_sessionmaker()()
    try:
        matched = _count(session, TradingSession, where_clause)
        deleted = 0 if dry_run else _delete(session, TradingSession, where_clause)
        if not dry_run:
            session.commit()
        return RetentionOutcome("sessions", days, cutoff.isoformat(), matched, deleted, dry_run)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _eod_metadata_retention(settings: Settings, dry_run: bool) -> RetentionOutcome:
    days = settings.eod_metadata_retention_days
    if days <= 0:
        return _disabled("eod.metadata", days, dry_run)
    cutoff = _cutoff(days)
    effective_time = func.coalesce(
        EodDataset.finalized_at,
        EodDataset.completed_at,
        EodDataset.updated_at,
        EodDataset.received_at,
    )
    where_clause = EodDataset.status.in_(TERMINAL_EOD_STATUSES) & (effective_time < cutoff)
    session = get_sessionmaker()()
    try:
        dataset_ids = [
            row[0]
            for row in session.execute(select(EodDataset.dataset_id).where(where_clause)).all()
        ]
        matched = len(dataset_ids)
        deleted = 0
        if not dry_run and dataset_ids:
            session.execute(
                EodDatasetFile.__table__.delete().where(
                    EodDatasetFile.__table__.c.dataset_id.in_(dataset_ids)
                )
            )
            deleted = _delete(session, EodDataset, where_clause)
            session.commit()
        return RetentionOutcome("eod.metadata", days, cutoff.isoformat(), matched, deleted, dry_run)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _eod_raw_retention(settings: Settings, dry_run: bool) -> RetentionOutcome:
    days = settings.eod_raw_retention_days
    if days <= 0:
        return _disabled("eod.raw", days, dry_run)
    cutoff = _cutoff(days)
    effective_time = func.coalesce(
        EodDataset.finalized_at,
        EodDataset.completed_at,
        EodDataset.updated_at,
        EodDataset.received_at,
    )
    where_clause = (
        EodDataset.status.in_(TERMINAL_EOD_STATUSES)
        & (EodDataset.raw_deleted_at.is_(None))
        & (effective_time < cutoff)
    )
    session = get_sessionmaker()()
    try:
        rows = session.execute(select(EodDataset.dataset_id).where(where_clause)).all()
        dataset_ids = [row[0] for row in rows]
        removed_objects = 0
        if not dry_run and dataset_ids:
            storage = get_dataset_storage()
            for dataset_id in dataset_ids:
                removed_objects += storage.delete_dataset(dataset_id)
                dataset = session.get(EodDataset, dataset_id)
                if dataset is not None:
                    dataset.raw_deleted_at = utcnow()
            session.commit()
        return RetentionOutcome(
            "eod.raw",
            days,
            cutoff.isoformat(),
            len(dataset_ids),
            removed_objects,
            dry_run,
            "deleted counts raw storage objects/files; metadata is retained",
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run_retention(*, dry_run: bool = True, settings: Settings | None = None) -> dict[str, Any]:
    """Run every configured retention policy and return an auditable summary."""
    if not database_enabled():
        raise RuntimeError("DATABASE_URL is not configured; retention requires the ops database")

    settings = settings or get_settings()
    outcomes: list[RetentionOutcome] = []
    outcomes.extend(_telemetry_retention(settings, dry_run))
    outcomes.append(
        _simple_table_retention(
            policy="operational.events",
            table=Event,
            time_column=Event.time,
            days=settings.operational_event_retention_days,
            dry_run=dry_run,
        )
    )
    outcomes.append(
        _simple_table_retention(
            policy="dead_letters",
            table=DeadLetter,
            time_column=DeadLetter.received_at,
            days=settings.dead_letter_retention_days,
            dry_run=dry_run,
        )
    )
    outcomes.append(_session_retention(settings, dry_run))
    outcomes.append(_eod_raw_retention(settings, dry_run))
    outcomes.append(_eod_metadata_retention(settings, dry_run))
    outcomes.append(
        _simple_table_retention(
            policy="quant.reports",
            table=QuantReport,
            time_column=QuantReport.updated_at,
            days=settings.quant_report_retention_days,
            dry_run=dry_run,
        )
    )
    return {
        "dryRun": dry_run,
        "generatedAt": utcnow().isoformat(),
        "matched": sum(outcome.matched for outcome in outcomes),
        "deleted": sum(outcome.deleted for outcome in outcomes),
        "policies": [asdict(outcome) for outcome in outcomes],
    }
