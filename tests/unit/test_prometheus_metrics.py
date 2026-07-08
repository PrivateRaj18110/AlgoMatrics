"""Unit tests for the Prometheus metrics foundation (Phase 1, slice A)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from algo_platform.api.middleware.request_context import (
    CORRELATION_ID_HEADER,
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
)
from algo_platform.api.routes.metrics import router as metrics_router
from algo_platform.shared.infrastructure.prometheus import (
    CONTENT_TYPE_LATEST,
    PrometheusMetrics,
)


def _build_metrics() -> PrometheusMetrics:
    return PrometheusMetrics(
        namespace="algo", service="algo-api", version="test", env="test"
    )


def test_render_exposes_catalogue_and_app_info() -> None:
    metrics = _build_metrics()
    body = metrics.render().decode()

    assert "algo_http_requests_total" in body
    assert "algo_http_request_duration_seconds" in body
    assert "algo_orders_submitted_total" in body
    assert "algo_broker_requests_total" in body
    assert 'service="algo-api"' in body
    assert 'env="test"' in body


def test_registries_are_isolated() -> None:
    # Two instances must not collide on the global default registry.
    first = _build_metrics()
    second = _build_metrics()
    assert first.registry is not second.registry
    first.orders_filled_total.labels(broker="paper", mode="paper").inc()
    assert "algo_orders_filled_total" in second.render().decode()


def _app_with_metrics() -> tuple[FastAPI, PrometheusMetrics]:
    app = FastAPI()
    metrics = _build_metrics()
    app.state.prometheus = metrics
    app.add_middleware(RequestContextMiddleware)
    app.include_router(metrics_router)

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    return app, metrics


def test_request_records_prometheus_and_correlation_headers() -> None:
    app, _ = _app_with_metrics()
    with TestClient(app) as client:
        response = client.get("/ping")
        assert response.status_code == 200
        assert response.headers[REQUEST_ID_HEADER]
        assert response.headers[CORRELATION_ID_HEADER]

        scrape = client.get("/metrics")
        assert scrape.status_code == 200
        assert scrape.headers["content-type"].startswith(CONTENT_TYPE_LATEST.split(";")[0])
        body = scrape.text
        # The /ping request must have been counted under its route template.
        assert 'route="/ping"' in body
        assert 'algo_http_requests_total{method="GET",route="/ping",status="200"}' in body


def test_correlation_id_is_propagated_from_upstream() -> None:
    app, _ = _app_with_metrics()
    with TestClient(app) as client:
        response = client.get("/ping", headers={CORRELATION_ID_HEADER: "trace-abc123"})
        assert response.headers[CORRELATION_ID_HEADER] == "trace-abc123"


def test_unmatched_route_collapses_label() -> None:
    app, _ = _app_with_metrics()
    with TestClient(app) as client:
        client.get("/does-not-exist-" + "x" * 40)
        body = client.get("/metrics").text
        assert 'route="unmatched"' in body


def test_metrics_endpoint_absent_returns_404() -> None:
    app = FastAPI()
    app.include_router(metrics_router)
    with TestClient(app) as client:
        assert client.get("/metrics").status_code == 404
