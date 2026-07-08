import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";

import {
  Badge,
  Button,
  Card,
  EmptyState,
  Input,
  PageHeader,
  SkeletonRows,
  Table,
  Tabs,
  Td,
  statusColor,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import {
  useCheckout,
  useInvoices,
  usePayments,
  usePlans,
  usePreviewCoupon,
  useSubscription,
  useUsage,
} from "@/lib/hooks";
import { dateOnly, dateTime, money } from "@/lib/format";
import { toastError, toastSuccess } from "@/stores/toast";
import type { CheckoutResponse, Plan } from "@/types/api";

declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => { open: () => void };
  }
}

export function SubscriptionPage() {
  const [params, setParams] = useSearchParams();
  const [tab, setTab] = useState("plans");
  const { data: subscription } = useSubscription();
  const client = useQueryClient();

  useEffect(() => {
    const payment = params.get("payment");
    if (payment === "success") {
      toastSuccess("Payment received", "Your subscription is being activated.");
      client.invalidateQueries({ queryKey: ["subscription"] });
      client.invalidateQueries({ queryKey: ["invoices"] });
      setParams({}, { replace: true });
    } else if (payment === "cancelled") {
      toastError("Checkout cancelled");
      setParams({}, { replace: true });
    }
  }, [params, setParams, client]);

  return (
    <div>
      <PageHeader
        title="Subscription"
        description="Manage your plan, billing, and payment history"
        actions={
          subscription && (
            <Badge color={statusColor(subscription.status)}>
              {subscription.plan_name} · {subscription.status}
            </Badge>
          )
        }
      />

      <div className="mb-4">
        <Tabs
          tabs={[
            { key: "plans", label: "Plans" },
            { key: "usage", label: "Usage" },
            { key: "invoices", label: "Invoices" },
            { key: "payments", label: "Payments" },
          ]}
          active={tab}
          onChange={setTab}
        />
      </div>

      {tab === "plans" && <PlansTab />}
      {tab === "usage" && <UsageTab />}
      {tab === "invoices" && <InvoicesTab />}
      {tab === "payments" && <PaymentsTab />}
    </div>
  );
}

function PlansTab() {
  const { data: plans } = usePlans();
  const { data: subscription } = useSubscription();
  const [cycle, setCycle] = useState<"monthly" | "yearly">("monthly");
  const [coupon, setCoupon] = useState("");
  const checkout = useCheckout();
  const previewCoupon = usePreviewCoupon();
  const client = useQueryClient();
  const [couponResult, setCouponResult] = useState<string | null>(null);

  async function handleCheckout(plan: Plan, useTrial = false) {
    try {
      const result = await checkout.mutateAsync({
        plan_code: plan.code,
        cycle,
        coupon_code: coupon || null,
        use_trial: useTrial,
      });
      handleCheckoutResult(result, client);
    } catch (error) {
      toastError("Checkout failed", error instanceof ApiError ? error.detail : undefined);
    }
  }

  async function checkCoupon(planCode: string) {
    if (!coupon) return;
    try {
      const preview = await previewCoupon.mutateAsync({ code: coupon, plan_code: planCode, cycle });
      setCouponResult(`Discount: ${money(preview.discount, preview.currency)} → total ${money(preview.total, preview.currency)}`);
    } catch (error) {
      setCouponResult(error instanceof ApiError ? error.detail : "Invalid coupon");
    }
  }

  async function cancel() {
    try {
      await api("/billing/cancel", { method: "POST" });
      client.invalidateQueries({ queryKey: ["subscription"] });
      toastSuccess("Cancellation scheduled");
    } catch (error) {
      toastError("Cancel failed", error instanceof ApiError ? error.detail : undefined);
    }
  }

  async function resume() {
    try {
      await api("/billing/resume", { method: "POST" });
      client.invalidateQueries({ queryKey: ["subscription"] });
      toastSuccess("Subscription resumed");
    } catch (error) {
      toastError("Resume failed", error instanceof ApiError ? error.detail : undefined);
    }
  }

  return (
    <div>
      {subscription && (
        <Card className="mb-6" title="Current subscription">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-lg font-semibold">{subscription.plan_name}</p>
              <p className="text-sm text-slate-500">
                {subscription.status === "trialing"
                  ? `Trial ends ${dateOnly(subscription.trial_end)}`
                  : `Renews ${dateOnly(subscription.current_period_end)}`}
              </p>
            </div>
            <div className="flex gap-2">
              {subscription.cancel_at_period_end ? (
                <Button size="sm" variant="secondary" onClick={resume}>
                  Resume subscription
                </Button>
              ) : (
                subscription.plan_code !== "free" && (
                  <Button size="sm" variant="ghost" onClick={cancel}>
                    Cancel at period end
                  </Button>
                )
              )}
            </div>
          </div>
          {subscription.cancel_at_period_end && (
            <Badge color="amber" className="mt-3">
              Scheduled to cancel on {dateOnly(subscription.current_period_end)}
            </Badge>
          )}
        </Card>
      )}

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-1 dark:border-surface-800 dark:bg-surface-900">
          {(["monthly", "yearly"] as const).map((option) => (
            <button
              key={option}
              onClick={() => setCycle(option)}
              className={
                cycle === option
                  ? "rounded-md bg-white px-4 py-1.5 text-sm font-medium shadow-sm dark:bg-surface-800"
                  : "px-4 py-1.5 text-sm text-slate-500"
              }
            >
              {option === "monthly" ? "Monthly" : "Yearly"}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <Input
            placeholder="Coupon code"
            value={coupon}
            onChange={(event) => {
              setCoupon(event.target.value.toUpperCase());
              setCouponResult(null);
            }}
            className="w-40"
          />
          {couponResult && <span className="text-xs text-slate-500">{couponResult}</span>}
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        {(plans ?? []).map((plan) => {
          const current = subscription?.plan_code === plan.code;
          return (
            <Card
              key={plan.id}
              className={plan.code === "pro" ? "border-accent-500" : undefined}
              title={plan.name}
            >
              <p className="text-2xl font-bold tabular-nums">
                {money(cycle === "monthly" ? plan.price_monthly : plan.price_yearly, plan.currency)}
                <span className="text-sm font-normal text-slate-400">
                  /{cycle === "monthly" ? "mo" : "yr"}
                </span>
              </p>
              <ul className="mt-3 space-y-1.5 text-sm">
                {plan.features.slice(0, 5).map((feature) => (
                  <li key={feature} className="flex gap-2">
                    <span className="text-profit-500">✓</span>
                    <span className="text-slate-600 dark:text-slate-300">{feature}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-4 space-y-2">
                {current ? (
                  <Badge color="green">Current plan</Badge>
                ) : (
                  <>
                    <Button
                      className="w-full"
                      variant={plan.code === "pro" ? "primary" : "secondary"}
                      loading={checkout.isPending}
                      onClick={() => handleCheckout(plan)}
                    >
                      {plan.code === "free" ? "Switch to Free" : "Subscribe"}
                    </Button>
                    {plan.trial_days > 0 && subscription?.trial_available && (
                      <Button
                        className="w-full"
                        size="sm"
                        variant="ghost"
                        onClick={() => handleCheckout(plan, true)}
                      >
                        Start {plan.trial_days}-day trial
                      </Button>
                    )}
                    {coupon && plan.code !== "free" && (
                      <button
                        className="w-full text-xs text-accent-500 hover:underline"
                        onClick={() => checkCoupon(plan.code)}
                      >
                        Preview coupon
                      </button>
                    )}
                  </>
                )}
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function handleCheckoutResult(result: CheckoutResponse, client: ReturnType<typeof useQueryClient>) {
  if (result.kind === "checkout" && result.checkout_url) {
    window.location.href = result.checkout_url;
    return;
  }
  if (result.kind === "checkout" && result.provider === "razorpay" && window.Razorpay) {
    const payload = result.payload as Record<string, unknown>;
    const recurring = typeof payload.subscription_id === "string";
    const razorpay = new window.Razorpay({
      key: payload.key_id,
      order_id: payload.order_id,
      subscription_id: payload.subscription_id,
      amount: payload.amount,
      currency: payload.currency,
      name: payload.name,
      description: payload.description,
      prefill: { email: payload.prefill_email },
      handler: async (response: Record<string, string>) => {
        if (recurring) {
          client.invalidateQueries({ queryKey: ["subscription"] });
          toastSuccess("Subscription authorized; activation is being confirmed");
          return;
        }
        try {
          await api("/billing/checkout/razorpay/confirm", {
            method: "POST",
            body: {
              invoice_id: result.invoice_id,
              order_id: response.razorpay_order_id,
              payment_id: response.razorpay_payment_id,
              signature: response.razorpay_signature,
            },
          });
          client.invalidateQueries({ queryKey: ["subscription"] });
          toastSuccess("Payment confirmed");
        } catch (error) {
          toastError("Confirmation failed", error instanceof ApiError ? error.detail : undefined);
        }
      },
    });
    razorpay.open();
    return;
  }
  // trial_started / activated / scheduled
  client.invalidateQueries({ queryKey: ["subscription"] });
  toastSuccess(result.message);
}

function UsageTab() {
  const { data: usage } = useUsage();
  if (!usage) return <Card><SkeletonRows rows={4} cols={2} /></Card>;
  return (
    <Card title="Plan usage (last 30 days)">
      <dl className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm sm:grid-cols-3">
        {Object.entries(usage.limits).map(([key, limit]) => (
          <div key={key}>
            <dt className="text-xs text-slate-500">{key.replace(/_/g, " ")}</dt>
            <dd className="mt-0.5 font-medium tabular-nums">
              {usage.usage[key] ?? 0}
              <span className="text-slate-400"> / {limit === -1 ? "∞" : String(limit)}</span>
            </dd>
          </div>
        ))}
        <div>
          <dt className="text-xs text-slate-500">orders today</dt>
          <dd className="mt-0.5 font-medium tabular-nums">{usage.usage.orders_placed_today ?? 0}</dd>
        </div>
      </dl>
    </Card>
  );
}

function InvoicesTab() {
  const { data: invoices, isLoading } = useInvoices();
  return (
    <Card>
      {isLoading ? (
        <SkeletonRows rows={5} cols={5} />
      ) : !invoices || invoices.length === 0 ? (
        <EmptyState title="No invoices yet" />
      ) : (
        <Table headers={["Invoice", "Status", "Total", "Period", "Issued"]}>
          {invoices.map((invoice) => (
            <tr key={invoice.id}>
              <Td className="font-mono text-xs">{invoice.number}</Td>
              <Td>
                <Badge color={statusColor(invoice.status)}>{invoice.status}</Badge>
              </Td>
              <Td className="tabular-nums">{money(invoice.total, invoice.currency)}</Td>
              <Td className="text-xs text-slate-400">
                {dateOnly(invoice.period_start)} – {dateOnly(invoice.period_end)}
              </Td>
              <Td className="text-xs text-slate-400">{dateTime(invoice.issued_at)}</Td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}

function PaymentsTab() {
  const { data: payments, isLoading } = usePayments();
  return (
    <Card>
      {isLoading ? (
        <SkeletonRows rows={5} cols={5} />
      ) : !payments || payments.length === 0 ? (
        <EmptyState title="No payments yet" />
      ) : (
        <Table headers={["Provider", "Amount", "Method", "Status", "When"]}>
          {payments.map((payment) => (
            <tr key={payment.id}>
              <Td className="capitalize">{payment.provider}</Td>
              <Td className="tabular-nums">{money(payment.amount, payment.currency)}</Td>
              <Td className="text-slate-500">{payment.method ?? "—"}</Td>
              <Td>
                <Badge color={statusColor(payment.status)}>{payment.status}</Badge>
              </Td>
              <Td className="text-xs text-slate-400">{dateTime(payment.created_at)}</Td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}
