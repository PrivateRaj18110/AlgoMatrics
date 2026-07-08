"""Unit tests for the browser RUM intake endpoint (Phase 1, slice D)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from algo_platform.api.routes.rum import router as rum_router
from algo_platform.shared.infrastructure.prometheus import PrometheusMetrics


def _client() -> tuple[TestClient, PrometheusMetrics]:
    app = FastAPI()
    metrics = PrometheusMetrics(namespace="algo", service="t", version="t", env="test")
    app.state.prometheus = metrics
    app.include_router(rum_router, prefix="/api/v1")
    return TestClient(app), metrics


def test_valid_report_records_web_vitals_and_errors() -> None:
    client, metrics = _client()
    response = client.post(
        "/api/v1/rum",
        json={
            "metrics": [{"name": "LCP", "value": 1200.5}, {"name": "CLS", "value": 0.05}],
            "errors": [{"kind": "unhandledrejection"}, {"kind": "weird-thing"}],
        },
    )
    assert response.status_code == 204
    body = metrics.render().decode()
    assert 'algo_frontend_web_vitals_bucket{le="2000.0",metric="LCP"}' in body
    # Unknown error kind is normalised to "other".
    assert metrics.registry.get_sample_value(
        "algo_frontend_errors_total", {"kind": "other"}
    ) == 1.0
    assert metrics.registry.get_sample_value(
        "algo_frontend_errors_total", {"kind": "unhandledrejection"}
    ) == 1.0


def test_unknown_metric_name_is_rejected() -> None:
    client, _ = _client()
    response = client.post("/api/v1/rum", json={"metrics": [{"name": "BOGUS", "value": 1}]})
    assert response.status_code == 422


def test_out_of_range_value_is_rejected() -> None:
    client, _ = _client()
    response = client.post(
        "/api/v1/rum", json={"metrics": [{"name": "LCP", "value": 9_999_999}]}
    )
    assert response.status_code == 422


def test_oversized_arrays_are_rejected() -> None:
    client, _ = _client()
    response = client.post(
        "/api/v1/rum",
        json={"metrics": [{"name": "FCP", "value": 1} for _ in range(100)]},
    )
    assert response.status_code == 422


def test_empty_report_is_accepted() -> None:
    client, _ = _client()
    assert client.post("/api/v1/rum", json={}).status_code == 204
