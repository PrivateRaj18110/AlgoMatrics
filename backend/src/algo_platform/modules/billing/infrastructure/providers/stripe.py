"""Stripe adapter: Checkout Sessions and signed webhook verification.

Uses the REST API directly (form-encoded, Bearer secret key) so no vendor SDK
is required. https://docs.stripe.com/api/checkout/sessions/create
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx

from algo_platform.modules.billing.application.ports import (
    CheckoutSession,
    RefundResult,
    WebhookResult,
)
from algo_platform.modules.billing.domain.invoices import Invoice
from algo_platform.shared.domain.errors import ConflictError, ValidationFailed

_API_BASE = "https://api.stripe.com/v1"
_TIMEOUT = httpx.Timeout(20.0)
_SIGNATURE_TOLERANCE_SECONDS = 300


class StripeProvider:
    def __init__(self, *, secret_key: str, webhook_secret: str | None) -> None:
        self._secret_key = secret_key
        self._webhook_secret = webhook_secret

    @property
    def name(self) -> str:
        return "stripe"

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
    ) -> CheckoutSession:
        recurring = provider_price_ref is not None
        form: dict[str, str] = {
            "mode": "subscription" if recurring else "payment",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "customer_email": customer_email,
            "client_reference_id": str(invoice.id),
            "metadata[invoice_id]": str(invoice.id),
            "metadata[internal_subscription_id]": str(invoice.subscription_id),
            "line_items[0][quantity]": "1",
        }
        if recurring:
            assert provider_price_ref is not None
            form["line_items[0][price]"] = provider_price_ref
            form["subscription_data[metadata][invoice_id]"] = str(invoice.id)
            form["subscription_data[metadata][internal_subscription_id]"] = str(
                invoice.subscription_id
            )
            form["subscription_data[metadata][billing_cycle]"] = billing_cycle
        else:
            form["line_items[0][price_data][currency]"] = invoice.currency.lower()
            form["line_items[0][price_data][unit_amount]"] = str(int(invoice.total * 100))
            form["line_items[0][price_data][product_data][name]"] = (
                f"Algo Matrics {plan_name} ({invoice.number})"
            )
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                f"{_API_BASE}/checkout/sessions",
                data=form,
                headers={"Authorization": f"Bearer {self._secret_key}"},
            )
        if response.status_code >= 400:
            raise ConflictError(
                "payment provider rejected the checkout session",
                details={"provider": "stripe", "status": response.status_code},
            )
        session = response.json()
        return CheckoutSession(
            provider=self.name,
            checkout_id=str(session["id"]),
            checkout_url=str(session["url"]),
            payload={"session_id": str(session["id"])},
            recurring=recurring,
        )

    async def cancel_subscription(
        self, provider_subscription_id: str, *, at_period_end: bool
    ) -> None:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            if at_period_end:
                response = await client.post(
                    f"{_API_BASE}/subscriptions/{provider_subscription_id}",
                    data={"cancel_at_period_end": "true"},
                    headers={"Authorization": f"Bearer {self._secret_key}"},
                )
            else:
                response = await client.delete(
                    f"{_API_BASE}/subscriptions/{provider_subscription_id}",
                    headers={"Authorization": f"Bearer {self._secret_key}"},
                )
        if response.status_code >= 400:
            raise ConflictError(
                "payment provider could not cancel the subscription",
                details={"provider": "stripe", "status": response.status_code},
            )

    async def resume_subscription(self, provider_subscription_id: str) -> None:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                f"{_API_BASE}/subscriptions/{provider_subscription_id}",
                data={"cancel_at_period_end": "false"},
                headers={"Authorization": f"Bearer {self._secret_key}"},
            )
        if response.status_code >= 400:
            raise ConflictError(
                "payment provider could not resume the subscription",
                details={"provider": "stripe", "status": response.status_code},
            )

    async def refund_payment(
        self,
        provider_payment_id: str,
        *,
        amount: Decimal,
        currency: str,
        reason: str | None = None,
    ) -> RefundResult:
        # Stripe amounts are in the smallest currency unit (e.g. paise/cents).
        minor = int((amount * 100).to_integral_value())
        data = {"payment_intent": provider_payment_id, "amount": str(minor)}
        if reason in {"duplicate", "fraudulent", "requested_by_customer"}:
            data["reason"] = reason
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                f"{_API_BASE}/refunds",
                data=data,
                headers={"Authorization": f"Bearer {self._secret_key}"},
            )
        if response.status_code >= 400:
            raise ConflictError(
                "payment provider could not process the refund",
                details={"provider": "stripe", "status": response.status_code},
            )
        body = response.json()
        return RefundResult(
            provider_refund_id=str(body.get("id", "")),
            amount=amount,
            currency=currency.upper(),
            status=str(body.get("status", "pending")),
        )

    def verify_webhook(self, *, body: bytes, headers: Mapping[str, str]) -> WebhookResult:
        if not self._webhook_secret:
            raise ValidationFailed("stripe webhook secret is not configured")
        header = headers.get("stripe-signature", "")
        timestamp, signatures = _parse_signature_header(header)
        if timestamp is None or not signatures:
            raise ValidationFailed("stripe webhook signature header malformed")
        if abs(time.time() - timestamp) > _SIGNATURE_TOLERANCE_SECONDS:
            raise ValidationFailed("stripe webhook timestamp outside tolerance")
        signed_payload = f"{timestamp}.".encode() + body
        expected = hmac.new(
            self._webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256
        ).hexdigest()
        if not any(hmac.compare_digest(expected, sig) for sig in signatures):
            raise ValidationFailed("stripe webhook signature mismatch")

        event: dict[str, Any] = json.loads(body)
        event_id = str(event.get("id", ""))
        event_type = str(event.get("type", ""))
        obj: dict[str, Any] = event.get("data", {}).get("object", {})
        invoice_id_raw = obj.get("metadata", {}).get("invoice_id") or obj.get("client_reference_id")
        invoice_id = UUID(str(invoice_id_raw)) if invoice_id_raw else None
        amount_raw = obj.get("amount_total")
        if event_type.startswith("invoice."):
            amount_raw = obj.get("amount_paid", obj.get("amount_due"))
        amount = Decimal(str(amount_raw)) / 100 if amount_raw is not None else None
        currency = obj.get("currency")

        payload_hash = hashlib.sha256(body).hexdigest()
        if event_type == "checkout.session.completed" and obj.get("payment_status") == "paid":
            return WebhookResult(
                kind="payment_captured",
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                provider_payment_id=str(obj.get("payment_intent") or obj.get("id", "")),
                provider_order_id=str(obj.get("id", "")),
                provider_subscription_id=(
                    str(obj.get("subscription")) if obj.get("subscription") else None
                ),
                provider_customer_id=str(obj.get("customer")) if obj.get("customer") else None,
                invoice_id=invoice_id,
                amount=amount,
                currency=str(currency).upper() if currency else None,
                method="card",
            )
        if event_type == "invoice.paid":
            subscription_id = obj.get("subscription")
            line_period: dict[str, Any] = {}
            lines = obj.get("lines", {}).get("data", [])
            if lines:
                line_period = lines[0].get("period", {})
            return WebhookResult(
                kind="payment_captured",
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                provider_payment_id=str(obj.get("payment_intent") or obj.get("id", "")),
                provider_order_id=str(obj.get("id", "")),
                provider_subscription_id=str(subscription_id) if subscription_id else None,
                amount=amount,
                currency=str(currency).upper() if currency else None,
                method="recurring",
                period_start=line_period.get("start"),
                period_end=line_period.get("end"),
            )
        if event_type in {
            "checkout.session.async_payment_failed",
            "checkout.session.expired",
            "invoice.payment_failed",
        }:
            return WebhookResult(
                kind="payment_failed",
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                provider_payment_id=str(obj.get("payment_intent") or obj.get("id", "")),
                provider_order_id=str(obj.get("id", "")),
                provider_subscription_id=(
                    str(obj.get("subscription")) if obj.get("subscription") else None
                ),
                invoice_id=invoice_id,
                amount=amount,
                currency=str(currency).upper() if currency else None,
                error=event_type,
            )
        if event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
            status = str(obj.get("status", ""))
            items = obj.get("items", {}).get("data", [])
            price_ref = None
            if items:
                price_ref = str(items[0].get("price", {}).get("id", "")) or None
            return WebhookResult(
                kind=(
                    "subscription_cancelled"
                    if event_type == "customer.subscription.deleted"
                    else "subscription_updated"
                ),
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                provider_subscription_id=str(obj.get("id", "")),
                provider_customer_id=str(obj.get("customer", "")) or None,
                provider_price_ref=price_ref,
                provider_status=status,
                period_start=obj.get("current_period_start"),
                period_end=obj.get("current_period_end"),
                cancel_at_period_end=bool(obj.get("cancel_at_period_end", False)),
            )
        return WebhookResult(
            kind="ignored",
            event_id=event_id,
            event_type=event_type,
            payload_hash=payload_hash,
        )


def _parse_signature_header(header: str) -> tuple[int | None, list[str]]:
    timestamp: int | None = None
    signatures: list[str] = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t" and value.isdigit():
            timestamp = int(value)
        elif key == "v1" and value:
            signatures.append(value)
    return timestamp, signatures
