"""Payment-provider port. New gateways plug in behind this interface."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, Protocol
from uuid import UUID

from algo_platform.modules.billing.domain.invoices import Invoice


@dataclass(frozen=True, slots=True)
class CheckoutSession:
    provider: str
    checkout_id: str
    checkout_url: str | None
    payload: dict[str, Any]
    recurring: bool = False


@dataclass(frozen=True, slots=True)
class WebhookResult:
    kind: Literal[
        "payment_captured",
        "payment_failed",
        "subscription_updated",
        "subscription_cancelled",
        "ignored",
    ]
    event_id: str = ""
    event_type: str = ""
    payload_hash: str = ""
    provider_payment_id: str = ""
    provider_order_id: str | None = None
    provider_subscription_id: str | None = None
    provider_customer_id: str | None = None
    provider_price_ref: str | None = None
    provider_status: str | None = None
    invoice_id: UUID | None = None
    amount: Decimal | None = None
    currency: str | None = None
    method: str | None = None
    error: str | None = None
    period_start: int | None = None
    period_end: int | None = None
    cancel_at_period_end: bool | None = None


class PaymentProvider(Protocol):
    """Command-side payment gateway contract.

    ``create_checkout`` performs a real API call against the provider.
    ``verify_webhook`` authenticates and normalizes an incoming webhook body.
    """

    @property
    def name(self) -> str: ...

    async def create_checkout(
        self,
        *,
        invoice: Invoice,
        plan_name: str,
        customer_email: str,
        success_url: str,
        cancel_url: str,
        provider_price_ref: str | None,
        billing_cycle: str,
    ) -> CheckoutSession: ...

    async def cancel_subscription(
        self, provider_subscription_id: str, *, at_period_end: bool
    ) -> None: ...

    async def resume_subscription(self, provider_subscription_id: str) -> None: ...

    def verify_webhook(self, *, body: bytes, headers: Mapping[str, str]) -> WebhookResult: ...
