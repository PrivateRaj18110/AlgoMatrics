"""Razorpay adapter: order creation, payment-signature and webhook verification.

Uses the public Orders API (https://razorpay.com/docs/api/orders/). The
browser opens Razorpay Checkout with the returned ``order_id``; the frontend
then posts the ``payment_id``/``signature`` pair back for verification, and
Razorpay also delivers a signed webhook.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import httpx

from algo_platform.modules.billing.application.ports import (
    CheckoutSession,
    RefundResult,
    WebhookResult,
)
from algo_platform.modules.billing.domain.invoices import Invoice
from algo_platform.shared.domain.errors import ConflictError, ValidationFailed

_API_BASE = "https://api.razorpay.com/v1"
_TIMEOUT = httpx.Timeout(20.0)


class RazorpayProvider:
    def __init__(self, *, key_id: str, key_secret: str, webhook_secret: str | None) -> None:
        self._key_id = key_id
        self._key_secret = key_secret
        self._webhook_secret = webhook_secret

    @property
    def name(self) -> str:
        return "razorpay"

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
        if provider_price_ref:
            total_count = 120 if billing_cycle == "monthly" else 10
            async with httpx.AsyncClient(
                timeout=_TIMEOUT, auth=(self._key_id, self._key_secret)
            ) as client:
                response = await client.post(
                    f"{_API_BASE}/subscriptions",
                    json={
                        "plan_id": provider_price_ref,
                        "total_count": total_count,
                        "quantity": 1,
                        "customer_notify": True,
                        "notes": {
                            "invoice_id": str(invoice.id),
                            "internal_subscription_id": str(invoice.subscription_id),
                        },
                    },
                )
            if response.status_code >= 400:
                raise ConflictError(
                    "payment provider rejected the subscription",
                    details={"provider": "razorpay", "status": response.status_code},
                )
            subscription = response.json()
            subscription_id = str(subscription["id"])
            return CheckoutSession(
                provider=self.name,
                checkout_id=subscription_id,
                checkout_url=(
                    str(subscription["short_url"]) if subscription.get("short_url") else None
                ),
                payload={
                    "subscription_id": subscription_id,
                    "key_id": self._key_id,
                    "name": "Algo Matrics",
                    "description": plan_name,
                    "prefill_email": customer_email,
                },
                recurring=True,
            )
        amount_minor = int(invoice.total * 100)
        async with httpx.AsyncClient(
            timeout=_TIMEOUT, auth=(self._key_id, self._key_secret)
        ) as client:
            response = await client.post(
                f"{_API_BASE}/orders",
                json={
                    "amount": amount_minor,
                    "currency": invoice.currency,
                    "receipt": invoice.number,
                    "notes": {"invoice_id": str(invoice.id)},
                },
            )
        if response.status_code >= 400:
            raise ConflictError(
                "payment provider rejected the order",
                details={"provider": "razorpay", "status": response.status_code},
            )
        order = response.json()
        order_id = str(order["id"])
        return CheckoutSession(
            provider=self.name,
            checkout_id=order_id,
            checkout_url=None,
            payload={
                "order_id": order_id,
                "key_id": self._key_id,
                "amount": amount_minor,
                "currency": invoice.currency,
                "name": "Algo Matrics",
                "description": plan_name,
                "prefill_email": customer_email,
            },
            recurring=False,
        )

    async def cancel_subscription(
        self, provider_subscription_id: str, *, at_period_end: bool
    ) -> None:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT, auth=(self._key_id, self._key_secret)
        ) as client:
            response = await client.post(
                f"{_API_BASE}/subscriptions/{provider_subscription_id}/cancel",
                json={"cancel_at_cycle_end": 1 if at_period_end else 0},
            )
        if response.status_code >= 400:
            raise ConflictError(
                "payment provider could not cancel the subscription",
                details={"provider": "razorpay", "status": response.status_code},
            )

    async def resume_subscription(self, provider_subscription_id: str) -> None:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT, auth=(self._key_id, self._key_secret)
        ) as client:
            response = await client.post(
                f"{_API_BASE}/subscriptions/{provider_subscription_id}/resume"
            )
        if response.status_code >= 400:
            raise ConflictError(
                "payment provider could not resume the subscription",
                details={"provider": "razorpay", "status": response.status_code},
            )

    async def refund_payment(
        self,
        provider_payment_id: str,
        *,
        amount: Decimal,
        currency: str,
        reason: str | None = None,
    ) -> RefundResult:
        # Razorpay amounts are in the smallest currency unit (paise).
        minor = int((amount * 100).to_integral_value())
        payload: dict[str, Any] = {"amount": minor}
        if reason:
            payload["notes"] = {"reason": reason[:255]}
        async with httpx.AsyncClient(
            timeout=_TIMEOUT, auth=(self._key_id, self._key_secret)
        ) as client:
            response = await client.post(
                f"{_API_BASE}/payments/{provider_payment_id}/refund", json=payload
            )
        if response.status_code >= 400:
            raise ConflictError(
                "payment provider could not process the refund",
                details={"provider": "razorpay", "status": response.status_code},
            )
        body = response.json()
        return RefundResult(
            provider_refund_id=str(body.get("id", "")),
            amount=amount,
            currency=currency.upper(),
            status=str(body.get("status", "processed")),
        )

    def verify_payment_signature(self, *, order_id: str, payment_id: str, signature: str) -> bool:
        message = f"{order_id}|{payment_id}".encode()
        expected = hmac.new(self._key_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def verify_webhook(self, *, body: bytes, headers: Mapping[str, str]) -> WebhookResult:
        if not self._webhook_secret:
            raise ValidationFailed("razorpay webhook secret is not configured")
        signature = headers.get("x-razorpay-signature", "")
        expected = hmac.new(self._webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if not signature or not hmac.compare_digest(expected, signature):
            raise ValidationFailed("razorpay webhook signature mismatch")

        event: dict[str, Any] = json.loads(body)
        event_id = headers.get("x-razorpay-event-id", "") or hashlib.sha256(body).hexdigest()
        event_type = str(event.get("event", ""))
        payment_entity: dict[str, Any] = (
            event.get("payload", {}).get("payment", {}).get("entity", {})
        )
        payment_id = str(payment_entity.get("id", ""))
        order_id = payment_entity.get("order_id")
        amount_raw = payment_entity.get("amount")
        amount = Decimal(str(amount_raw)) / 100 if amount_raw is not None else None
        currency = payment_entity.get("currency")

        subscription_entity: dict[str, Any] = (
            event.get("payload", {}).get("subscription", {}).get("entity", {})
        )
        subscription_id = subscription_entity.get("id") or payment_entity.get("subscription_id")
        payload_hash = hashlib.sha256(body).hexdigest()
        if event_type in {"payment.captured", "subscription.charged"}:
            return WebhookResult(
                kind="payment_captured",
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                provider_payment_id=payment_id,
                provider_order_id=str(order_id) if order_id else None,
                provider_subscription_id=str(subscription_id) if subscription_id else None,
                amount=amount,
                currency=str(currency) if currency else None,
                method=str(payment_entity.get("method")) if payment_entity.get("method") else None,
            )
        if event_type == "payment.failed":
            error = payment_entity.get("error_description")
            return WebhookResult(
                kind="payment_failed",
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                provider_payment_id=payment_id,
                provider_order_id=str(order_id) if order_id else None,
                amount=amount,
                currency=str(currency) if currency else None,
                error=str(error) if error else None,
            )
        if event_type in {
            "subscription.activated",
            "subscription.resumed",
            "subscription.paused",
            "subscription.pending",
            "subscription.halted",
            "subscription.cancelled",
            "subscription.completed",
        }:
            status = str(subscription_entity.get("status", ""))
            return WebhookResult(
                kind=(
                    "subscription_cancelled"
                    if event_type in {"subscription.cancelled", "subscription.completed"}
                    else "subscription_updated"
                ),
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                provider_subscription_id=str(subscription_id) if subscription_id else None,
                provider_customer_id=(
                    str(subscription_entity.get("customer_id"))
                    if subscription_entity.get("customer_id")
                    else None
                ),
                provider_price_ref=(
                    str(subscription_entity.get("plan_id"))
                    if subscription_entity.get("plan_id")
                    else None
                ),
                provider_status=status,
                period_start=subscription_entity.get("current_start"),
                period_end=subscription_entity.get("current_end"),
            )
        return WebhookResult(
            kind="ignored",
            event_id=event_id,
            event_type=event_type,
            payload_hash=payload_hash,
        )
