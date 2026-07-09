# Payments & billing (Phase 9)

The billing system spans Stripe and Razorpay behind one `PaymentProvider` port,
with recurring subscriptions, coupons, trials, usage metering, tax (GST), and
refunds.

## Capabilities

| Area | Where |
|---|---|
| Providers | `infrastructure/providers/{stripe,razorpay}.py` behind `application/ports.py` |
| Subscriptions | `domain/subscriptions.py` — free/trial/paid, recurring renewal, cancel/resume |
| Coupons | `domain/coupons.py` — percent/amount off, redemption limits, plan/currency scoping |
| Trials | `Plan.trial_days` + `Subscription.start_trial` |
| Invoices | `domain/invoices.py` — subtotal, discount, **tax**, total, line items |
| Tax (GST) | `domain/tax.py` — see below |
| Usage billing | `record_usage` / `usage_summary` metering |
| Webhooks | replay-safe receipts (`billing_webhook_events`), signature verified |
| Refunds | see below |

## Tax (GST)

`compute_tax(taxable, rate_percent)` applies the configured rate to the
post-discount amount and rounds to cents; the invoice stores `tax` and
`tax_rate` and folds tax into `total`. `gst_breakdown` splits the tax into
CGST/SGST (intra-state) or IGST (inter-state) for display; the halves always sum
back to the total under rounding.

`GST_RATE_PERCENT` (default `18`) is applied to **INR** invoices at checkout and
at recurring renewal; other currencies are untaxed. Set it to `0` to disable.

## Refunds

```
POST /api/v1/admin/payments/{payment_id}/refund
{ "organization_id": "...", "amount": "500.00", "reason": "requested_by_customer" }
```

- Platform-admin only; every refund is written to the immutable audit log.
- Full or partial: `Payment.refunded_amount` accumulates and the payment moves to
  `refunded` once fully refunded. A refund can never exceed the refundable
  balance (validated before the provider call).
- The provider refund runs first (`RefundResult`), then the domain state is
  applied and persisted.

## Rollback

- **Tax:** `GST_RATE_PERCENT=0` stops applying tax at runtime; `alembic downgrade
  0007` drops the invoice tax columns.
- **Refunds:** `alembic downgrade 0008` drops `payments.refunded_amount`.
- The work is isolated to the `phase-9-payments` branch; all changes are additive
  (new columns default to 0, new port method, new endpoint), so `git revert` is
  safe.
