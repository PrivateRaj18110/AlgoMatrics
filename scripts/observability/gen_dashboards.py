"""Generate Algo Matrics Grafana dashboards as validated JSON.

Kept in the repo (scripts/observability) so dashboards are reproducible rather
than hand-edited blobs. Run: python gen_dashboards.py <output_dir>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}


def _grid(x: int, y: int, w: int, h: int) -> dict:
    return {"h": h, "w": w, "x": x, "y": y}


def timeseries(pid, title, x, y, exprs, *, unit="short", w=12, h=8, stack=False):
    targets = [
        {"expr": e, "legendFormat": lf, "refId": chr(65 + i), "datasource": PROM}
        for i, (e, lf) in enumerate(exprs)
    ]
    return {
        "id": pid,
        "type": "timeseries",
        "title": title,
        "datasource": PROM,
        "gridPos": _grid(x, y, w, h),
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "custom": {
                    "drawStyle": "line",
                    "fillOpacity": 15 if not stack else 40,
                    "stacking": {"mode": "normal" if stack else "none"},
                },
            },
            "overrides": [],
        },
        "options": {"legend": {"displayMode": "table", "placement": "bottom"}},
        "targets": targets,
    }


def stat(pid, title, x, y, expr, *, unit="short", w=6, h=6, legend=""):
    return {
        "id": pid,
        "type": "stat",
        "title": title,
        "datasource": PROM,
        "gridPos": _grid(x, y, w, h),
        "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"]},
            "colorMode": "value",
            "graphMode": "area",
        },
        "targets": [{"expr": expr, "legendFormat": legend, "refId": "A", "datasource": PROM}],
    }


def logs_panel(pid, title, x, y, expr, *, w=24, h=10):
    return {
        "id": pid,
        "type": "logs",
        "title": title,
        "datasource": LOKI,
        "gridPos": _grid(x, y, w, h),
        "options": {"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending"},
        "targets": [{"expr": expr, "refId": "A", "datasource": LOKI}],
    }


def dashboard(uid, title, tags, panels) -> dict:
    return {
        "uid": uid,
        "title": title,
        "tags": tags,
        "schemaVersion": 39,
        "version": 1,
        "editable": True,
        "refresh": "30s",
        "time": {"from": "now-6h", "to": "now"},
        "timezone": "",
        "templating": {"list": []},
        "annotations": {"list": []},
        "panels": panels,
    }


def api_dashboard() -> dict:
    panels = [
        stat(1, "Requests / sec", 0, 0, "sum(rate(algo_http_requests_total[5m]))", unit="reqps"),
        stat(
            2,
            "Error rate",
            6,
            0,
            'sum(rate(algo_http_requests_total{status=~"5.."}[5m]))'
            " / clamp_min(sum(rate(algo_http_requests_total[5m])), 1e-9)",
            unit="percentunit",
        ),
        stat(
            3,
            "p95 latency",
            12,
            0,
            "histogram_quantile(0.95, sum by (le)"
            " (rate(algo_http_request_duration_seconds_bucket[5m])))",
            unit="s",
        ),
        stat(4, "In-flight", 18, 0, "sum(algo_http_requests_in_progress)"),
        timeseries(
            5,
            "Request rate by route",
            0,
            6,
            [("sum by (route) (rate(algo_http_requests_total[5m]))", "{{route}}")],
            unit="reqps",
        ),
        timeseries(
            6,
            "Latency quantiles (p50/p90/p99)",
            12,
            6,
            [
                (
                    f"histogram_quantile({q}, sum by (le)"
                    " (rate(algo_http_request_duration_seconds_bucket[5m])))",
                    lbl,
                )
                for q, lbl in [(0.5, "p50"), (0.9, "p90"), (0.99, "p99")]
            ],
            unit="s",
        ),
        timeseries(
            7,
            "Responses by status",
            0,
            14,
            [("sum by (status) (rate(algo_http_requests_total[5m]))", "{{status}}")],
            unit="reqps",
            stack=True,
        ),
        timeseries(
            8,
            "5xx errors by route",
            12,
            14,
            [
                (
                    'sum by (route) (rate(algo_http_requests_total{status=~"5.."}[5m]))',
                    "{{route}}",
                )
            ],
            unit="reqps",
        ),
        logs_panel(
            9,
            "Error logs",
            0,
            22,
            '{service="api"} | json | level=~"error|warning"',
        ),
    ]
    return dashboard(
        "algo-api-overview", "Algo Matrics — API Latency & Errors", ["algo", "api"], panels
    )


def trading_dashboard() -> dict:
    panels = [
        stat(1, "Orders / min", 0, 0, "sum(rate(algo_orders_submitted_total[5m])) * 60"),
        stat(
            2,
            "Reject ratio",
            6,
            0,
            "sum(rate(algo_orders_rejected_total[5m]))"
            " / clamp_min(sum(rate(algo_orders_submitted_total[5m])), 1e-9)",
            unit="percentunit",
        ),
        stat(3, "Open positions", 12, 0, "sum(algo_positions_open)"),
        stat(4, "Active strategy runs", 18, 0, "sum(algo_strategy_runs_active)"),
        timeseries(
            5,
            "Order flow (submitted / filled / rejected)",
            0,
            6,
            [
                ("sum(rate(algo_orders_submitted_total[5m]))", "submitted"),
                ("sum(rate(algo_orders_filled_total[5m]))", "filled"),
                ("sum(rate(algo_orders_rejected_total[5m]))", "rejected"),
            ],
            unit="ops",
        ),
        timeseries(
            6,
            "P&L by mode",
            12,
            6,
            [('sum by (mode) (algo_pnl{kind="realized"})', "realized {{mode}}"),
             ('sum by (mode) (algo_pnl{kind="unrealized"})', "unrealized {{mode}}")],
            unit="currencyINR",
        ),
        timeseries(
            7,
            "Open positions by mode",
            0,
            14,
            [("sum by (mode) (algo_positions_open)", "{{mode}}")],
        ),
        timeseries(
            8,
            "Rejections by reason",
            12,
            14,
            [("sum by (reason) (rate(algo_orders_rejected_total[5m]))", "{{reason}}")],
            unit="ops",
        ),
        stat(9, "Market ticks / sec", 0, 22, "sum(rate(algo_market_ticks_total[1m]))", w=8),
        timeseries(
            10,
            "Broker health (1=up)",
            8,
            22,
            [("algo_broker_up", "{{broker}}")],
            w=16,
            h=6,
        ),
    ]
    return dashboard(
        "algo-trading", "Algo Matrics — Trading, Orders & P&L", ["algo", "trading"], panels
    )


def infra_dashboard() -> dict:
    panels = [
        stat(1, "Redis up", 0, 0, "min(algo_redis_up)"),
        stat(2, "DB pool in use", 6, 0, 'sum(algo_db_pool_connections{state="checked_out"})'),
        stat(3, "WS connections", 12, 0, "sum(algo_ws_connections)"),
        stat(4, "Max stream depth", 18, 0, "max(algo_stream_depth)"),
        timeseries(
            5,
            "Process CPU",
            0,
            6,
            [("rate(algo_process_cpu_seconds_total[5m])", "{{service}}")],
            unit="percentunit",
        ),
        timeseries(
            6,
            "Process resident memory",
            12,
            6,
            [("algo_process_resident_memory_bytes", "{{service}}")],
            unit="bytes",
        ),
        timeseries(
            7,
            "DB pool connections",
            0,
            14,
            [("sum by (state) (algo_db_pool_connections)", "{{state}}")],
        ),
        timeseries(
            8,
            "Stream depth (backlog)",
            12,
            14,
            [("algo_stream_depth", "{{stream}}")],
        ),
        timeseries(
            9,
            "Event throughput",
            0,
            22,
            [
                ("sum by (stream) (rate(algo_events_published_total[5m]))", "pub {{stream}}"),
                ("sum by (stream) (rate(algo_events_consumed_total[5m]))", "con {{stream}}"),
            ],
            unit="ops",
        ),
        timeseries(
            10,
            "WebSocket frames",
            12,
            22,
            [("sum by (direction) (rate(algo_ws_messages_total[5m]))", "{{direction}}")],
            unit="ops",
        ),
    ]
    return dashboard(
        "algo-infrastructure", "Algo Matrics — Infrastructure & Queues", ["algo", "infra"], panels
    )


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    dashboards = {
        "api-overview.json": api_dashboard(),
        "trading.json": trading_dashboard(),
        "infrastructure.json": infra_dashboard(),
    }
    for name, doc in dashboards.items():
        text = json.dumps(doc, indent=2)
        json.loads(text)  # validate round-trip
        (out / name).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {name} ({len(doc['panels'])} panels)")


if __name__ == "__main__":
    main()
