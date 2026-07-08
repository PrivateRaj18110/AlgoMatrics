"""Domain tests for the brokerage aggregate: catalog credential validation,
connection lifecycle, and trading-account onboarding."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from algo_platform.modules.brokerage.domain.brokers import (
    AccountMode,
    Broker,
    BrokerConnection,
    ConnectionStatus,
    CredentialField,
    TradingAccount,
)
from algo_platform.shared.domain.errors import ConflictError, ValidationFailed
from algo_platform.shared.domain.types import TenantId, UserId


def _broker() -> Broker:
    return Broker(
        id=uuid4(),
        code="zerodha",
        name="Zerodha",
        description="",
        credential_fields=[
            CredentialField(name="api_key", label="API key", secret=False),
            CredentialField(name="access_token", label="Access token", secret=True),
        ],
        capabilities={},
        supports_paper=False,
        supports_live=True,
    )


class TestBrokerCredentials:
    def test_valid_credentials_are_trimmed(self) -> None:
        cleaned = _broker().validate_credentials({"api_key": "  k  ", "access_token": "t"})
        assert cleaned == {"api_key": "k", "access_token": "t"}

    def test_unknown_field_rejected(self) -> None:
        with pytest.raises(ValidationFailed, match="unknown credential fields"):
            _broker().validate_credentials({"api_key": "k", "access_token": "t", "rogue": "x"})

    def test_missing_required_field_rejected(self) -> None:
        with pytest.raises(ValidationFailed, match="required"):
            _broker().validate_credentials({"api_key": "k", "access_token": "  "})

    def test_overlong_value_rejected(self) -> None:
        with pytest.raises(ValidationFailed, match="too long"):
            _broker().validate_credentials({"api_key": "k", "access_token": "t" * 2001})


class TestBrokerConnection:
    def _connection(self) -> BrokerConnection:
        return BrokerConnection.create(
            organization_id=TenantId(uuid4()),
            broker=_broker(),
            name="  Prod  ",
            credential_ciphertext="c",
            credential_wrapped_dek="d",
            key_version=1,
            created_by=UserId(uuid4()),
            connection_id=uuid4(),
        )

    def test_create_trims_name(self) -> None:
        assert self._connection().name == "Prod"

    def test_blank_name_rejected(self) -> None:
        with pytest.raises(ValidationFailed, match="name is required"):
            BrokerConnection.create(
                organization_id=TenantId(uuid4()),
                broker=_broker(),
                name="   ",
                credential_ciphertext="c",
                credential_wrapped_dek="d",
                key_version=1,
                created_by=UserId(uuid4()),
                connection_id=uuid4(),
            )

    def test_verify_then_fail_transitions(self) -> None:
        connection = self._connection()
        connection.mark_verified()
        assert connection.status is ConnectionStatus.VERIFIED
        assert connection.last_verified_at is not None
        connection.mark_failed("bad token" * 60)
        assert connection.status is ConnectionStatus.FAILED
        assert connection.failure_reason is not None
        assert len(connection.failure_reason) <= 300

    def test_disable_twice_conflicts(self) -> None:
        connection = self._connection()
        connection.disable()
        with pytest.raises(ConflictError, match="already disabled"):
            connection.disable()

    def test_soft_delete_disables(self) -> None:
        connection = self._connection()
        connection.soft_delete()
        assert connection.deleted_at is not None
        assert connection.status is ConnectionStatus.DISABLED

    def test_rotate_credentials_returns_to_pending(self) -> None:
        connection = self._connection()
        connection.mark_verified()
        connection.rotate_credentials(ciphertext="c2", wrapped_dek="d2", key_version=2)
        assert connection.status is ConnectionStatus.PENDING
        assert connection.key_version == 2
        assert connection.credential_ciphertext == "c2"


class TestTradingAccount:
    def _open(self, **overrides: object) -> TradingAccount:
        base: dict[str, object] = {
            "organization_id": TenantId(uuid4()),
            "connection_id": uuid4(),
            "external_account_id": "X1",
            "name": "  ",
            "mode": AccountMode.PAPER,
            "base_currency": "inr",
            "starting_balance": Decimal("100000"),
        }
        base.update(overrides)
        return TradingAccount.open(**base)  # type: ignore[arg-type]

    def test_open_defaults_and_normalizes(self) -> None:
        account = self._open()
        assert account.name == "Account"
        assert account.base_currency == "INR"
        assert account.equity == Decimal("100000")
        assert account.cash_balance == Decimal("100000")

    def test_negative_balance_rejected(self) -> None:
        with pytest.raises(ValidationFailed, match="negative"):
            self._open(starting_balance=Decimal("-1"))

    def test_invalid_currency_rejected(self) -> None:
        with pytest.raises(ValidationFailed, match="ISO-4217"):
            self._open(base_currency="RUPEE")

    def test_cash_delta_and_equity_and_close(self) -> None:
        account = self._open()
        account.apply_cash_delta(Decimal("-2500"))
        assert account.cash_balance == Decimal("97500")
        account.set_equity(Decimal("98000"))
        assert account.equity == Decimal("98000")
        account.close()
        with pytest.raises(ConflictError, match="already closed"):
            account.close()

    def test_account_id_type(self) -> None:
        account = self._open()
        assert isinstance(account.id, UUID)
