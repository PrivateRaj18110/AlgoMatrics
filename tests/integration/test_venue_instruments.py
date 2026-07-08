from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from algo_platform.modules.brokerage.infrastructure.models import BrokerModel
from algo_platform.modules.instruments.application.venue_directory import (
    VenueInstrumentDirectory,
)
from algo_platform.modules.instruments.infrastructure.models import InstrumentModel
from algo_platform.shared.domain.errors import ConflictError
from algo_platform.shared.domain.types import utc_now

pytestmark = pytest.mark.integration


async def test_venue_mapping_create_resolve_and_duplicate_guard(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    broker_id = uuid4()
    instrument_id = uuid4()
    now = utc_now()
    async with session_factory() as session:
        session.add(
            BrokerModel(
                id=broker_id,
                code="testvenue",
                name="Test Venue",
                description="",
                credential_fields=[],
                capabilities={},
                supports_paper=False,
                supports_live=True,
                is_active=True,
                created_at=now,
            )
        )
        session.add(
            InstrumentModel(
                id=instrument_id,
                symbol="CANONICAL-TEST",
                name="Canonical Test",
                exchange="TEST",
                asset_class="equity",
                currency="INR",
                tick_size=Decimal("0.05"),
                lot_size=Decimal("1"),
                price_precision=2,
                reference_price=Decimal("100"),
                is_active=True,
                created_at=now,
            )
        )
        await session.flush()

        directory = VenueInstrumentDirectory(session)
        created = await directory.create(
            broker_id=broker_id,
            instrument_id=instrument_id,
            venue_symbol="venue-test",
            exchange="nse",
            instrument_token="12345",
            tick_size=None,
            lot_size=Decimal("25"),
            contract_multiplier=Decimal("1"),
            venue_metadata={"segment": "NFO"},
        )
        assert created.venue_symbol == "VENUE-TEST"
        assert created.exchange == "NSE"
        assert created.lot_size == Decimal("25")

        resolved = await directory.resolve(
            broker_id=broker_id,
            instrument_id=instrument_id,
        )
        assert resolved.id == created.id
        assert resolved.instrument_token == "12345"

        with pytest.raises(ConflictError, match="already has a mapping"):
            await directory.create(
                broker_id=broker_id,
                instrument_id=instrument_id,
                venue_symbol="OTHER",
                exchange="NSE",
                instrument_token=None,
                tick_size=None,
                lot_size=None,
                contract_multiplier=Decimal("1"),
                venue_metadata={},
            )

