from decimal import Decimal
from uuid import uuid4

from algo_platform.modules.trading.domain.positions import Position
from algo_platform.shared.domain.types import AccountId, Side, TenantId


def make_position() -> Position:
    return Position.open_empty(
        organization_id=TenantId(uuid4()),
        account_id=AccountId(uuid4()),
        instrument_id=uuid4(),
    )


def test_open_long_and_average_up() -> None:
    position = make_position()
    position.apply_execution(Side.BUY, Decimal("10"), Decimal("100"), Decimal("0"))
    position.apply_execution(Side.BUY, Decimal("10"), Decimal("110"), Decimal("0"))
    assert position.quantity == Decimal("20")
    assert position.average_price == Decimal("105")
    assert position.side == "long"


def test_partial_close_realizes_pnl() -> None:
    position = make_position()
    position.apply_execution(Side.BUY, Decimal("10"), Decimal("100"), Decimal("0"))
    realized = position.apply_execution(Side.SELL, Decimal("4"), Decimal("120"), Decimal("0"))
    assert realized == Decimal("80")  # (120-100)*4
    assert position.quantity == Decimal("6")
    assert position.average_price == Decimal("100")
    assert position.realized_pnl == Decimal("80")


def test_full_close_resets_average() -> None:
    position = make_position()
    position.apply_execution(Side.BUY, Decimal("5"), Decimal("50"), Decimal("0"))
    position.apply_execution(Side.SELL, Decimal("5"), Decimal("40"), Decimal("0"))
    assert position.is_flat
    assert position.average_price == Decimal("0")
    assert position.realized_pnl == Decimal("-50")


def test_flip_through_zero_opens_opposite_side() -> None:
    position = make_position()
    position.apply_execution(Side.BUY, Decimal("10"), Decimal("100"), Decimal("0"))
    realized = position.apply_execution(Side.SELL, Decimal("15"), Decimal("110"), Decimal("0"))
    assert realized == Decimal("100")  # closed 10 at +10 each
    assert position.quantity == Decimal("-5")
    assert position.average_price == Decimal("110")
    assert position.side == "short"


def test_short_cover_realizes_pnl() -> None:
    position = make_position()
    position.apply_execution(Side.SELL, Decimal("8"), Decimal("200"), Decimal("0"))
    realized = position.apply_execution(Side.BUY, Decimal("8"), Decimal("180"), Decimal("0"))
    assert realized == Decimal("160")  # (180-200)*8*(-1)
    assert position.is_flat


def test_fees_reduce_realized_pnl() -> None:
    position = make_position()
    position.apply_execution(Side.BUY, Decimal("10"), Decimal("100"), Decimal("5"))
    realized = position.apply_execution(Side.SELL, Decimal("10"), Decimal("101"), Decimal("5"))
    assert realized == Decimal("5")  # 10 profit - 5 fee on the close
    assert position.realized_pnl == Decimal("0")  # 10 - 5 - 5
    assert position.fees_paid == Decimal("10")


def test_unrealized_pnl_uses_mark() -> None:
    position = make_position()
    position.apply_execution(Side.BUY, Decimal("10"), Decimal("100"), Decimal("0"))
    position.mark(Decimal("108"))
    assert position.unrealized_pnl == Decimal("80")
    assert position.market_value == Decimal("1080")
