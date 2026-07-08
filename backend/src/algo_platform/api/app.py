from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from algo_platform.api.middleware.errors import register_exception_handlers
from algo_platform.api.middleware.request_context import RequestContextMiddleware
from algo_platform.api.routes.health import router as health_router
from algo_platform.api.routes.metrics import router as metrics_router
from algo_platform.config import Settings, get_settings
from algo_platform.modules.billing.application.ports import PaymentProvider
from algo_platform.modules.billing.infrastructure.providers.razorpay import RazorpayProvider
from algo_platform.modules.billing.infrastructure.providers.stripe import StripeProvider
from algo_platform.shared.infrastructure.database import create_engine, create_session_factory
from algo_platform.shared.infrastructure.email import create_email_sender
from algo_platform.shared.infrastructure.encryption import CredentialCipher
from algo_platform.shared.infrastructure.jwt_service import JwtService
from algo_platform.shared.infrastructure.metrics import MetricsRecorder
from algo_platform.shared.infrastructure.prometheus import PrometheusMetrics
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway
from algo_platform.shared.infrastructure.telemetry import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(level=resolved.log_level, env=resolved.app_env, service=resolved.service_name)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Create shared pools/clients here; never connect at import time.
        engine = create_engine(resolved.database_url, pool_size=resolved.database_pool_size)
        redis = RedisGateway.from_url(resolved.redis_url)
        app.state.settings = resolved
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        app.state.redis = redis
        app.state.jwt = JwtService(
            private_key_pem=resolved.load_jwt_private_key(),
            public_key_pem=resolved.load_jwt_public_key(),
            issuer=resolved.jwt_issuer,
            audience=resolved.jwt_audience,
            access_ttl_seconds=resolved.access_token_ttl_seconds,
        )
        app.state.cipher = CredentialCipher.from_base64(
            resolved.load_broker_kek_b64(), key_version=resolved.credential_key_version
        )
        app.state.email_sender = create_email_sender(resolved)
        app.state.metrics = MetricsRecorder(redis)
        if resolved.metrics_enabled:
            app.state.prometheus = PrometheusMetrics(
                namespace=resolved.metrics_namespace,
                service=resolved.service_name,
                version=app.version,
                env=resolved.app_env,
            )
        app.state.payment_providers = build_payment_providers(resolved)
        try:
            yield
        finally:
            await redis.close()
            await engine.dispose()

    app = FastAPI(
        title="Algo Matrics API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if resolved.app_env in {"local", "test"} else None,
        openapi_url="/openapi.json",
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "X-Org-Id", "X-API-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    register_exception_handlers(app)

    _include_routers(app)
    return app


def build_payment_providers(settings: Settings) -> dict[str, PaymentProvider]:
    providers: dict[str, PaymentProvider] = {}
    if settings.razorpay_key_id and settings.razorpay_key_secret:
        providers["razorpay"] = RazorpayProvider(
            key_id=settings.razorpay_key_id,
            key_secret=settings.razorpay_key_secret,
            webhook_secret=settings.razorpay_webhook_secret,
        )
    if settings.stripe_secret_key:
        providers["stripe"] = StripeProvider(
            secret_key=settings.stripe_secret_key,
            webhook_secret=settings.stripe_webhook_secret,
        )
    return providers


def _include_routers(app: FastAPI) -> None:
    from algo_platform.api.routes.admin import router as admin_router
    from algo_platform.api.routes.audit import router as audit_router
    from algo_platform.api.websocket.hub import router as ws_router
    from algo_platform.modules.billing.presentation.router import (
        router as billing_router,
    )
    from algo_platform.modules.billing.presentation.router import (
        webhooks_router as billing_webhooks_router,
    )
    from algo_platform.modules.brokerage.presentation.router import (
        router as brokerage_router,
    )
    from algo_platform.modules.identity.presentation.auth_router import (
        router as auth_router,
    )
    from algo_platform.modules.identity.presentation.users_router import (
        api_keys_router,
    )
    from algo_platform.modules.identity.presentation.users_router import (
        router as users_router,
    )
    from algo_platform.modules.instruments.presentation.router import (
        admin_router as venue_instruments_admin_router,
    )
    from algo_platform.modules.instruments.presentation.router import (
        router as market_data_router,
    )
    from algo_platform.modules.notifications.presentation.router import (
        router as notifications_router,
    )
    from algo_platform.modules.organizations.presentation.router import (
        router as organizations_router,
    )
    from algo_platform.modules.portfolio.presentation.router import (
        router as portfolio_router,
    )
    from algo_platform.modules.risk.presentation.router import router as risk_router
    from algo_platform.modules.strategies.presentation.router import (
        router as strategies_router,
    )
    from algo_platform.modules.trading.presentation.router import (
        router as trading_router,
    )

    # Prometheus scrape endpoint is mounted at the root, not under /api/v1.
    app.include_router(metrics_router)

    prefix = "/api/v1"
    app.include_router(health_router, prefix=prefix)
    app.include_router(auth_router, prefix=prefix)
    app.include_router(users_router, prefix=prefix)
    app.include_router(api_keys_router, prefix=prefix)
    app.include_router(organizations_router, prefix=prefix)
    app.include_router(billing_router, prefix=prefix)
    app.include_router(billing_webhooks_router, prefix=prefix)
    app.include_router(notifications_router, prefix=prefix)
    app.include_router(brokerage_router, prefix=prefix)
    app.include_router(market_data_router, prefix=prefix)
    app.include_router(venue_instruments_admin_router, prefix=prefix)
    app.include_router(trading_router, prefix=prefix)
    app.include_router(risk_router, prefix=prefix)
    app.include_router(strategies_router, prefix=prefix)
    app.include_router(portfolio_router, prefix=prefix)
    app.include_router(audit_router, prefix=prefix)
    app.include_router(admin_router, prefix=prefix)
    app.include_router(ws_router, prefix=prefix)


app = create_app()
