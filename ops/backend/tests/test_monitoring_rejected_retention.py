"""Retention for monitoring.v1 rejected traffic — owner decision 2, 2026-09-13.

The decision is narrow: quarantine rows and stored raw rejected request bodies
are kept for 30 days. Accepted evidence is retained **indefinitely** (decision 1)
and the audit trail is the record of every attempt rather than rejected traffic.

So these tests are as much about what must NOT be deleted as what must. The
dangerous failure here is not "retention did not run" — it is "retention ran and
took something it was never authorised to take", which for an append-only
forensic record cannot be undone.

Follows the subprocess pattern of ``test_ops_retention.py``: each call is a fresh
interpreter against a real migrated database, because the repositories bind at
import time from ``DATABASE_URL``.
"""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _environment(database_url: str, **overrides: str) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(BACKEND_DIR), env.get("PYTHONPATH", "")) if part
    )
    env["RAJ_AGENT_TOKEN"] = "rejected-retention-agent"  # noqa: S105
    env["RAJ_DASHBOARD_TOKEN"] = "rejected-retention-dashboard"  # noqa: S105
    env.pop("RAJ_AGENT_TOKENS", None)
    env.pop("ENVIRONMENT", None)
    env["DATABASE_URL"] = database_url
    env.update(overrides)
    return env


def _run_backend(code: str, database_url: str, **overrides: str) -> dict:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=BACKEND_DIR,
        env=_environment(database_url, **overrides),
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
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
        timeout=180,
    )


#: Seeds one row either side of the 30-day boundary in each rejected-traffic
#: table, plus evidence and audit rows far older than any window — those two
#: exist purely so their survival can be asserted.
_SEED = """
    import json
    import uuid
    from datetime import timedelta

    from app.database.session import get_sessionmaker
    from app.models import (
        MonitoringAudit,
        MonitoringEvidence,
        MonitoringQuarantine,
        MonitoringRawRequest,
        utcnow,
    )

    now = utcnow()
    old, recent = now - timedelta(days=45), now - timedelta(days=5)
    ancient = now - timedelta(days=3650)

    s = get_sessionmaker()()
    for index, (when, tag) in enumerate(((old, "old"), (recent, "recent"))):
        s.add(MonitoringQuarantine(
            quarantine_id="q-" + tag, request_id="r-" + tag, source_id="lls",
            reason="schema_invalid", received_at=when,
        ))
        s.add(MonitoringRawRequest(
            request_id="r-" + tag, source_id="lls", received_at=when,
            byte_length=10, body_sha256=str(index).zfill(64), body=b"rejected",
        ))
    s.add(MonitoringEvidence(
        message_id="mon1/keep", organisation_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        source_id="lls", source_instance="i-1",
        source_sequence="1", sequence_ordinal=1,
        message_type="monitoring.snapshot", schema_version="monitoring.v1",
        source_environment="offline_fixture",
        receiver_deployment_environment="staging",
        generated_at=ancient, received_at=ancient,
        source_as_of_json="{}", coverage_json="{}", freshness_json="{}",
        trust_json="{}", runtime_json="{}",
        request_sha256="1".zfill(64), message_json="{}",
    ))
    s.add(MonitoringAudit(
        at=ancient, action="ingest", outcome="refused",
        source_id="lls", request_id="r-old",
    ))
    s.commit()
    s.close()
    print(json.dumps({"seeded": True}))
"""

_COUNTS = """
    import json
    from sqlalchemy import func, select
    from app.database.session import get_sessionmaker
    from app.models import (
        MonitoringAudit,
        MonitoringEvidence,
        MonitoringQuarantine,
        MonitoringRawRequest,
    )

    s = get_sessionmaker()()
    counts = {
        name: int(s.execute(select(func.count()).select_from(model)).scalar_one())
        for name, model in (
            ("quarantine", MonitoringQuarantine),
            ("raw_requests", MonitoringRawRequest),
            ("evidence", MonitoringEvidence),
            ("audit", MonitoringAudit),
        )
    }
    s.close()
    print(json.dumps(counts))
"""


def test_disabled_by_default_so_no_environment_deletes_by_accident() -> None:
    """The code default is 0. A deployment must opt in explicitly.

    The 30-day figure lives in deployment configuration, not in this default, so
    a fresh install, a developer machine or a test run never destroys forensic
    material it was not told to.
    """
    from app.core.config import Settings

    assert Settings().monitoring_rejected_retention_days == 0


def test_policy_targets_exactly_the_two_rejected_traffic_tables() -> None:
    """Scope asserted structurally, not merely observed.

    A future edit that added evidence or audit to this policy would still pass a
    test that only counted rows in a fixture. This one fails.
    """
    from app.services import retention_service

    body = inspect.getsource(retention_service._monitoring_rejected_retention)
    _, _, code = body.partition('"""')
    _, _, code = code.partition('"""')  # drop the docstring, which names them all

    assert "MonitoringQuarantine" in code
    assert "MonitoringRawRequest" in code
    assert "MonitoringEvidence" not in code, "evidence retention is INDEFINITE"
    assert "MonitoringAudit" not in code, "the audit trail is not rejected traffic"
    assert "MonitoringProjection" not in code
    assert "MonitoringSequenceState" not in code


def test_disabled_policy_reports_and_deletes_nothing(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'off.db').as_posix()}"
    _migrate(database_url)
    _run_backend(_SEED, database_url)

    result = _run_backend(
        """
        import json
        from app.services.retention_service import run_retention
        print(json.dumps(run_retention(dry_run=False)))
        """,
        database_url,
    )
    policies = {p["policy"]: p for p in result["policies"]}
    assert policies["monitoring.quarantine"]["note"] == "disabled"
    assert policies["monitoring.raw_requests"]["note"] == "disabled"

    counts = _run_backend(_COUNTS, database_url)
    assert counts == {"quarantine": 2, "raw_requests": 2, "evidence": 1, "audit": 1}


def test_dry_run_matches_without_deleting(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'dry.db').as_posix()}"
    _migrate(database_url)
    _run_backend(_SEED, database_url)

    result = _run_backend(
        """
        import json
        from app.services.retention_service import run_retention
        print(json.dumps(run_retention(dry_run=True)))
        """,
        database_url,
        MONITORING_REJECTED_RETENTION_DAYS="30",
    )
    policies = {p["policy"]: p for p in result["policies"]}
    assert policies["monitoring.quarantine"]["matched"] == 1
    assert policies["monitoring.raw_requests"]["matched"] == 1
    assert policies["monitoring.quarantine"]["deleted"] == 0
    assert policies["monitoring.raw_requests"]["deleted"] == 0

    counts = _run_backend(_COUNTS, database_url)
    assert counts == {"quarantine": 2, "raw_requests": 2, "evidence": 1, "audit": 1}


def test_thirty_day_window_prunes_only_rejected_traffic(tmp_path: Path) -> None:
    """The load-bearing test.

    The 45-day-old quarantine row and its raw body go. The 5-day-old pair stays.
    Evidence ten years old and the audit row recording the refusal both survive,
    because decision 1 is indefinite retention and audit is not rejected traffic.
    """
    database_url = f"sqlite:///{(tmp_path / 'prune.db').as_posix()}"
    _migrate(database_url)
    _run_backend(_SEED, database_url)

    result = _run_backend(
        """
        import json
        from app.services.retention_service import run_retention
        print(json.dumps(run_retention(dry_run=False)))
        """,
        database_url,
        MONITORING_REJECTED_RETENTION_DAYS="30",
    )
    policies = {p["policy"]: p for p in result["policies"]}
    assert policies["monitoring.quarantine"]["deleted"] == 1
    assert policies["monitoring.raw_requests"]["deleted"] == 1
    assert policies["monitoring.quarantine"]["retentionDays"] == 30

    counts = _run_backend(_COUNTS, database_url)
    assert counts["quarantine"] == 1, "the recent quarantine row was taken too"
    assert counts["raw_requests"] == 1, "the recent raw body was taken too"
    assert counts["evidence"] == 1, "ACCEPTED EVIDENCE WAS DELETED"
    assert counts["audit"] == 1, "THE AUDIT TRAIL WAS DELETED"


def test_quarantine_and_its_raw_body_age_out_together(tmp_path: Path) -> None:
    """Both tables share one cutoff, so the forensic record never half-survives.

    A quarantine row whose raw body had been pruned would describe bytes nobody
    can produce any more; the reverse leaves bytes nothing explains.
    """
    database_url = f"sqlite:///{(tmp_path / 'pair.db').as_posix()}"
    _migrate(database_url)
    _run_backend(_SEED, database_url)
    _run_backend(
        """
        import json
        from app.services.retention_service import run_retention
        print(json.dumps(run_retention(dry_run=False)))
        """,
        database_url,
        MONITORING_REJECTED_RETENTION_DAYS="30",
    )

    surviving = _run_backend(
        """
        import json
        from sqlalchemy import select
        from app.database.session import get_sessionmaker
        from app.models import MonitoringQuarantine, MonitoringRawRequest

        s = get_sessionmaker()()
        q = [r for (r,) in s.execute(select(MonitoringQuarantine.request_id)).all()]
        raw = [r for (r,) in s.execute(select(MonitoringRawRequest.request_id)).all()]
        s.close()
        print(json.dumps({"quarantine": sorted(q), "raw": sorted(raw)}))
        """,
        database_url,
    )
    assert surviving["quarantine"] == surviving["raw"] == ["r-recent"]
