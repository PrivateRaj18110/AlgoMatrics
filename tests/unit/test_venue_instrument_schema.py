from sqlalchemy import CheckConstraint, UniqueConstraint

from algo_platform.modules.instruments.infrastructure.models import VenueInstrumentModel


def test_venue_instrument_schema_enforces_identity_and_positive_sizes() -> None:
    table = VenueInstrumentModel.__table__
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    check_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert ("broker_id", "instrument_id") in unique_columns
    assert ("broker_id", "exchange", "venue_symbol") in unique_columns
    assert "ck_venue_instruments_positive_sizes" in check_names
