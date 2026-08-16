"""AWS-side quant analytics and replay over finalized EOD datasets.

This module is deliberately read-only with respect to trading systems. It reads
bytes from the EOD storage port, computes bounded derived analytics, and stores
reports in the ops read model. It never imports broker adapters, strategy
runners, order services or risk-control code.
"""

from __future__ import annotations

import csv
import io
import json
import math
import random
from datetime import UTC, datetime
from itertools import pairwise
from statistics import fmean, pstdev
from typing import Any

from app.core.config import get_settings
from app.repositories import eod_repo, quant_report_repo
from app.schemas.quant import QuantAnalyticsSummary, SyntheticReplayRequest
from app.storage import get_dataset_storage


class QuantNotFoundError(LookupError):
    """Requested dataset/report does not exist."""


class QuantValidationError(ValueError):
    """Dataset cannot be analyzed in its current state."""


TRADE_TYPES = {"trades", "trade", "executions", "execution", "fills", "fill"}
PRICE_TYPES = {"ticks", "tick", "candles", "candle", "prices", "price", "market_data", "market"}
SIGNAL_TYPES = {"signals", "signal"}
RISK_TYPES = {"risk", "risks", "risk_events", "risk_event"}
POSITION_TYPES = {"positions", "position"}
ANALYTICS_VERSION = "phase3-quant-analytics-v1"
ANALYTICS_CATEGORIES = (
    "performance",
    "strategy",
    "execution",
    "signals",
    "risk",
    "sessions",
    "dataQuality",
)


def list_reports(*, limit: int = 100, dataset_id: str | None = None) -> list[dict[str, Any]]:
    reports = quant_report_repo.list(limit=limit, dataset_id=dataset_id)
    return [_normalise_report(report) for report in reports]


def get_report(report_id: str) -> dict[str, Any]:
    report = quant_report_repo.get(report_id)
    if report is None:
        raise QuantNotFoundError("quant report not found")
    return _normalise_report(report)


def get_dataset_report(dataset_id: str) -> dict[str, Any]:
    report = quant_report_repo.latest_for_dataset(dataset_id)
    if report is None:
        raise QuantNotFoundError("quant report not found for dataset")
    return _normalise_report(report)


def analytics_summary(
    category: str,
    *,
    limit: int = 100,
    dataset_id: str | None = None,
) -> dict[str, Any]:
    if category not in ANALYTICS_CATEGORIES:
        raise QuantValidationError(f"unknown analytics category {category!r}")
    reports = list_reports(limit=limit, dataset_id=dataset_id)
    return QuantAnalyticsSummary(
        category=category,
        generatedAt=datetime.now(UTC).isoformat(),
        calculationVersion=ANALYTICS_VERSION,
        reportCount=len(reports),
        datasetId=dataset_id,
        reports=[
            {
                "reportId": report["reportId"],
                "datasetId": report["datasetId"],
                "machineId": report["machineId"],
                "tradingDate": report["tradingDate"],
                "status": report["status"],
                "analytics": report["analytics"][category],
            }
            for report in reports
        ],
    ).model_dump()


def analyze_dataset(dataset_id: str) -> dict[str, Any]:
    dataset = eod_repo.get(dataset_id)
    if dataset is None:
        raise QuantNotFoundError("dataset not found")
    if dataset["status"] != "COMPLETE":
        raise QuantValidationError("dataset must be finalized before quant analysis")

    settings = get_settings()
    storage = get_dataset_storage()
    warnings: list[str] = []
    trade_rows: list[dict[str, Any]] = []
    price_rows: list[dict[str, Any]] = []
    signal_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    other_rows: list[dict[str, Any]] = []
    dataset_types: dict[str, int] = {}
    parsed_files = 0
    parsed_rows = 0
    skipped_files = 0

    for file in dataset.get("files", []):
        dtype = str(file.get("datasetType", "")).strip().lower()
        dataset_types[dtype or "unknown"] = dataset_types.get(dtype or "unknown", 0) + 1
        if file.get("status") not in {"READY", "COMPLETE"}:
            skipped_files += 1
            warnings.append(f"skipped {file['fileId']}: file is {file.get('status')}")
            continue
        try:
            size = storage.size(dataset_id, file["fileId"])
        except OSError as exc:
            skipped_files += 1
            warnings.append(
                f"skipped {file['fileId']}: storage object missing ({type(exc).__name__})"
            )
            continue
        if size > settings.quant_max_file_bytes:
            skipped_files += 1
            warnings.append(f"skipped {file['fileId']}: file exceeds quant_max_file_bytes")
            continue

        rows = _read_rows(dataset_id, file, max_rows=settings.quant_max_rows)
        parsed_files += 1
        parsed_rows += len(rows)
        if dtype in TRADE_TYPES:
            trade_rows.extend(rows)
        elif dtype in PRICE_TYPES:
            price_rows.extend(rows)
        elif dtype in SIGNAL_TYPES:
            signal_rows.extend(rows)
        elif dtype in RISK_TYPES:
            risk_rows.extend(rows)
        elif dtype in POSITION_TYPES:
            position_rows.extend(rows)
        else:
            other_rows.extend(rows)
            warnings.append(
                f"parsed {file['fileId']} but ignored unknown datasetType={dtype or 'unknown'}"
            )

    coverage = {
        "datasetId": dataset_id,
        "tradingDate": dataset["tradingDate"],
        "machineId": dataset["machineId"],
        "sessionId": dataset.get("sessionId"),
        "fileCount": len(dataset.get("files", [])),
        "parsedFiles": parsed_files,
        "parsedRows": parsed_rows,
        "skippedFiles": skipped_files,
        "datasetTypes": dataset_types,
    }
    trade_metrics = _trade_metrics(trade_rows)
    replay = _market_replay(price_rows, max_points=settings.quant_replay_max_points)
    analytics = _analytics_bundle(
        dataset=dataset,
        coverage=coverage,
        trade_metrics=trade_metrics,
        replay=replay,
        trade_rows=trade_rows,
        price_rows=price_rows,
        signal_rows=signal_rows,
        risk_rows=risk_rows,
        position_rows=position_rows,
        other_rows=other_rows,
        warnings=warnings,
    )
    status = "READY" if parsed_rows and not warnings else "PARTIAL" if parsed_rows else "EMPTY"
    report = {
        "reportId": f"qrep-{dataset_id}",
        "datasetId": dataset_id,
        "machineId": dataset["machineId"],
        "tradingDate": dataset["tradingDate"],
        "status": status,
        "coverage": coverage,
        "tradeMetrics": trade_metrics,
        "marketReplay": replay,
        "analytics": analytics,
        "warnings": warnings,
    }
    return _normalise_report(quant_report_repo.upsert(report))


def synthetic_replay(payload: SyntheticReplayRequest) -> dict[str, Any]:
    settings = get_settings()
    steps = min(payload.steps, settings.quant_synthetic_max_steps)
    rng = random.Random(payload.seed)  # noqa: S311 - deterministic simulation, not crypto
    prices: list[dict[str, Any]] = []
    price = float(payload.startPrice)
    drift = float(payload.driftBps) / 10_000.0
    vol = float(payload.volatilityBps) / 10_000.0
    for i in range(steps):
        if i:
            shock = rng.gauss(drift, vol)
            price = max(0.0001, price * (1.0 + shock))
        prices.append({
            "time": f"T+{i:05d}",
            "symbol": payload.symbol,
            "price": price,
        })
    start, end = prices[0]["price"], prices[-1]["price"]
    trade = {
        "time": prices[-1]["time"],
        "symbol": payload.symbol,
        "strategy": "synthetic-buy-hold",
        "quantity": 1,
        "entry": start,
        "exit": end,
        "pnl": end - start,
    }
    return {
        "seed": payload.seed,
        "symbol": payload.symbol,
        "steps": steps,
        "replay": _market_replay(prices, max_points=settings.quant_replay_max_points),
        "tradeMetrics": _trade_metrics([trade]),
    }


def _metric(
    status: str,
    value: float | int | str | None = None,
    *,
    unit: str | None = None,
    reason: str | None = None,
    required_fields: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "value": value,
        "unit": unit,
        "reason": reason,
        "requiredFields": required_fields or [],
    }


def _available(value: float | int | str | None, unit: str | None = None) -> dict[str, Any]:
    return _metric("AVAILABLE", value, unit=unit)


def _not_available(reason: str, required_fields: list[str] | None = None) -> dict[str, Any]:
    return _metric("NOT_AVAILABLE", None, reason=reason, required_fields=required_fields)


def _insufficient(reason: str, required_fields: list[str] | None = None) -> dict[str, Any]:
    return _metric("INSUFFICIENT_DATA", None, reason=reason, required_fields=required_fields)


def _lineage_from_dataset(dataset: dict[str, Any]) -> dict[str, str | None]:
    return {
        "datasetId": dataset.get("datasetId"),
        "machineId": dataset.get("machineId"),
        "tradingDate": dataset.get("tradingDate"),
        "sessionId": dataset.get("sessionId"),
        "calculationVersion": ANALYTICS_VERSION,
    }


def _lineage_from_report(report: dict[str, Any]) -> dict[str, str | None]:
    coverage = report.get("coverage") or {}
    return {
        "datasetId": report.get("datasetId"),
        "machineId": report.get("machineId"),
        "tradingDate": report.get("tradingDate"),
        "sessionId": coverage.get("sessionId"),
        "calculationVersion": ANALYTICS_VERSION,
    }


def _section(
    status: str,
    lineage: dict[str, str | None],
    *,
    metrics: dict[str, dict[str, Any]] | None = None,
    dimensions: dict[str, dict[str, int]] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "calculationVersion": ANALYTICS_VERSION,
        "lineage": lineage,
        "metrics": metrics or {},
        "dimensions": dimensions or {},
        "warnings": warnings or [],
    }


def _empty_analytics(lineage: dict[str, str | None]) -> dict[str, Any]:
    reason = "analytics were not materialized for this report"
    return {
        category: _section(
            "NOT_AVAILABLE",
            lineage,
            metrics={"status": _not_available(reason)},
            warnings=[reason],
        )
        for category in ANALYTICS_CATEGORIES
    }


def _normalise_report(report: dict[str, Any]) -> dict[str, Any]:
    result = dict(report)
    lineage = _lineage_from_report(result)
    analytics = result.get("analytics")
    if not isinstance(analytics, dict):
        analytics = {}
    defaults = _empty_analytics(lineage)
    for category in ANALYTICS_CATEGORIES:
        if not isinstance(analytics.get(category), dict):
            analytics[category] = defaults[category]
    result["analytics"] = analytics
    coverage = dict(result.get("coverage") or {})
    coverage.setdefault("sessionId", None)
    result["coverage"] = coverage
    return result


def _analytics_bundle(
    *,
    dataset: dict[str, Any],
    coverage: dict[str, Any],
    trade_metrics: dict[str, Any],
    replay: dict[str, Any],
    trade_rows: list[dict[str, Any]],
    price_rows: list[dict[str, Any]],
    signal_rows: list[dict[str, Any]],
    risk_rows: list[dict[str, Any]],
    position_rows: list[dict[str, Any]],
    other_rows: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    lineage = _lineage_from_dataset(dataset)
    return {
        "performance": _performance_section(lineage, trade_metrics),
        "strategy": _strategy_section(lineage, trade_metrics),
        "execution": _execution_section(lineage, trade_rows),
        "signals": _signals_section(lineage, signal_rows),
        "risk": _risk_section(lineage, trade_metrics, risk_rows, position_rows),
        "sessions": _sessions_section(lineage, dataset, coverage, trade_metrics),
        "dataQuality": _data_quality_section(lineage, coverage, price_rows, other_rows, warnings),
        "marketReplay": replay,
    }


def _performance_section(
    lineage: dict[str, str | None],
    trade_metrics: dict[str, Any],
) -> dict[str, Any]:
    closed = int(trade_metrics.get("closedTrades") or 0)
    if closed <= 0:
        return _section(
            "INSUFFICIENT_DATA",
            lineage,
            metrics={
                "closedTrades": _available(closed, "count"),
                "grossPnl": _insufficient("closed trade PnL is required", ["pnl"]),
                "profitFactor": _insufficient(
                    "at least one winning and losing trade is required",
                    ["pnl"],
                ),
                "winRate": _insufficient("closed trade outcomes are required", ["pnl"]),
                "maxDrawdown": _insufficient("closed trade PnL series is required", ["pnl"]),
            },
        )
    return _section(
        "AVAILABLE",
        lineage,
        metrics={
            "closedTrades": _available(closed, "count"),
            "grossPnl": _available(trade_metrics["grossPnl"], "pnl"),
            "averagePnl": _available(trade_metrics["averagePnl"], "pnl"),
            "winRate": _available(trade_metrics["winRate"], "percent"),
            "expectancy": _available(trade_metrics["expectancy"], "pnl"),
            "profitFactor": (
                _available(trade_metrics["profitFactor"], "ratio")
                if trade_metrics.get("profitFactor") is not None
                else _not_available("no losing trades in the sample", ["pnl"])
            ),
            "maxDrawdown": _available(trade_metrics["maxDrawdown"], "pnl"),
            "sharpeLike": (
                _available(trade_metrics["sharpeLike"], "ratio")
                if trade_metrics.get("sharpeLike") is not None
                else _not_available("sample has zero or unavailable PnL variance", ["pnl"])
            ),
        },
    )


def _strategy_section(
    lineage: dict[str, str | None],
    trade_metrics: dict[str, Any],
) -> dict[str, Any]:
    total = int(trade_metrics.get("totalTrades") or 0)
    strategies = trade_metrics.get("strategies") or {}
    symbols = trade_metrics.get("symbols") or {}
    if total <= 0:
        return _section(
            "INSUFFICIENT_DATA",
            lineage,
            metrics={"tradeCount": _available(total, "count")},
            warnings=["strategy analytics require observed trades"],
        )
    return _section(
        "AVAILABLE",
        lineage,
        metrics={
            "tradeCount": _available(total, "count"),
            "strategyCount": _available(len(strategies), "count"),
            "symbolCount": _available(len(symbols), "count"),
            "grossPnl": _available(trade_metrics["grossPnl"], "pnl"),
            "winRate": _available(trade_metrics["winRate"], "percent"),
        },
        dimensions={"strategies": strategies, "symbols": symbols},
    )


def _float_values(rows: list[dict[str, Any]], *keys: str) -> list[float]:
    return [value for row in rows if (value := _float(row, *keys)) is not None]


def _sum_metric(rows: list[dict[str, Any]], *keys: str) -> dict[str, Any]:
    values = _float_values(rows, *keys)
    return _available(round(sum(values), 6)) if values else _not_available(
        "source field is absent", list(keys)
    )


def _avg_metric(rows: list[dict[str, Any]], *keys: str) -> dict[str, Any]:
    values = _float_values(rows, *keys)
    return _available(round(fmean(values), 6)) if values else _not_available(
        "source field is absent", list(keys)
    )


def _execution_section(
    lineage: dict[str, str | None],
    trade_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if not trade_rows:
        return _section(
            "INSUFFICIENT_DATA",
            lineage,
            metrics={"tradeCount": _available(0, "count")},
            warnings=["execution analytics require trade/fill rows"],
        )
    metrics = {
        "tradeCount": _available(len(trade_rows), "count"),
        "totalFees": _sum_metric(trade_rows, "fees", "fee", "commission", "cost"),
        "averageSpread": _avg_metric(trade_rows, "spread", "spreadBps", "spread_bps"),
        "averageSlippage": _avg_metric(trade_rows, "slippage", "slippageBps", "slippage_bps"),
        "averageLatencyMs": _avg_metric(trade_rows, "latencyMs", "latency_ms"),
    }
    expected = _float_values(trade_rows, "expectedPnl", "theoreticalPnl", "theoretical_pnl")
    actual = [_pnl(row) for row in trade_rows]
    actual = [value for value in actual if value is not None]
    if expected and actual and sum(expected):
        metrics["edgeCapturePct"] = _available(
            round(sum(actual) / sum(expected) * 100.0, 6),
            "percent",
        )
    else:
        metrics["edgeCapturePct"] = _not_available(
            "requires expected/theoretical PnL and realized PnL",
            ["expectedPnl", "pnl"],
        )
    status = (
        "AVAILABLE"
        if any(m["status"] == "AVAILABLE" for m in metrics.values())
        else "NOT_AVAILABLE"
    )
    return _section(status, lineage, metrics=metrics)


def _signals_section(
    lineage: dict[str, str | None],
    signal_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if not signal_rows:
        return _section(
            "NOT_AVAILABLE",
            lineage,
            metrics={"signalCount": _not_available("no signal dataset was provided", ["signals"])},
        )
    statuses = _counts(signal_rows, "status", "state", "action")
    rejected = sum(count for key, count in statuses.items() if "reject" in key.lower())
    stale = sum(count for key, count in statuses.items() if "stale" in key.lower())
    return _section(
        "AVAILABLE",
        lineage,
        metrics={
            "signalCount": _available(len(signal_rows), "count"),
            "rejectedSignals": _available(rejected, "count"),
            "staleSignals": _available(stale, "count"),
            "signalToOrderConversion": _not_available(
                "requires linked signal/order identifiers",
                ["signalId", "orderId"],
            ),
            "timeToExecution": _not_available(
                "requires linked signal and fill timestamps",
                ["signalId", "fillTime"],
            ),
        },
        dimensions={"statuses": statuses},
    )


def _risk_section(
    lineage: dict[str, str | None],
    trade_metrics: dict[str, Any],
    risk_rows: list[dict[str, Any]],
    position_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    metrics = {
        "riskEventCount": (
            _available(len(risk_rows), "count")
            if risk_rows
            else _not_available("no risk event dataset was provided", ["risk"])
        ),
        "maxDrawdown": (
            _available(trade_metrics["maxDrawdown"], "pnl")
            if int(trade_metrics.get("closedTrades") or 0) > 0
            else _insufficient("closed trade PnL is required", ["pnl"])
        ),
        "positionCount": (
            _available(len(position_rows), "count")
            if position_rows
            else _not_available("no position dataset was provided", ["positions"])
        ),
        "grossExposure": _sum_metric(position_rows, "exposure", "notional", "marketValue"),
    }
    status = (
        "AVAILABLE"
        if any(m["status"] == "AVAILABLE" for m in metrics.values())
        else "NOT_AVAILABLE"
    )
    return _section(
        status,
        lineage,
        metrics=metrics,
        dimensions={"riskReasons": _counts(risk_rows, "reason", "type")},
    )


def _sessions_section(
    lineage: dict[str, str | None],
    dataset: dict[str, Any],
    coverage: dict[str, Any],
    trade_metrics: dict[str, Any],
) -> dict[str, Any]:
    session_id = dataset.get("sessionId")
    if not session_id:
        return _section(
            "INSUFFICIENT_DATA",
            lineage,
            metrics={
                "sessionId": _insufficient(
                    "dataset does not declare sessionId",
                    ["sessionId"],
                )
            },
        )
    return _section(
        "AVAILABLE",
        lineage,
        metrics={
            "sessionId": _available(str(session_id)),
            "closedTrades": _available(int(trade_metrics.get("closedTrades") or 0), "count"),
            "grossPnl": _available(trade_metrics.get("grossPnl", 0.0), "pnl"),
            "parsedRows": _available(int(coverage.get("parsedRows") or 0), "count"),
            "durationSec": _not_available(
                "session start/end timestamps are not in this EOD manifest",
                ["start", "end"],
            ),
        },
    )


def _data_quality_section(
    lineage: dict[str, str | None],
    coverage: dict[str, Any],
    price_rows: list[dict[str, Any]],
    other_rows: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    parsed_rows = int(coverage.get("parsedRows") or 0)
    file_count = int(coverage.get("fileCount") or 0)
    parsed_files = int(coverage.get("parsedFiles") or 0)
    if parsed_rows <= 0:
        return _section(
            "INSUFFICIENT_DATA",
            lineage,
            metrics={"parsedRows": _available(parsed_rows, "count")},
            warnings=["no rows were parsed"],
        )
    explicit_times = [
        _text(row, "time", "ts", "timestamp", "datetime", "date") for row in price_rows
    ]
    explicit_times = [value for value in explicit_times if value]
    duplicate_times = len(explicit_times) - len(set(explicit_times))
    timestamp_anomalies = sum(
        1
        for previous, current in pairwise(explicit_times)
        if current < previous
    )
    coverage_pct = (parsed_files / file_count * 100.0) if file_count else 0.0
    return _section(
        "AVAILABLE",
        lineage,
        metrics={
            "parsedRows": _available(parsed_rows, "count"),
            "parsedFiles": _available(parsed_files, "count"),
            "fileCoveragePct": _available(round(coverage_pct, 6), "percent"),
            "skippedFiles": _available(int(coverage.get("skippedFiles") or 0), "count"),
            "priceRows": _available(len(price_rows), "count"),
            "duplicateTimestamps": _available(duplicate_times, "count"),
            "timestampAnomalies": _available(timestamp_anomalies, "count"),
            "ignoredRows": _available(len(other_rows), "count"),
        },
        dimensions={"datasetTypes": coverage.get("datasetTypes") or {}},
        warnings=warnings[:10],
    )


def _read_rows(dataset_id: str, file: dict[str, Any], *, max_rows: int) -> list[dict[str, Any]]:
    storage = get_dataset_storage()
    raw = storage.read_bytes(dataset_id, file["fileId"], max_bytes=int(file["sizeBytes"]))
    text = raw.decode("utf-8-sig")
    stripped = text.lstrip()
    if file["relativePath"].lower().endswith((".jsonl", ".ndjson")) or stripped.startswith("{"):
        rows = []
        for line in text.splitlines():
            if not line.strip():
                continue
            rows.append(json.loads(line))
            if len(rows) >= max_rows:
                break
        return rows
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        rows.append(dict(row))
        if len(rows) >= max_rows:
            break
    return rows


def _value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in {None, ""}:
            return row[key]
    return None


def _float(row: dict[str, Any], *keys: str) -> float | None:
    value = _value(row, *keys)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(row: dict[str, Any], *keys: str) -> str | None:
    value = _value(row, *keys)
    return str(value) if value is not None else None


def _pnl(row: dict[str, Any]) -> float | None:
    direct = _float(row, "pnl", "realizedPnl", "realized_pnl", "profit")
    if direct is not None:
        return direct
    entry = _float(row, "entry", "entryPrice", "entry_price")
    exit_ = _float(row, "exit", "exitPrice", "exit_price", "price")
    qty = _float(row, "quantity", "qty", "size") or 1.0
    if entry is None or exit_ is None:
        return None
    direction = (_text(row, "direction", "side") or "long").lower()
    sign = -1.0 if direction in {"short", "sell"} else 1.0
    return (exit_ - entry) * qty * sign


def _counts(rows: list[dict[str, Any]], *keys: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        value = _text(row, *keys)
        if value:
            result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items(), key=lambda item: (-item[1], item[0]))[:20])


def _max_drawdown(equity: list[float]) -> float:
    peak = 0.0
    drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        drawdown = max(drawdown, peak - value)
    return drawdown


def _trade_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pnls = [pnl for row in rows if (pnl := _pnl(row)) is not None]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    gross = sum(pnls)
    equity: list[float] = []
    running = 0.0
    for pnl in pnls:
        running += pnl
        equity.append(running)
    avg = fmean(pnls) if pnls else 0.0
    std = pstdev(pnls) if len(pnls) > 1 else 0.0
    return {
        "totalTrades": len(rows),
        "closedTrades": len(pnls),
        "winningTrades": len(wins),
        "losingTrades": len(losses),
        "grossPnl": round(gross, 6),
        "averagePnl": round(avg, 6),
        "winRate": round((len(wins) / len(pnls) * 100.0) if pnls else 0.0, 4),
        "profitFactor": round(sum(wins) / abs(sum(losses)), 6) if losses else None,
        "expectancy": round(avg, 6),
        "maxDrawdown": round(_max_drawdown(equity), 6),
        "sharpeLike": round(avg / std * math.sqrt(len(pnls)), 6) if std > 0 else None,
        "symbols": _counts(rows, "symbol", "instrument", "ticker"),
        "strategies": _counts(rows, "strategy", "strategyName", "strategy_name"),
    }


def _price(row: dict[str, Any]) -> float | None:
    return _float(row, "price", "close", "last", "ltp", "lastPrice", "last_price")


def _time(row: dict[str, Any], index: int) -> str:
    return _text(row, "time", "ts", "timestamp", "datetime", "date") or f"T+{index:05d}"


def _market_replay(rows: list[dict[str, Any]], *, max_points: int) -> dict[str, Any]:
    points = [
        {"t": _time(row, i), "price": price, "equity": None}
        for i, row in enumerate(rows)
        if (price := _price(row)) is not None
    ]
    if not points:
        return {"available": False, "points": []}
    prices = [point["price"] for point in points]
    returns = [
        (prices[i] / prices[i - 1] - 1.0)
        for i in range(1, len(prices))
        if prices[i - 1] != 0
    ]
    symbol = _text(rows[0], "symbol", "instrument", "ticker")
    start_price, end_price = prices[0], prices[-1]
    sampled = _downsample(points, max_points)
    return {
        "available": True,
        "symbol": symbol,
        "points": sampled,
        "startTime": points[0]["t"],
        "endTime": points[-1]["t"],
        "startPrice": round(start_price, 6),
        "endPrice": round(end_price, 6),
        "returnPct": round(((end_price / start_price - 1.0) * 100.0) if start_price else 0.0, 6),
        "high": round(max(prices), 6),
        "low": round(min(prices), 6),
        "maxDrawdownPct": round(_price_drawdown_pct(prices), 6),
        "volatilityPct": round(
            (pstdev(returns) * math.sqrt(len(returns)) * 100.0)
            if len(returns) > 1
            else 0.0,
            6,
        ),
    }


def _downsample(points: list[dict[str, Any]], max_points: int) -> list[dict[str, Any]]:
    if len(points) <= max_points:
        return points
    step = math.ceil(len(points) / max_points)
    sampled = points[::step]
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return sampled


def _price_drawdown_pct(prices: list[float]) -> float:
    peak = prices[0]
    drawdown = 0.0
    for price in prices:
        peak = max(peak, price)
        if peak:
            drawdown = max(drawdown, (peak - price) / peak * 100.0)
    return drawdown
