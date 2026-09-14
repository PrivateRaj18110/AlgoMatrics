"""Read-only access to the monitoring.v1 projections in the ops database.

The receiver lives in ``ops/backend`` and owns these tables. The platform reads
them; it never writes them, never validates on their behalf, and never
reinterprets what they contain.

Deliberately a separate store from :mod:`telemetry_store`, which reads the
``raj_monitor`` agent tables. The two ingest protocols are independent, and a
query that joined them would quietly assert an equivalence the contract does not
support.

Everything the producer sent passes through verbatim. In particular:

* ``freshness`` is the producer's **asserted state**. Nothing here evaluates a
  horizon, because monitoring.v1 has none — the contract requires receiver
  freshness to use source validity and trust, not arrival time.
* ``runtime`` stays the array of capture identifiers it is.
* ``source_environment`` (market reality) and ``receiver_deployment_environment``
  (our tier) are reported separately and never derived from one another.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from algo_platform.modules.operations.application.timestamps import to_utc_z
from algo_platform.shared.domain.errors import UnavailableError

#: Used when the receiver has not been told its own deployment tier.
UNKNOWN_DEPLOYMENT = "UNKNOWN"


def _sync_url(url: str) -> str:
    """Normalise to the installed synchronous psycopg driver."""
    if url.startswith("postgresql+asyncpg://"):
        return f"postgresql+psycopg://{url.removeprefix('postgresql+asyncpg://')}"
    if url.startswith("postgresql+psycopg2://"):
        return f"postgresql+psycopg://{url.removeprefix('postgresql+psycopg2://')}"
    if url.startswith("postgres://"):
        return f"postgresql+psycopg://{url.removeprefix('postgres://')}"
    if url.startswith("postgresql://"):
        return f"postgresql+psycopg://{url.removeprefix('postgresql://')}"
    return url


class MonitoringStore:
    """Reads monitoring.v1 projections, evidence and delivery state.

    Unset ``OPS_DATABASE_URL`` yields empty results rather than fixtures: an
    empty monitoring dashboard is honest, and invented monitoring data is the
    single worst thing this system could display.
    """

    def __init__(self, database_url: str | None) -> None:
        self._url = (database_url or "").strip()
        self._engine: Engine | None = None
        if self._url:
            connect_args = {"check_same_thread": False} if self._url.startswith("sqlite") else {}
            self._engine = create_engine(
                _sync_url(self._url),
                pool_pre_ping=True,
                future=True,
                connect_args=connect_args,
            )

    @property
    def configured(self) -> bool:
        return self._engine is not None

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        if self._engine is None:
            raise UnavailableError("OPS_DATABASE_URL is not configured")
        try:
            with self._engine.connect() as conn:
                yield conn
        except SQLAlchemyError as exc:
            raise UnavailableError("ops monitoring database is unavailable") from exc
        except (ImportError, ModuleNotFoundError) as exc:
            raise UnavailableError("ops monitoring database is unavailable") from exc

    # ----------------------------------------------------------------- #
    # Current state
    # ----------------------------------------------------------------- #
    def current_state(
        self,
        *,
        organisation_id: UUID | str | None = None,
        deployment: str = UNKNOWN_DEPLOYMENT,
        message_type: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Current projections for one receiver deployment tier and tenant organisation.

        ``deployment`` is **this receiver's** tier, not the producer's
        ``environment`` field — different axes, never derived from one another.
        It is applied in the WHERE clause rather than by the caller, so a staging
        observation cannot leak into a production response through a UI bug.
        """
        if not self.configured or not organisation_id:
            return []
        clauses = [
            "receiver_deployment_environment = :deployment",
            "organisation_id = :organisation_id",
        ]
        params: dict[str, Any] = {
            "deployment": deployment,
            "organisation_id": str(organisation_id),
            "limit": limit,
        }
        if message_type:
            clauses.append("message_type = :message_type")
            params["message_type"] = message_type
        sql = text(
            f"""
            SELECT message_type, capture_ref, source_id, source_instance,
                   source_sequence, message_id,
                   source_environment, receiver_deployment_environment,
                   generated_at, received_at,
                   source_as_of_json, coverage_json, freshness_json, trust_json,
                   runtime_json, payload_json
            FROM monitoring_projections
            WHERE {" AND ".join(clauses)}
            ORDER BY message_type, capture_ref
            LIMIT :limit
            """  # noqa: S608 - clauses are literals built above, never caller input
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [self._projection(row) for row in rows]

    def sources(
        self,
        *,
        organisation_id: UUID | str | None = None,
    ) -> list[dict[str, Any]]:
        """Ordered-acceptance state per publisher instance for one tenant organisation.

        ``refused_*`` counters are observability. A refused message was never
        accepted and appears nowhere as data — these exist so an operator can see
        a publisher delivering out of order.
        """
        if not self.configured or not organisation_id:
            return []
        sql = text(
            """
            SELECT source_id, source_instance, last_accepted_sequence,
                   last_accepted_message_id, accepted_count, duplicate_count,
                   refused_gap_count, refused_old_count, observed_gaps,
                   first_seen_at, last_seen_at
            FROM monitoring_sequence_state
            WHERE organisation_id = :organisation_id
            ORDER BY source_id, source_instance
            """
        )
        with self._connect() as conn:
            rows = conn.execute(sql, {"organisation_id": str(organisation_id)}).mappings().all()
        return [
            {
                "source_id": row["source_id"],
                "source_instance": row["source_instance"],
                # String, matching the wire representation.
                "last_accepted_sequence": str(row["last_accepted_sequence"]),
                "last_accepted_message_id": row["last_accepted_message_id"],
                "accepted_count": int(row["accepted_count"]),
                "duplicate_count": int(row["duplicate_count"]),
                "refused_gap_count": int(row["refused_gap_count"]),
                "refused_old_count": int(row["refused_old_count"]),
                "observed_refusals": _loads(row["observed_gaps"], []),
                "first_seen_at": to_utc_z(row["first_seen_at"]),
                "last_seen_at": to_utc_z(row["last_seen_at"]),
            }
            for row in rows
        ]

    def history(
        self,
        *,
        organisation_id: UUID | str | None = None,
        deployment: str = UNKNOWN_DEPLOYMENT,
        message_type: str | None = None,
        source_instance: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Evidence history, oldest first. Superseded observations are still here."""
        if not self.configured or not organisation_id:
            return []
        clauses = [
            "receiver_deployment_environment = :deployment",
            "organisation_id = :organisation_id",
        ]
        params: dict[str, Any] = {
            "deployment": deployment,
            "organisation_id": str(organisation_id),
            "limit": limit,
        }
        for column, value in (
            ("message_type", message_type),
            ("source_instance", source_instance),
        ):
            if value:
                clauses.append(f"{column} = :{column}")
                params[column] = value
        sql = text(
            f"""
            SELECT message_id, message_type, schema_version, source_id, source_instance,
                   source_sequence, source_environment, receiver_deployment_environment,
                   generated_at, received_at, source_as_of_json, coverage_json,
                   freshness_json, trust_json, runtime_json, request_sha256, capture_ref
            FROM monitoring_evidence
            WHERE {" AND ".join(clauses)}
            ORDER BY generated_at, sequence_ordinal
            LIMIT :limit
            """  # noqa: S608 - clauses are literals built above, never caller input
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [
            {
                "message_id": row["message_id"],
                "message_type": row["message_type"],
                "schema_version": row["schema_version"],
                "source_id": row["source_id"],
                "source_instance": row["source_instance"],
                "source_sequence": row["source_sequence"],
                "capture_ref": row["capture_ref"],
                "source_environment": row["source_environment"],
                "receiver_deployment_environment": row["receiver_deployment_environment"],
                "runtime": _loads(row["runtime_json"], []),
                "source_as_of": _loads(row["source_as_of_json"], {}),
                "generated_at": to_utc_z(row["generated_at"]),
                "received_at": to_utc_z(row["received_at"]),
                "freshness": _loads(row["freshness_json"], {}),
                "trust": _loads(row["trust_json"], {}),
                "coverage": _loads(row["coverage_json"], {}),
                "request_sha256": row["request_sha256"],
            }
            for row in rows
        ]

    # ----------------------------------------------------------------- #
    @staticmethod
    def _projection(row: Any) -> dict[str, Any]:
        """Every producer object passes through verbatim.

        No value is unwrapped, no ratio computed, no freshness derived.
        """
        return {
            "message_type": row["message_type"],
            "capture_ref": row["capture_ref"] or None,
            "source_id": row["source_id"],
            "source_instance": row["source_instance"],
            # The wire value, as a string. Never re-rendered.
            "source_sequence": row["source_sequence"],
            "message_id": row["message_id"],
            # Market reality, from the producer.
            "source_environment": row["source_environment"],
            # Our deployment tier, from receiver configuration.
            "receiver_deployment_environment": row["receiver_deployment_environment"],
            # An array of capture identifiers, never collapsed to an enum.
            "runtime": _loads(row["runtime_json"], []),
            "source_as_of": _loads(row["source_as_of_json"], {}),
            "generated_at": to_utc_z(row["generated_at"]),
            "received_at": to_utc_z(row["received_at"]),
            # Asserted by the source. No horizon is evaluated anywhere.
            "freshness": _loads(row["freshness_json"], {}),
            "trust": _loads(row["trust_json"], {}),
            "coverage": _loads(row["coverage_json"], {}),
            "payload": _loads(row["payload_json"], {}),
        }


def _loads(raw: Any, fallback: Any) -> Any:
    if raw is None:
        return fallback
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return fallback
