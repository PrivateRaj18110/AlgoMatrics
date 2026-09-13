"""Deterministic synthetic load generator for the monitoring.v1 receiver.

**This produces synthetic traffic for measuring a receiver. It is not LLS data
and must never be presented as such.** Every message it emits carries the
producer's own non-live environment value and a `synthetic-load/` source
instance, so anything it writes is identifiable as generated traffic in the
database, in a projection, and on screen.

Why it exists: monitoring.v1 messages are content-addressed and must arrive in
sequence per publisher instance, so a load test cannot simply resend one
fixture — that is a duplicate, which exercises a different path and measures the
wrong thing. Each message here is genuinely distinct and correctly ordered, so
the receiver does the full accept-and-project work under load.

Kept deliberately apart from `tests/fixtures/lls-monitoring-v1-handoff/`. Those
fixtures are the producer's, and correctness is judged against them; these are
ours, and only throughput is judged against these. Mixing the two would let a
generated message be mistaken for a contract fixture.

Usage:

    python tools/monitoring_loadgen.py --endpoint https://host/api/monitoring/v1/messages \\
        --token "$TOKEN" --ca staging-ca.crt --messages 500 --concurrency 8
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import contextlib
import hashlib
import http.client
import json
import ssl
import statistics
import sys
import time
import urllib.parse
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO = BACKEND_DIR.parents[1]
MESSAGES = REPO / "tests" / "fixtures" / "lls-monitoring-v1-handoff" / "fixtures" / "messages"
TEMPLATE = MESSAGES / "valid_snapshot.json"

#: Templates by message type, so storage and latency can be measured per type
#: rather than assumed uniform. The producer's own fixtures span roughly
#: 1.2 kB to 98 kB, and a capacity model built on one size would be wrong for
#: the others.
TEMPLATES = {
    "snapshot": MESSAGES / "valid_snapshot.json",
    "events": MESSAGES / "valid_events.json",
    "incidents": MESSAGES / "valid_incidents.json",
    "forensic_reference": MESSAGES / "valid_forensic_reference.json",
}

#: Marks generated traffic unmistakably wherever it lands.
SYNTHETIC_INSTANCE_PREFIX = "synthetic-load"


def canonical_json(value: Any) -> bytes:
    """Must match the receiver's canonical form exactly, or identities differ."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def message_identity(document: dict[str, Any]) -> str:
    without_id = {key: value for key, value in document.items() if key != "message_id"}
    return "mon1/" + hashlib.sha256(canonical_json(without_id)).hexdigest()


def build(template: dict[str, Any], run_id: str, worker: int, sequence: int,
          capture_ref_mode: str = "per-message") -> bytes:
    """One valid, distinct, correctly ordered synthetic message."""
    document = json.loads(json.dumps(template))  # deep copy

    # Dots, not slashes: the contract constrains source_instance to
    # ^[A-Za-z0-9_.-]{1,80}$, and a generator that ignored that would be
    # measuring the rejection path instead of the acceptance path.
    document["source_instance"] = f"{SYNTHETIC_INSTANCE_PREFIX}.{run_id}.{worker}"
    document["source_sequence"] = str(sequence)
    # Deterministic, monotonic, and clearly not a market clock.
    generated = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=sequence)
    document["generated_at"] = generated.isoformat().replace("+00:00", "+00:00")

    # The producer's own non-live value. Never "live_trading", never anything
    # that could be read as real market activity.
    document["environment"] = "offline_fixture"

    # capture_ref is part of the projection key
    # (receiver_deployment_environment, source_id, message_type, capture_ref),
    # so this single field decides whether `monitoring_projections` stays
    # bounded or grows one row per message. The contract does not say which
    # production does — it says only that page offsets are "tied to an immutable
    # capture" — so the generator can produce either, and a measurement must say
    # which one it used.
    #
    #   per-message  a new capture per message. Projections grow 1:1 with
    #                evidence. The pessimistic case.
    #   stable       one capture reused, as every producer fixture does.
    #                Projections stay bounded. The optimistic case.
    #
    # Message identity does not depend on this: distinctness is guaranteed by
    # source_instance, source_sequence and generated_at regardless, so a stable
    # capture_ref still produces a unique content address per message.
    #
    # Only where the message type already carries a capture_ref:
    # `monitoring.forensic_reference` payloads do not, and the contract's schema
    # rejects the extra field.
    payload = document.get("payload")
    if isinstance(payload, dict) and "capture_ref" in payload:
        if capture_ref_mode == "stable":
            payload["capture_ref"] = f"{SYNTHETIC_INSTANCE_PREFIX}.capture"
        else:
            payload["capture_ref"] = f"{SYNTHETIC_INSTANCE_PREFIX}.{run_id}.{worker}.{sequence}"

    document["message_id"] = message_identity(document)
    return canonical_json(document)


def open_connection(url: str, ctx: ssl.SSLContext) -> tuple[Any, str]:
    """One keep-alive connection, reused for a worker's whole sequence.

    A real publisher holds a connection open. Opening a fresh TLS connection per
    message would put a full handshake — measured at roughly 2 seconds against
    this staging deployment — inside every sample, and the result would describe
    the handshake rather than the receiver.
    """
    parsed = urllib.parse.urlsplit(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if parsed.scheme == "https":
        connection = http.client.HTTPSConnection(parsed.hostname, port, context=ctx, timeout=120)
    else:
        connection = http.client.HTTPConnection(parsed.hostname, port, timeout=120)
    return connection, parsed.path


def send(
    connection: Any, path: str, token: str, body: bytes, reconnect: Any = None
) -> tuple[object, float, Any]:
    """Deliver one message, reconnecting once if the connection has gone.

    A keep-alive connection can be closed by the server between messages —
    idle timeout, worker recycling, an intervening restart. Without a retry the
    whole of that publisher's remaining run fails, which is how a 15-minute run
    lost 200 of 28,800 messages to what looked like receiver errors and was
    really the generator giving up on a dead socket.

    Exactly one reconnect per message, so a genuinely unreachable receiver still
    reports a transport failure rather than spinning.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-Monitoring-SHA256": hashlib.sha256(body).hexdigest(),
    }
    started = time.perf_counter()
    for attempt in (1, 2):
        try:
            connection.request("POST", path, body=body, headers=headers)
            response = connection.getresponse()
            response.read()
            return response.status, time.perf_counter() - started, connection
        except Exception as exc:
            if attempt == 2 or reconnect is None:
                return f"TRANSPORT:{type(exc).__name__}", time.perf_counter() - started, connection
            # The socket is already broken; closing it is best-effort tidying.
            with contextlib.suppress(Exception):
                connection.close()
            connection = reconnect()
    raise AssertionError("unreachable")


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--ca", default=None, help="CA file validating the receiver certificate")
    parser.add_argument("--messages", type=int, default=200, help="messages per worker")
    parser.add_argument("--concurrency", type=int, default=1, help="concurrent publishers")
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--template",
        default="snapshot",
        choices=sorted(TEMPLATES),
        help="which message type to generate; sizes differ by roughly 80x",
    )
    parser.add_argument(
        "--capture-ref-mode",
        default="per-message",
        choices=("per-message", "stable"),
        help="whether each message gets its own capture_ref (projections grow 1:1 with "
             "evidence) or reuses one (projections stay bounded). Decides which of the two "
             "readings of the contract is being measured",
    )
    parser.add_argument("--json", action="store_true", help="emit the summary as JSON")
    args = parser.parse_args()

    template = json.loads(TEMPLATES[args.template].read_text(encoding="utf-8"))
    ctx = ssl.create_default_context(cafile=args.ca) if args.ca else ssl.create_default_context()
    run_id = args.run_id or f"r{int(time.time())}"

    latencies: list[float] = []
    statuses: dict[str, int] = {}

    def worker(index: int) -> tuple[list[float], dict[str, int]]:
        """One publisher instance, delivering its own sequence in order."""
        local_latencies: list[float] = []
        local_statuses: dict[str, int] = {}

        def make_connection():
            conn, _ = open_connection(args.endpoint, ctx)
            return conn

        connection, path = open_connection(args.endpoint, ctx)
        try:
            # Warm the connection outside the measurement. The TLS handshake
            # costs roughly 2 seconds here; leaving it inside the first sample
            # would put it in the mean and own the p99 outright, describing the
            # handshake rather than ingest.
            warmup_path = path.rsplit("/messages", 1)[0] + "/health"
            try:
                connection.request("GET", warmup_path)
                connection.getresponse().read()
            except Exception:  # noqa: S110 - a failed warm-up is not a measurement
                pass

            for sequence in range(1, args.messages + 1):
                body = build(template, run_id, index, sequence, args.capture_ref_mode)
                status, elapsed, connection = send(
                    connection, path, args.token, body, reconnect=make_connection
                )
                local_latencies.append(elapsed)
                local_statuses[str(status)] = local_statuses.get(str(status), 0) + 1
        finally:
            connection.close()
        return local_latencies, local_statuses

    wall_start = time.perf_counter()
    with futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for task in [pool.submit(worker, index) for index in range(args.concurrency)]:
            worker_latencies, worker_statuses = task.result()
            latencies.extend(worker_latencies)
            for key, count in worker_statuses.items():
                statuses[key] = statuses.get(key, 0) + count
    wall = time.perf_counter() - wall_start

    total = len(latencies)
    summary = {
        "run_id": run_id,
        "capture_ref_mode": args.capture_ref_mode,
        "template": args.template,
        "concurrency": args.concurrency,
        "messages_per_worker": args.messages,
        "messages_total": total,
        "wall_seconds": round(wall, 3),
        "messages_per_second": round(total / wall, 1) if wall else None,
        "latency_ms": {
            "mean": round(statistics.fmean(latencies) * 1000, 2) if latencies else None,
            "p50": round(percentile(latencies, 0.50) * 1000, 2),
            "p95": round(percentile(latencies, 0.95) * 1000, 2),
            "p99": round(percentile(latencies, 0.99) * 1000, 2),
            "max": round(max(latencies) * 1000, 2) if latencies else None,
        },
        "statuses": statuses,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(json.dumps(summary, indent=2))
    # Any non-200 makes the run untrustworthy as a throughput measurement.
    return 0 if set(statuses) == {"200"} else 1


if __name__ == "__main__":
    sys.exit(main())
