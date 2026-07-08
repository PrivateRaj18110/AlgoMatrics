"""Contract tests: payment-provider webhook signature verification and parsing."""

import hashlib
import hmac
import json
import time
from decimal import Decimal
from uuid import uuid4

import pytest

from algo_platform.modules.billing.infrastructure.providers.razorpay import (
    RazorpayProvider,
)
from algo_platform.modules.billing.infrastructure.providers.stripe import StripeProvider
from algo_platform.shared.domain.errors import ValidationFailed

pytestmark = pytest.mark.contract

RAZORPAY_SECRET = "rzp-webhook-secret"
STRIPE_SECRET = "whsec_test"


def razorpay_provider() -> RazorpayProvider:
    return RazorpayProvider(
        key_id="rzp_test_key", key_secret="rzp_test_secret", webhook_secret=RAZORPAY_SECRET
    )


def stripe_provider() -> StripeProvider:
    return StripeProvider(secret_key="sk_test_key", webhook_secret=STRIPE_SECRET)


class TestRazorpayWebhook:
    def sign(self, body: bytes) -> str:
        return hmac.new(RAZORPAY_SECRET.encode(), body, hashlib.sha256).hexdigest()

    def test_payment_captured_parsed(self) -> None:
        body = json.dumps(
            {
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": "pay_123",
                            "order_id": "order_456",
                            "amount": 249900,
                            "currency": "INR",
                            "method": "upi",
                        }
                    }
                },
            }
        ).encode()
        result = razorpay_provider().verify_webhook(
            body=body, headers={"x-razorpay-signature": self.sign(body)}
        )
        assert result.kind == "payment_captured"
        assert result.provider_payment_id == "pay_123"
        assert result.provider_order_id == "order_456"
        assert result.amount == Decimal("2499")
        assert result.method == "upi"

    def test_tampered_signature_rejected(self) -> None:
        body = b'{"event": "payment.captured"}'
        with pytest.raises(ValidationFailed, match="signature mismatch"):
            razorpay_provider().verify_webhook(
                body=body, headers={"x-razorpay-signature": "deadbeef"}
            )

    def test_unknown_event_ignored(self) -> None:
        body = json.dumps({"event": "refund.created", "payload": {}}).encode()
        result = razorpay_provider().verify_webhook(
            body=body, headers={"x-razorpay-signature": self.sign(body)}
        )
        assert result.kind == "ignored"

    def test_payment_signature_verification(self) -> None:
        provider = razorpay_provider()
        message = b"order_1|pay_1"
        signature = hmac.new(b"rzp_test_secret", message, hashlib.sha256).hexdigest()
        assert provider.verify_payment_signature(
            order_id="order_1", payment_id="pay_1", signature=signature
        )
        assert not provider.verify_payment_signature(
            order_id="order_1", payment_id="pay_1", signature="bad"
        )

    def test_subscription_activation_parsed(self) -> None:
        body = json.dumps(
            {
                "event": "subscription.activated",
                "payload": {
                    "subscription": {
                        "entity": {
                            "id": "sub_123",
                            "plan_id": "plan_123",
                            "customer_id": "cust_123",
                            "status": "active",
                            "current_start": 1_700_000_000,
                            "current_end": 1_702_592_000,
                        }
                    }
                },
            }
        ).encode()
        result = razorpay_provider().verify_webhook(
            body=body,
            headers={
                "x-razorpay-signature": self.sign(body),
                "x-razorpay-event-id": "event_123",
            },
        )
        assert result.kind == "subscription_updated"
        assert result.event_id == "event_123"
        assert result.provider_subscription_id == "sub_123"
        assert result.provider_price_ref == "plan_123"


class TestStripeWebhook:
    def sign_header(self, body: bytes, *, timestamp: int | None = None) -> str:
        ts = timestamp if timestamp is not None else int(time.time())
        payload = f"{ts}.".encode() + body
        signature = hmac.new(STRIPE_SECRET.encode(), payload, hashlib.sha256).hexdigest()
        return f"t={ts},v1={signature}"

    def test_checkout_completed_parsed(self) -> None:
        invoice_id = uuid4()
        body = json.dumps(
            {
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": "cs_test_1",
                        "payment_intent": "pi_1",
                        "payment_status": "paid",
                        "amount_total": 249900,
                        "currency": "inr",
                        "metadata": {"invoice_id": str(invoice_id)},
                    }
                },
            }
        ).encode()
        result = stripe_provider().verify_webhook(
            body=body, headers={"stripe-signature": self.sign_header(body)}
        )
        assert result.kind == "payment_captured"
        assert result.invoice_id == invoice_id
        assert result.provider_payment_id == "pi_1"
        assert result.amount == Decimal("2499")
        assert result.currency == "INR"

    def test_stale_timestamp_rejected(self) -> None:
        body = b"{}"
        stale = int(time.time()) - 3600
        with pytest.raises(ValidationFailed, match="tolerance"):
            stripe_provider().verify_webhook(
                body=body,
                headers={"stripe-signature": self.sign_header(body, timestamp=stale)},
            )

    def test_bad_signature_rejected(self) -> None:
        body = b"{}"
        ts = int(time.time())
        with pytest.raises(ValidationFailed, match="signature mismatch"):
            stripe_provider().verify_webhook(
                body=body, headers={"stripe-signature": f"t={ts},v1=deadbeef"}
            )

    def test_subscription_update_parsed(self) -> None:
        body = json.dumps(
            {
                "id": "evt_subscription",
                "type": "customer.subscription.updated",
                "data": {
                    "object": {
                        "id": "sub_123",
                        "customer": "cus_123",
                        "status": "active",
                        "current_period_start": 1_700_000_000,
                        "current_period_end": 1_702_592_000,
                        "cancel_at_period_end": False,
                        "items": {"data": [{"price": {"id": "price_pro_monthly"}}]},
                    }
                },
            }
        ).encode()
        result = stripe_provider().verify_webhook(
            body=body, headers={"stripe-signature": self.sign_header(body)}
        )
        assert result.kind == "subscription_updated"
        assert result.event_id == "evt_subscription"
        assert result.provider_subscription_id == "sub_123"
        assert result.provider_price_ref == "price_pro_monthly"
