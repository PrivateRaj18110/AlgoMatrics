"""Phase 3 ops retention coverage."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _environment(database_url: str | None, **overrides: str) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(BACKEND_DIR), env.get("PYTHONPATH", "")) if part
    )
    env["RAJ_AGENT_TOKEN"] = "retention-agent-token"  # noqa: S105
    env["RAJ_DASHBOARD_TOKEN"] = "retention-dashboard-token"  # noqa: S105
    env.pop("RAJ_AGENT_TOKENS", None)
    env.pop("ENVIRONMENT", None)
    if database_url is None:
        env.pop("DATABASE_URL", None)
    else:
        env["DATABASE_URL"] = database_url
    env.update(overrides)
    return env


def _run_backend(
    code: str,
    database_url: str | None,
    **env_overrides: str,
) -> dict:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=BACKEND_DIR,
        env=_environment(database_url, **env_overrides),
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


def _count_table(database_url: str, model_name: str) -> int:
    return _run_backend(
        """
        import json
        import os
        from sqlalchemy import func, select
        from app.database.session import get_sessionmaker
        from app.models import (
            DeadLetter,
            EodDataset,
            Event,
            Log,
            Metric,
            QuantReport,
            Trade,
            TradingSession,
        )

        models = {
            "DeadLetter": DeadLetter,
            "EodDataset": EodDataset,
            "Event": Event,
            "Log": Log,
            "Metric": Metric,
            "QuantReport": QuantReport,
            "Trade": Trade,
            "TradingSession": TradingSession,
        }
        model = models[os.environ["COUNT_MODEL"]]
        s = get_sessionmaker()()
        count = s.execute(select(func.count()).select_from(model)).scalar_one()
        s.close()
        print(json.dumps({"count": int(count)}))
        """,
        database_url,
        COUNT_MODEL=model_name,
    )["count"]


def _seed_tables(database_url: str) -> None:
    _run_backend(
        """
        import json
        from datetime import timedelta

        from app.database.session import get_sessionmaker
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

        old = utcnow() - timedelta(days=30)
        new = utcnow()
        s = get_sessionmaker()()
        s.add(Event(id="old-event", envelope_id="old-event-env", time=old, category="system",
                    severity="info", source="retention", message="old"))
        s.add(Event(id="new-event", envelope_id="new-event-env", time=new, category="system",
                    severity="info", source="retention", message="new"))
        s.add(Log(id="old-log", envelope_id="old-log-env", time=old, source="agent",
                  level="info", logger="retention", message="old"))
        s.add(Log(id="new-log", envelope_id="new-log-env", time=new, source="agent",
                  level="info", logger="retention", message="new"))
        s.add(Metric(envelope_id="old-metric-env", time=old, machine="gcp",
                     machine_id="machine-gcp", name="cpu", value=1.0))
        s.add(Metric(envelope_id="new-metric-env", time=new, machine="gcp",
                     machine_id="machine-gcp", name="cpu", value=2.0))
        s.add(Trade(id="old-trade", envelope_id="old-trade-env", time=old, strategy="s",
                    machine="gcp", machine_id="machine-gcp", broker="paper",
                    account="paper", symbol="NIFTY", direction="buy"))
        s.add(Trade(id="new-trade", envelope_id="new-trade-env", time=new, strategy="s",
                    machine="gcp", machine_id="machine-gcp", broker="paper",
                    account="paper", symbol="NIFTY", direction="buy"))
        s.add(DeadLetter(envelope_id="old-dead", kind="bad", reason="old", received_at=old))
        s.add(DeadLetter(envelope_id="new-dead", kind="bad", reason="new", received_at=new))
        s.add(TradingSession(session_id="old-closed", machine_id="machine-gcp",
                             machine="gcp", status="completed", ended_at=old,
                             last_event_at=old, created_at=old, updated_at=old))
        s.add(TradingSession(session_id="old-open", machine_id="machine-gcp",
                             machine="gcp", status="open", last_event_at=old,
                             created_at=old, updated_at=old))
        s.add(QuantReport(report_id="old-report", dataset_id="old-eod",
                          machine_id="machine-gcp", trading_date="2026-08-01",
                          status="READY", coverage_json="{}", trade_metrics_json="{}",
                          market_replay_json="{}", warnings_json="[]",
                          created_at=old, updated_at=old))
        s.add(QuantReport(report_id="new-report", dataset_id="new-eod",
                          machine_id="machine-gcp", trading_date="2026-08-10",
                          status="READY", coverage_json="{}", trade_metrics_json="{}",
                          market_replay_json="{}", warnings_json="[]",
                          created_at=new, updated_at=new))
        s.add(EodDataset(dataset_id="old-eod", machine_id="machine-gcp", machine="gcp",
                         agent_id="agent", trading_date="2026-08-01",
                         schema_version="1", status="COMPLETE", finalized_at=old,
                         received_at=old, updated_at=old, total_files=1, total_bytes=3))
        s.add(EodDatasetFile(dataset_id="old-eod", file_id="ticks",
                             relative_path="ticks.jsonl", dataset_type="ticks",
                             size_bytes=3, sha256="0" * 64, status="COMPLETE"))
        s.commit()
        s.close()
        print(json.dumps({"seeded": True}))
        """,
        database_url,
    )


def test_retention_policies_are_disabled_by_default(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'disabled.db').as_posix()}"
    _migrate(database_url)
    _seed_tables(database_url)

    result = _run_backend(
        """
        import json
        from app.services.retention_service import run_retention
        print(json.dumps(run_retention(dry_run=False)))
        """,
        database_url,
    )

    assert result["deleted"] == 0
    assert _count_table(database_url, "Event") == 2
    assert _count_table(database_url, "EodDataset") == 1


def test_retention_prunes_configured_tables_without_touching_open_sessions(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{(tmp_path / 'retention.db').as_posix()}"
    _migrate(database_url)
    _seed_tables(database_url)

    result = _run_backend(
        """
        import json
        from sqlalchemy import select
        from sqlalchemy import func
        from app.database.session import get_sessionmaker
        from app.models import (
            DeadLetter, EodDataset, Event, Log, Metric, QuantReport, Trade, TradingSession
        )
        from app.services.retention_service import run_retention

        summary = run_retention(dry_run=False)
        s = get_sessionmaker()()
        remaining = {
            "events": sorted(row[0] for row in s.execute(select(Event.id))),
            "logs": sorted(row[0] for row in s.execute(select(Log.id))),
            "metrics": int(s.execute(select(func.count()).select_from(Metric)).scalar_one()),
            "trades": sorted(row[0] for row in s.execute(select(Trade.id))),
            "dead": int(s.execute(select(func.count()).select_from(DeadLetter)).scalar_one()),
            "sessions": sorted(row[0] for row in s.execute(select(TradingSession.session_id))),
            "eod": int(s.execute(select(func.count()).select_from(EodDataset)).scalar_one()),
            "reports": sorted(row[0] for row in s.execute(select(QuantReport.report_id))),
        }
        s.close()
        print(json.dumps({"summary": summary, "remaining": remaining}))
        """,
        database_url,
        TELEMETRY_RETENTION_DAYS="7",
        OPERATIONAL_EVENT_RETENTION_DAYS="7",
        DEAD_LETTER_RETENTION_DAYS="7",
        SESSION_RETENTION_DAYS="7",
        EOD_METADATA_RETENTION_DAYS="7",
        QUANT_REPORT_RETENTION_DAYS="7",
    )

    remaining = result["remaining"]
    assert remaining["events"] == ["new-event"]
    assert remaining["logs"] == ["new-log"]
    assert remaining["metrics"] == 1
    assert remaining["trades"] == ["new-trade"]
    assert remaining["dead"] == 1
    assert remaining["sessions"] == ["old-open"]
    assert remaining["eod"] == 0
    assert remaining["reports"] == ["new-report"]
    assert result["summary"]["deleted"] >= 8


def test_raw_eod_retention_deletes_bytes_but_keeps_metadata(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'raw.db').as_posix()}"
    storage_root = tmp_path / "eod"
    _migrate(database_url)

    result = _run_backend(
        """
        import json
        from datetime import timedelta
        from sqlalchemy import select
        from app.database.session import get_sessionmaker
        from app.models import EodDataset, EodDatasetFile, utcnow
        from app.services.retention_service import run_retention
        from app.storage.dataset import LocalDatasetStorage

        old = utcnow() - timedelta(days=30)
        storage = LocalDatasetStorage(__import__("os").environ["EOD_STORAGE_ROOT"])
        storage.write_chunk("raw-old", "ticks", 0, b"abc")

        s = get_sessionmaker()()
        s.add(EodDataset(dataset_id="raw-old", machine_id="machine-gcp", machine="gcp",
                         agent_id="agent", trading_date="2026-08-01",
                         schema_version="1", status="COMPLETE", finalized_at=old,
                         received_at=old, updated_at=old, total_files=1, total_bytes=3))
        s.add(EodDatasetFile(dataset_id="raw-old", file_id="ticks",
                             relative_path="ticks.jsonl", dataset_type="ticks",
                             size_bytes=3, sha256="ba7816bf8f01cfea414140de5dae2223"
                             "b00361a396177a9cb410ff61f20015ad",
                             status="COMPLETE", storage_key="raw-old/ticks.part"))
        s.commit()

        s.close()
        summary = run_retention(dry_run=False)
        s2 = get_sessionmaker()()
        row = s2.get(EodDataset, "raw-old")
        exists = storage.exists("raw-old", "ticks")
        s2.close()
        print(json.dumps({
            "summary": summary,
            "exists": exists,
            "rawDeletedAt": row.raw_deleted_at.isoformat() if row.raw_deleted_at else None,
        }))
        """,
        database_url,
        EOD_STORAGE_ROOT=str(storage_root),
        EOD_RAW_RETENTION_DAYS="7",
    )

    assert result["exists"] is False
    assert result["rawDeletedAt"]
    raw_policy = next(p for p in result["summary"]["policies"] if p["policy"] == "eod.raw")
    assert raw_policy["matched"] == 1
    assert raw_policy["deleted"] == 1
    assert _count_table(database_url, "EodDataset") == 1


def test_retention_command_dry_run_outputs_json_and_deletes_nothing(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'cli.db').as_posix()}"
    _migrate(database_url)
    _seed_tables(database_url)

    result = subprocess.run(
        [sys.executable, "-m", "scripts.prune_retention", "--dry-run", "--json"],
        cwd=BACKEND_DIR,
        env=_environment(database_url, OPERATIONAL_EVENT_RETENTION_DAYS="7"),
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    summary = json.loads(result.stdout.strip().splitlines()[-1])
    assert summary["dryRun"] is True
    assert summary["matched"] >= 1
    assert _count_table(database_url, "Event") == 2


def test_retention_command_refuses_without_database() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.prune_retention"],
        cwd=BACKEND_DIR,
        env=_environment(None),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 1
    assert "DATABASE_URL" in result.stdout + result.stderr
