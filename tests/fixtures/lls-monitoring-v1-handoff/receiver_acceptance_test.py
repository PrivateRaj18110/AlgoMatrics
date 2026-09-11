#!/usr/bin/env python3
"""Standalone monitoring.v1 receiver acceptance runner.

This file intentionally imports only the Python standard library. It sends the
JSON fixture bytes exactly as stored and validates only the HTTP/ACK behavior
that an independent receiver must expose.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def load_json(path: Path):
    return json.loads(path.read_bytes(), object_pairs_hook=unique_object)


def body_message_id(data: bytes) -> str:
    return load_json_bytes(data)["message_id"]


def load_json_bytes(data: bytes):
    return json.loads(data, object_pairs_hook=unique_object)


def send(endpoint: str, token: str, message_path: Path, sha_override: str | None, timeout: float):
    data = message_path.read_bytes()
    try:
        document = load_json_bytes(data)
        message_id = document.get("message_id", "")
    except Exception:
        message_id = ""
    digest = sha_override or hashlib.sha256(data).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + token,
        "Idempotency-Key": message_id,
        "X-Monitoring-SHA256": digest,
    }
    request = Request(endpoint, data=data, method="POST", headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read(4097)
    except HTTPError as exc:
        return exc.code, exc.read(4097)
    except URLError as exc:
        raise RuntimeError(f"network failure: {exc}") from exc


def check_ack(body: bytes, expected_statuses: list[str], message_path: Path, sha_override: str | None) -> None:
    if not expected_statuses:
        return
    data = message_path.read_bytes()
    message = load_json_bytes(data)
    ack = json.loads(body, object_pairs_hook=unique_object)
    expected_digest = sha_override or hashlib.sha256(data).hexdigest()
    expected_fields = {"schema_version", "message_id", "sha256", "source_sequence", "status"}
    if set(ack) != expected_fields:
        raise AssertionError(f"ACK fields mismatch: {sorted(ack)}")
    if ack["schema_version"] != "monitoring.ack.v1":
        raise AssertionError("ACK schema_version mismatch")
    if ack["message_id"] != message["message_id"]:
        raise AssertionError("ACK message_id mismatch")
    if ack["sha256"] != expected_digest:
        raise AssertionError("ACK sha256 mismatch")
    if ack["source_sequence"] != message["source_sequence"]:
        raise AssertionError("ACK source_sequence mismatch")
    if ack["status"] not in expected_statuses:
        raise AssertionError(f"ACK status {ack['status']!r} not in {expected_statuses!r}")


def dry_run(fixtures: Path) -> None:
    manifest = load_json(fixtures / "fixture_manifest.json")
    cases = load_json(fixtures / "cases" / "http_cases.json")
    missing = []
    for item in manifest["messages"]:
        if not (fixtures / item["file"]).is_file():
            missing.append(item["file"])
    for item in manifest["acks"]:
        if not (fixtures / "fixtures" / "acks" / item).is_file():
            missing.append("fixtures/acks/" + item)
    for case in cases["cases"]:
        for step in case["steps"]:
            if not (fixtures / "fixtures" / "messages" / step["message"]).is_file():
                missing.append("fixtures/messages/" + step["message"])
    if missing:
        raise SystemExit("missing fixtures: " + ", ".join(missing))
    print(json.dumps({"status": "dry-run-ok", "messages": len(manifest["messages"]), "cases": len(cases["cases"])}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", default=str(Path(__file__).resolve().parent), help="fixture package directory")
    parser.add_argument("--endpoint", help="receiver HTTPS endpoint ending in /api/monitoring/v1/messages")
    parser.add_argument("--token", help="upload-only token for the target receiver")
    parser.add_argument("--case", action="append", help="case id to run; omit to run all cases in manifest order")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    fixtures = Path(args.fixtures).resolve()
    if args.dry_run:
        dry_run(fixtures)
        return 0
    if not args.endpoint or not args.token:
        parser.error("--endpoint and --token are required unless --dry-run is used")
    if not args.endpoint.endswith("/api/monitoring/v1/messages"):
        parser.error("endpoint must end in /api/monitoring/v1/messages")

    cases = load_json(fixtures / "cases" / "http_cases.json")["cases"]
    selected = set(args.case or [case["id"] for case in cases])
    failures = []
    for case in cases:
        if case["id"] not in selected:
            continue
        for step in case["steps"]:
            repeats = int(step.get("repeat", 1))
            for index in range(repeats):
                token = "invalid-monitoring-fixture-token" if step.get("token") == "invalid" else args.token
                path = fixtures / "fixtures" / "messages" / step["message"]
                status, body = send(args.endpoint, token, path, step.get("sha256_header"), args.timeout)
                if status not in step["expect_http"]:
                    failures.append({"case": case["id"], "message": step["message"], "repeat": index + 1, "http": status, "expected": step["expect_http"]})
                    continue
                if 200 <= status < 300:
                    try:
                        check_ack(body, step.get("expect_ack_status", []), path, step.get("sha256_header"))
                    except Exception as exc:
                        failures.append({"case": case["id"], "message": step["message"], "repeat": index + 1, "ack_error": str(exc)})
    if failures:
        print(json.dumps({"status": "failed", "failures": failures}, indent=2))
        return 1
    print(json.dumps({"status": "passed", "cases": sorted(selected)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
