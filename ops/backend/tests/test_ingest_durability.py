"""Durability, idempotency, acknowledgement and sequence tracking.

These exercise the real database path. Each ``_run_backend`` call is a fresh
interpreter, which is what makes the restart assertions meaningful: the
repositories are bound at import time from ``DATABASE_URL``, so a second process
against the same file genuinely re-reads persisted state rather than a warm
in-memory buffer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]

FLEET_TOKEN = "durability-fleet-token"
AGENT_HEADERS = {"X-Raj-Agent-Token": FLEET_TOKEN, "X-Raj-Agent-Id": "agent-dur-01"}


def _environment(database_url: str | None) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(BACKEND_DIR), env.get("PYTHONPATH", "")) if part
    )
    env["RAJ_AGENT_TOKEN"] = FLEET_TOKEN
    env["RAJ_DASHBOARD_TOKEN"] = "durability-dashboard-token"
    env.pop("RAJ_AGENT_TOKENS", None)
    env.pop("ENVIRONMENT", None)
    if database_url is None:
        env.pop("DATABASE_URL", None)
    else:
        env["DATABASE_URL"] = database_url
    return env


def _run_backend(code: str, database_url: str | None = None) -> dict:
    """Run ``code`` in a fresh interpreter with the ingest prelude prepended.

    Each block is dedented *separately* before joining: they are written at
    different indentation levels in this file, so dedenting the concatenation
    would find no common prefix and produce invalid Python.
    """
    script = textwrap.dedent(_PRELUDE) + "\n" + textwrap.dedent(code)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND_DIR,
        env=_environment(database_url),
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def _migrate(database_url: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=_environment(database_url),
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.fixture
def database(tmp_path: Path) -> str:
    url = f"sqlite:///{(tmp_path / 'ingest.db').as_posix()}"
    _migrate(url)
    return url


_PRELUDE = """
    import json
    from fastapi.testclient import TestClient
    from main import app

    HEADERS = %r
    """ % (AGENT_HEADERS,)


def _batch(items: list[dict], machine: str = "gcp-trading-01", **extra) -> dict:
    return {"agentId": "agent-dur-01", "machine": machine, "items": items, **extra}


# --------------------------------------------------------------------------- #
# Durability across restart
# --------------------------------------------------------------------------- #
def test_telemetry_survives_process_restart(database: str) -> None:
    """Trades, events, metrics and dedup all outlive the process that wrote them."""
    written = _run_backend(
        """
        payload = {
            "agentId": "agent-dur-01", "machine": "gcp-trading-01",
            "items": [
                {"id": "d-evt-1", "kind": "event", "machine": "gcp-trading-01",
                 "strategy": "S5-10",
                 "data": {"category": "strategy", "severity": "info", "message": "hello"}},
                {"id": "d-trd-1", "kind": "trade", "machine": "gcp-trading-01",
                 "strategy": "S5-10",
                 "data": {"symbol": "NIFTY", "direction": "long", "action": "close",
                          "entry": 100.0, "exit": 110.0, "quantity": 1, "pnl": 10.0}},
                {"id": "d-met-1", "kind": "metric", "machine": "gcp-trading-01",
                 "strategy": "S5-10", "data": {"name": "sharpe", "value": 1.84}},
            ],
        }
        with TestClient(app) as c:
            r = c.post("/api/agent/batch", json=payload, headers=HEADERS)
        print(json.dumps({"status": r.status_code, "ack": r.json()}))
        """,
        database,
    )
    assert written["status"] == 200, written
    assert written["ack"]["processed"] == 3
    assert written["ack"]["failed"] == 0

    # Fresh interpreter, same database file.
    reloaded = _run_backend(
        """
        from app.repositories import events_repo, metrics_repo, trades_repo
        print(json.dumps({
            "events": len(events_repo.list()),
            "trades": len(trades_repo.list()),
            "metrics": len(metrics_repo.list()),
        }))
        """,
        database,
    )
    assert reloaded["events"] >= 1
    assert reloaded["trades"] >= 1
    assert reloaded["metrics"] >= 1


def test_metrics_and_trades_are_persisted_not_dropped(database: str) -> None:
    """In mock mode these two repositories silently discard writes.

    That was the production configuration before Phase 2 — this test is the
    regression guard that a real database actually stores them.
    """
    result = _run_backend(
        """
        from app.repositories import metrics_repo, trades_repo
        print(json.dumps({
            "metrics_repo": type(metrics_repo).__name__,
            "trades_repo": type(trades_repo).__name__,
        }))
        """,
        database,
    )
    assert result["metrics_repo"] == "SqlMetricsRepository"
    assert result["trades_repo"] == "SqlTradesRepository"


# --------------------------------------------------------------------------- #
# Idempotency
# --------------------------------------------------------------------------- #
def test_duplicate_envelope_is_idempotent(database: str) -> None:
    result = _run_backend(
        """
        from app.repositories import events_repo
        item = {"id": "dup-1", "kind": "event", "machine": "gcp-trading-01",
                "strategy": "S5-10",
                "data": {"category": "strategy", "severity": "info", "message": "once"}}
        payload = {"agentId": "agent-dur-01", "machine": "gcp-trading-01", "items": [item]}
        with TestClient(app) as c:
            first = c.post("/api/agent/batch", json=payload, headers=HEADERS).json()
            second = c.post("/api/agent/batch", json=payload, headers=HEADERS).json()
        print(json.dumps({
            "first": {"processed": first["processed"], "duplicate": first["duplicate"]},
            "second": {"processed": second["processed"], "duplicate": second["duplicate"]},
            "events": len(events_repo.list()),
        }))
        """,
        database,
    )
    assert result["first"] == {"processed": 1, "duplicate": 0}
    assert result["second"] == {"processed": 0, "duplicate": 1}
    assert result["events"] == 1, "a redelivered envelope must not create a second row"


def test_duplicate_batch_replay_is_safe(database: str) -> None:
    """A whole batch replayed after a crash-before-ack produces no new rows."""
    result = _run_backend(
        """
        from app.repositories import events_repo, trades_repo
        items = [
            {"id": f"replay-{i}", "kind": "event", "machine": "gcp-trading-01",
             "strategy": "S5-10",
             "data": {"category": "strategy", "severity": "info", "message": str(i)}}
            for i in range(5)
        ] + [
            {"id": "replay-trade", "kind": "trade", "machine": "gcp-trading-01",
             "strategy": "S5-10",
             "data": {"symbol": "NIFTY", "direction": "long", "action": "close",
                      "entry": 1.0, "exit": 2.0, "quantity": 1, "pnl": 1.0}},
        ]
        payload = {"agentId": "agent-dur-01", "machine": "gcp-trading-01", "items": items}
        with TestClient(app) as c:
            # `seed_if_empty` loads demo trades on first DB startup, so measure
            # the delta this batch causes rather than an absolute row count.
            before = len(trades_repo.list())
            a = c.post("/api/agent/batch", json=payload, headers=HEADERS).json()
            after_first = len(trades_repo.list())
            b = c.post("/api/agent/batch", json=payload, headers=HEADERS).json()
            d = c.post("/api/agent/batch", json=payload, headers=HEADERS).json()
            after_replays = len(trades_repo.list())
        print(json.dumps({
            "first_processed": a["processed"], "second_duplicate": b["duplicate"],
            "third_duplicate": d["duplicate"],
            "events": len(events_repo.list()),
            "trades_added": after_first - before,
            "trades_added_by_replays": after_replays - after_first,
        }))
        """,
        database,
    )
    assert result["first_processed"] == 6
    assert result["second_duplicate"] == 6
    assert result["third_duplicate"] == 6
    # 5 event envelopes + 1 event derived from the trade (`_handle_trade` emits
    # a trade event alongside the blotter row) — and, crucially, no more after
    # two full replays. Events are not seeded, so this count is absolute.
    assert result["events"] == 6
    assert result["trades_added"] == 1
    assert result["trades_added_by_replays"] == 0, "replays must not duplicate the blotter"


def test_dedup_survives_restart(database: str) -> None:
    """The idempotency table is durable, so replay after a restart is still safe."""
    _run_backend(
        """
        item = {"id": "restart-dup", "kind": "event", "machine": "gcp-trading-01",
                "strategy": "S5-10",
                "data": {"category": "strategy", "severity": "info", "message": "x"}}
        with TestClient(app) as c:
            c.post("/api/agent/batch",
                   json={"agentId": "agent-dur-01", "machine": "gcp-trading-01",
                         "items": [item]}, headers=HEADERS)
        print(json.dumps({"ok": True}))
        """,
        database,
    )
    after = _run_backend(
        """
        from app.repositories import events_repo
        item = {"id": "restart-dup", "kind": "event", "machine": "gcp-trading-01",
                "strategy": "S5-10",
                "data": {"category": "strategy", "severity": "info", "message": "x"}}
        with TestClient(app) as c:
            ack = c.post("/api/agent/batch",
                         json={"agentId": "agent-dur-01", "machine": "gcp-trading-01",
                               "items": [item]}, headers=HEADERS).json()
        print(json.dumps({"duplicate": ack["duplicate"], "events": len(events_repo.list())}))
        """,
        database,
    )
    assert after["duplicate"] == 1
    assert after["events"] == 1


# --------------------------------------------------------------------------- #
# Acknowledgement accuracy
# --------------------------------------------------------------------------- #
def test_ack_reports_mixed_outcomes_accurately(database: str) -> None:
    """The bug this replaces: `processed = len(items)` regardless of reality.

    A batch of one good, one duplicate and one unroutable envelope must report
    exactly that — otherwise the agent deletes data the server never stored.
    """
    result = _run_backend(
        """
        good = {"id": "mix-good", "kind": "event", "machine": "gcp-trading-01",
                "strategy": "S5-10",
                "data": {"category": "strategy", "severity": "info", "message": "ok"}}
        with TestClient(app) as c:
            c.post("/api/agent/batch",
                   json={"agentId": "agent-dur-01", "machine": "gcp-trading-01",
                         "items": [good]}, headers=HEADERS)
            mixed = c.post("/api/agent/batch", json={
                "agentId": "agent-dur-01", "machine": "gcp-trading-01",
                "items": [
                    good,
                    {"id": "mix-new", "kind": "event", "machine": "gcp-trading-01",
                     "strategy": "S5-10",
                     "data": {"category": "strategy", "severity": "info", "message": "new"}},
                    {"id": "mix-bad", "kind": "totally-unknown-kind",
                     "machine": "gcp-trading-01", "strategy": "S5-10", "data": {}},
                ],
            }, headers=HEADERS)
        body = mixed.json()
        print(json.dumps({
            "status": mixed.status_code, "total": body["total"],
            "processed": body["processed"], "duplicate": body["duplicate"],
            "rejected": body["rejected"], "failed": body["failed"],
            "outcomes": sorted((o["id"], o["status"]) for o in body["outcomes"]),
            "accepted": body["accepted"],
        }))
        """,
        database,
    )
    assert result["status"] == 200
    assert result["total"] == 3
    assert result["processed"] == 1   # only the genuinely new envelope
    assert result["duplicate"] == 1
    assert result["rejected"] == 1
    assert result["failed"] == 0
    assert result["outcomes"] == [["mix-bad", "rejected"], ["mix-good", "duplicate"]]
    # No transient failure, so the agent may safely drop the batch from its queue.
    assert result["accepted"] is True


def test_all_accepted_batch_reports_clean_counts(database: str) -> None:
    result = _run_backend(
        """
        items = [{"id": f"clean-{i}", "kind": "event", "machine": "gcp-trading-01",
                  "strategy": "S5-10",
                  "data": {"category": "strategy", "severity": "info", "message": str(i)}}
                 for i in range(4)]
        with TestClient(app) as c:
            body = c.post("/api/agent/batch",
                          json={"agentId": "agent-dur-01", "machine": "gcp-trading-01",
                                "items": items}, headers=HEADERS).json()
        print(json.dumps({
            "processed": body["processed"], "total": body["total"],
            "duplicate": body["duplicate"], "rejected": body["rejected"],
            "failed": body["failed"], "outcomes": body["outcomes"],
        }))
        """,
        database,
    )
    assert result == {"processed": 4, "total": 4, "duplicate": 0, "rejected": 0,
                      "failed": 0, "outcomes": None}


def test_rejected_envelope_is_dead_lettered(database: str) -> None:
    """A permanently unprocessable envelope is recorded, not silently dropped."""
    result = _run_backend(
        """
        from app.repositories import dead_letter_repo
        with TestClient(app) as c:
            body = c.post("/api/agent/batch", json={
                "agentId": "agent-dur-01", "machine": "gcp-trading-01",
                "items": [{"id": "dl-1", "kind": "no-such-kind",
                           "machine": "gcp-trading-01", "strategy": "S5-10",
                           "data": {"note": "unroutable"}}],
            }, headers=HEADERS).json()
        rows = dead_letter_repo.list()
        print(json.dumps({
            "rejected": body["rejected"],
            "dead_letters": len(rows),
            "envelope_id": rows[0]["envelopeId"] if rows else None,
            "kind": rows[0]["kind"] if rows else None,
            "reason": rows[0]["reason"] if rows else None,
        }))
        """,
        database,
    )
    assert result["rejected"] == 1
    assert result["dead_letters"] == 1
    assert result["envelope_id"] == "dl-1"
    assert result["kind"] == "no-such-kind"
    assert "unknown envelope kind" in result["reason"]


def test_dead_letters_survive_restart(database: str) -> None:
    _run_backend(
        """
        with TestClient(app) as c:
            c.post("/api/agent/batch", json={
                "agentId": "agent-dur-01", "machine": "gcp-trading-01",
                "items": [{"id": "dl-restart", "kind": "bogus",
                           "machine": "gcp-trading-01", "data": {}}],
            }, headers=HEADERS)
        print(json.dumps({"ok": True}))
        """,
        database,
    )
    after = _run_backend(
        """
        from app.repositories import dead_letter_repo
        rows = dead_letter_repo.list()
        print(json.dumps({"count": len(rows), "id": rows[0]["envelopeId"] if rows else None}))
        """,
        database,
    )
    assert after["count"] == 1
    assert after["id"] == "dl-restart"


def test_batch_size_ceiling_is_enforced(database: str) -> None:
    result = _run_backend(
        """
        items = [{"id": f"big-{i}", "kind": "event", "machine": "gcp-trading-01",
                  "data": {"message": "x"}} for i in range(1001)]
        with TestClient(app) as c:
            r = c.post("/api/agent/batch",
                       json={"agentId": "agent-dur-01", "machine": "gcp-trading-01",
                             "items": items}, headers=HEADERS)
        print(json.dumps({"status": r.status_code}))
        """,
        database,
    )
    assert result["status"] == 413


# --------------------------------------------------------------------------- #
# Sequence tracking
# --------------------------------------------------------------------------- #
def test_normal_sequence_records_progress(database: str) -> None:
    result = _run_backend(
        """
        from app.repositories import sync_state_repo
        items = [{"id": f"seq-{i}", "kind": "event", "machine": "gcp-trading-01",
                  "sequence_id": i, "strategy": "S5-10",
                  "data": {"category": "strategy", "severity": "info", "message": str(i)}}
                 for i in range(1, 6)]
        with TestClient(app) as c:
            body = c.post("/api/agent/batch",
                          json={"agentId": "agent-dur-01", "machine": "gcp-trading-01",
                                "items": items, "queueDepth": 12}, headers=HEADERS).json()
        state = sync_state_repo.get("mch-agent-gcp-trading-01", "agent-dur-01")
        print(json.dumps({
            "ack_last": body["lastSequenceId"], "ack_gap": body["sequenceGap"],
            "last": state["lastSequenceId"], "gaps": state["gapCount"],
            "queue_depth": state["queueDepth"], "accepted": state["acceptedCount"],
        }))
        """,
        database,
    )
    assert result["ack_last"] == 5
    assert result["ack_gap"] is False
    assert result["last"] == 5
    assert result["gaps"] == 0
    assert result["queue_depth"] == 12
    assert result["accepted"] == 5


def test_sequence_gap_is_recorded_without_rejecting_data(database: str) -> None:
    """The core reliability requirement: a gap is observable, never fatal.

    Envelopes 6..9 never arrive. The valid envelope 10 must still be stored —
    refusing it because earlier data is missing would turn a small loss into a
    large one.
    """
    result = _run_backend(
        """
        from app.repositories import events_repo, sync_state_repo
        def item(i):
            return {"id": f"gap-{i}", "kind": "event", "machine": "gcp-trading-01",
                    "sequence_id": i, "strategy": "S5-10",
                    "data": {"category": "strategy", "severity": "info", "message": str(i)}}
        with TestClient(app) as c:
            c.post("/api/agent/batch",
                   json={"agentId": "agent-dur-01", "machine": "gcp-trading-01",
                         "items": [item(5)]}, headers=HEADERS)
            body = c.post("/api/agent/batch",
                          json={"agentId": "agent-dur-01", "machine": "gcp-trading-01",
                                "items": [item(10)]}, headers=HEADERS).json()
        state = sync_state_repo.get("mch-agent-gcp-trading-01", "agent-dur-01")
        print(json.dumps({
            "status_ok": body["accepted"], "processed": body["processed"],
            "ack_gap": body["sequenceGap"],
            "gaps": state["gapCount"], "missing": state["missingCount"],
            "from": state["lastGapFrom"], "to": state["lastGapTo"],
            "last": state["lastSequenceId"], "events": len(events_repo.list()),
        }))
        """,
        database,
    )
    assert result["status_ok"] is True
    assert result["processed"] == 1, "valid data must be accepted despite the gap"
    assert result["ack_gap"] is True
    assert result["gaps"] == 1
    assert result["missing"] == 4       # 6, 7, 8, 9
    assert result["from"] == 6
    assert result["to"] == 9
    assert result["last"] == 10
    assert result["events"] == 2


def test_replayed_older_sequence_does_not_rewind_progress(database: str) -> None:
    result = _run_backend(
        """
        from app.repositories import sync_state_repo
        def item(i, suffix=""):
            return {"id": f"old-{i}{suffix}", "kind": "event", "machine": "gcp-trading-01",
                    "sequence_id": i, "strategy": "S5-10",
                    "data": {"category": "strategy", "severity": "info", "message": str(i)}}
        with TestClient(app) as c:
            c.post("/api/agent/batch",
                   json={"agentId": "agent-dur-01", "machine": "gcp-trading-01",
                         "items": [item(1), item(2), item(3)]}, headers=HEADERS)
            c.post("/api/agent/batch",
                   json={"agentId": "agent-dur-01", "machine": "gcp-trading-01",
                         "items": [item(2, "-replay")]}, headers=HEADERS)
        state = sync_state_repo.get("mch-agent-gcp-trading-01", "agent-dur-01")
        print(json.dumps({"last": state["lastSequenceId"], "gaps": state["gapCount"]}))
        """,
        database,
    )
    assert result["last"] == 3, "an older replay must not rewind the high-water mark"
    assert result["gaps"] == 0, "a replay is not a gap"


def test_sync_state_survives_restart(database: str) -> None:
    _run_backend(
        """
        with TestClient(app) as c:
            c.post("/api/agent/batch", json={
                "agentId": "agent-dur-01", "machine": "gcp-trading-01",
                "items": [{"id": "sync-1", "kind": "event", "sequence_id": 42,
                           "machine": "gcp-trading-01", "data": {"message": "x"}}],
            }, headers=HEADERS)
        print(json.dumps({"ok": True}))
        """,
        database,
    )
    after = _run_backend(
        """
        from app.repositories import sync_state_repo
        state = sync_state_repo.get("mch-agent-gcp-trading-01", "agent-dur-01")
        print(json.dumps({"last": state["lastSequenceId"] if state else None}))
        """,
        database,
    )
    assert after["last"] == 42


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #
def test_session_is_recorded_when_the_agent_reports_one(database: str) -> None:
    result = _run_backend(
        """
        from app.repositories import sessions_repo
        with TestClient(app) as c:
            c.post("/api/agent/batch", json={
                "agentId": "agent-dur-01", "machine": "gcp-trading-01",
                "items": [
                    {"id": "s-1", "kind": "event", "machine": "gcp-trading-01",
                     "session_id": "2026-08-09-NSE", "ts": "2026-08-09T09:15:00+00:00",
                     "data": {"category": "strategy", "severity": "info", "message": "open"}},
                    {"id": "s-2", "kind": "trade", "machine": "gcp-trading-01",
                     "session_id": "2026-08-09-NSE", "ts": "2026-08-09T10:00:00+00:00",
                     "data": {"symbol": "NIFTY", "direction": "long", "action": "close",
                              "entry": 1.0, "exit": 2.0, "quantity": 1, "pnl": 1.0}},
                ],
            }, headers=HEADERS)
        latest = sessions_repo.latest("mch-agent-gcp-trading-01")
        print(json.dumps({
            "session": latest["sessionId"], "status": latest["status"],
            "events": latest["eventCount"], "trades": latest["tradeCount"],
        }))
        """,
        database,
    )
    assert result["session"] == "2026-08-09-NSE"
    assert result["status"] == "open"
    assert result["events"] == 2
    assert result["trades"] == 1


def test_no_session_rows_are_invented_for_current_agents(database: str) -> None:
    """The shipped agent sends no session_id — nothing must be fabricated."""
    result = _run_backend(
        """
        from app.repositories import sessions_repo
        with TestClient(app) as c:
            c.post("/api/agent/batch", json={
                "agentId": "agent-dur-01", "machine": "gcp-trading-01",
                "items": [{"id": "nosess-1", "kind": "event", "machine": "gcp-trading-01",
                           "data": {"category": "strategy", "severity": "info", "message": "x"}}],
            }, headers=HEADERS)
        print(json.dumps({"sessions": len(sessions_repo.list())}))
        """,
        database,
    )
    assert result["sessions"] == 0


# --------------------------------------------------------------------------- #
# Dedup retention
# --------------------------------------------------------------------------- #
def test_dedup_prune_removes_only_expired_rows(database: str) -> None:
    result = _run_backend(
        """
        from datetime import timedelta
        from sqlalchemy import select
        from app.database.session import get_sessionmaker
        from app.models import IngestDedup, utcnow
        from app.repositories import prune_dedup

        session = get_sessionmaker()()
        session.add(IngestDedup(envelope_id="old", kind="event",
                                processed_at=utcnow() - timedelta(days=30)))
        session.add(IngestDedup(envelope_id="new", kind="event", processed_at=utcnow()))
        session.commit()
        session.close()

        removed = prune_dedup(7)
        s2 = get_sessionmaker()()
        remaining = sorted(r[0] for r in s2.execute(select(IngestDedup.envelope_id)))
        s2.close()
        print(json.dumps({"removed": removed, "remaining": remaining}))
        """,
        database,
    )
    assert result["removed"] == 1
    assert result["remaining"] == ["new"]


def test_prune_dedup_command_runs(database: str) -> None:
    """The scheduled maintenance command works end to end (k8s CronJob entry)."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.prune_dedup", "--days", "7"],
        cwd=BACKEND_DIR, env=_environment(database), check=True,
        capture_output=True, text=True, timeout=120,
    )
    assert "pruned" in (result.stdout + result.stderr).lower()


def test_prune_dedup_command_dry_run_deletes_nothing(database: str) -> None:
    seeded = _run_backend("""
        from datetime import timedelta
        from app.database.session import get_sessionmaker
        from app.models import IngestDedup, utcnow
        s = get_sessionmaker()()
        s.add(IngestDedup(envelope_id="old-dry", kind="event",
                          processed_at=utcnow() - timedelta(days=30)))
        s.commit(); s.close()
        print(json.dumps({"ok": True}))
        """, database)
    assert seeded["ok"] is True

    subprocess.run(
        [sys.executable, "-m", "scripts.prune_dedup", "--days", "7", "--dry-run"],
        cwd=BACKEND_DIR, env=_environment(database), check=True,
        capture_output=True, text=True, timeout=120,
    )
    after = _run_backend("""
        from sqlalchemy import select
        from app.database.session import get_sessionmaker
        from app.models import IngestDedup
        s = get_sessionmaker()()
        rows = [r[0] for r in s.execute(select(IngestDedup.envelope_id))]
        s.close()
        print(json.dumps({"rows": sorted(rows)}))
        """, database)
    assert "old-dry" in after["rows"], "--dry-run must not delete anything"


def test_prune_dedup_command_refuses_without_database() -> None:
    """Fail loudly rather than silently succeeding against no database."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.prune_dedup"],
        cwd=BACKEND_DIR, env=_environment(None), check=False,
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 1
    assert "DATABASE_URL" in result.stdout + result.stderr
