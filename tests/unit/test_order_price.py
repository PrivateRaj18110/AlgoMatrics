from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from algo_platform.modules.trading.application.order_service import (
    OrderService,
    last_price_from_tick,
    live_last_price_from_tick,
)
from algo_platform.shared.domain.errors import ConflictError


def _service(redis: AsyncMock) -> OrderService:
    return OrderService(
        session=MagicMock(),
        redis=redis,
        billing=MagicMock(),
        risk=MagicMock(),
    )


def test_last_price_from_tick_parses_numeric_payload() -> None:
    assert last_price_from_tick({"last": "101.25"}) == Decimal("101.25")


def test_last_price_from_tick_missing_is_none() -> None:
    assert last_price_from_tick(None) is None
    assert last_price_from_tick({}) is None
    assert last_price_from_tick({"last": ""}) is None


def test_live_last_price_accepts_fresh_tick() -> None:
    now = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
    tick = {"last": "22450.50", "timestamp": (now - timedelta(seconds=2)).isoformat()}
    assert live_last_price_from_tick(tick, now=now) == Decimal("22450.50")


def test_live_last_price_blocks_missing_tick() -> None:
    with pytest.raises(ConflictError, match="unavailable"):
        live_last_price_from_tick(None)


def test_live_last_price_blocks_missing_timestamp() -> None:
    with pytest.raises(ConflictError, match="timestamp missing"):
        live_last_price_from_tick({"last": "100"})


def test_live_last_price_blocks_stale_tick() -> None:
    now = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
    tick = {"last": "100", "timestamp": (now - timedelta(seconds=90)).isoformat()}
    with pytest.raises(ConflictError, match="stale"):
        live_last_price_from_tick(tick, now=now)


@pytest.mark.asyncio
async def test_estimate_price_live_blocks_before_any_broker_path() -> None:
    redis = AsyncMock()
    redis.hget_json = AsyncMock(return_value=None)
    service = _service(redis)
    with pytest.raises(ConflictError, match="unavailable"):
        await service._estimate_price(uuid4(), None, fail_closed=True)
    redis.hget_json.assert_awaited()


@pytest.mark.asyncio
async def test_estimate_price_live_uses_fresh_last() -> None:
    now = datetime.now(tz=UTC)
    redis = AsyncMock()
    redis.hget_json = AsyncMock(
        return_value={"last": "101.5", "timestamp": now.isoformat()},
    )
    service = _service(redis)
    price = await service._estimate_price(uuid4(), None, fail_closed=True)
    assert price == Decimal("101.5")


@pytest.mark.asyncio
async def test_estimate_price_paper_falls_back_to_reference() -> None:
    redis = AsyncMock()
    redis.hget_json = AsyncMock(return_value=None)
    service = _service(redis)
    instrument = MagicMock()
    instrument.reference_price = Decimal("2900")
    service._instruments.get = AsyncMock(return_value=instrument)
    price = await service._estimate_price(uuid4(), None, fail_closed=False)
    assert price == Decimal("2900")


@pytest.mark.asyncio
async def test_estimate_price_limit_short_circuits_market_data() -> None:
    redis = AsyncMock()
    service = _service(redis)
    price = await service._estimate_price(uuid4(), Decimal("12.5"), fail_closed=True)
    assert price == Decimal("12.5")
    redis.hget_json.assert_not_called()


def _live_account() -> MagicMock:
    from algo_platform.modules.brokerage.domain.brokers import AccountMode, AccountStatus

    account = MagicMock()
    account.status = AccountStatus.ACTIVE
    account.mode = AccountMode.LIVE
    account.connection_id = uuid4()
    account.equity = Decimal("10000")
    account.starting_balance = Decimal("10000")
    return account


@pytest.mark.asyncio
async def test_live_place_order_blocks_unknown_broker_before_pricing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from algo_platform.modules.trading.domain.orders import OrderType, TimeInForce
    from algo_platform.shared.domain.types import AccountId, Side, TenantId

    redis = AsyncMock()
    service = _service(redis)
    service._accounts.get = AsyncMock(return_value=_live_account())
    service._instruments.get = AsyncMock(return_value=MagicMock())

    class _Policy:
        def __init__(self, session: object) -> None:
            pass

        async def live_trading_enabled(self, organization_id: object) -> bool:
            return True

    class _Connections:
        def __init__(self, session: object) -> None:
            pass

        async def get(self, organization_id: object, connection_id: object) -> None:
            return None

    monkeypatch.setattr(
        "algo_platform.modules.trading.application.order_service.OrganizationPolicy",
        _Policy,
    )
    monkeypatch.setattr(
        "algo_platform.modules.trading.application.order_service.SqlBrokerConnectionRepository",
        _Connections,
    )

    with pytest.raises(ConflictError, match="not verified"):
        await service.place_order(
            TenantId(uuid4()),
            account_id=AccountId(uuid4()),
            instrument_id=uuid4(),
            side=Side.BUY,
            quantity=Decimal("1"),
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
            limit_price=None,
            stop_price=None,
            client_order_id="live-unknown-broker",
        )
    redis.hget_json.assert_not_called()


@pytest.mark.asyncio
async def test_live_place_order_blocks_when_risk_engine_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from algo_platform.modules.trading.domain.orders import OrderType, TimeInForce
    from algo_platform.shared.domain.types import AccountId, Side, TenantId

    redis = AsyncMock()
    redis.hget_json = AsyncMock(
        return_value={"last": "100", "timestamp": datetime.now(tz=UTC).isoformat()},
    )
    service = _service(redis)
    service._accounts.get = AsyncMock(return_value=_live_account())
    service._instruments.get = AsyncMock(return_value=MagicMock())
    service._session.get_bind.return_value.dialect.name = "sqlite"
    service._orders.get_by_client_order_id = AsyncMock(return_value=None)
    service._acquire_order_lock = AsyncMock()
    service._realized_pnl_today = AsyncMock(return_value=Decimal("0"))
    service._billing.current_limits = AsyncMock(
        return_value=MagicMock(max_orders_per_day=100),
    )
    service._billing.orders_placed_today = AsyncMock(return_value=0)
    service._positions.count_open_for_account = AsyncMock(return_value=0)
    service._positions.gross_exposure_for_account = AsyncMock(return_value=Decimal("0"))
    service._risk.evaluate_order = AsyncMock(side_effect=RuntimeError("risk unavailable"))

    class _Policy:
        def __init__(self, session: object) -> None:
            pass

        async def live_trading_enabled(self, organization_id: object) -> bool:
            return True

    class _Connections:
        def __init__(self, session: object) -> None:
            pass

        async def get(self, organization_id: object, connection_id: object) -> MagicMock:
            connection = MagicMock()
            connection.status.value = "verified"
            connection.broker_id = uuid4()
            return connection

    class _Venue:
        def __init__(self, session: object) -> None:
            pass

        async def resolve(self, **kwargs: object) -> None:
            return None

    monkeypatch.setattr(
        "algo_platform.modules.trading.application.order_service.OrganizationPolicy",
        _Policy,
    )
    monkeypatch.setattr(
        "algo_platform.modules.trading.application.order_service.SqlBrokerConnectionRepository",
        _Connections,
    )
    monkeypatch.setattr(
        "algo_platform.modules.trading.application.order_service.VenueInstrumentDirectory",
        _Venue,
    )
    engine = AsyncMock()
    monkeypatch.setattr(
        "algo_platform.modules.trading.application.order_service.enqueue_engine_command",
        engine,
    )

    with pytest.raises(RuntimeError, match="risk unavailable"):
        await service.place_order(
            TenantId(uuid4()),
            account_id=AccountId(uuid4()),
            instrument_id=uuid4(),
            side=Side.BUY,
            quantity=Decimal("1"),
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
            limit_price=None,
            stop_price=None,
            client_order_id="live-risk-down",
        )
    engine.assert_not_called()
