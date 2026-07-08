import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router";

import {
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  SkeletonRows,
  StatCard,
  Table,
  Tabs,
  Td,
  statusColor,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import {
  useAdminCoupons,
  useAdminOrganizations,
  useAdminPlans,
  useAdminUsers,
  useAdminVenueInstruments,
  useBrokerCatalog,
  useBrokerMonitor,
  useInstruments,
  useSystemHealth,
} from "@/lib/hooks";
import { dateOnly, dateTime, money } from "@/lib/format";
import { toastError, toastSuccess } from "@/stores/toast";
import type { Plan } from "@/types/api";

const SECTIONS = [
  { key: "health", label: "System Health" },
  { key: "users", label: "Users" },
  { key: "organizations", label: "Organizations" },
  { key: "plans", label: "Plans" },
  { key: "coupons", label: "Coupons" },
  { key: "venue-instruments", label: "Venue Instruments" },
  { key: "grants", label: "Grants" },
];

export function AdminPage() {
  const { section = "health" } = useParams();
  const navigate = useNavigate();

  return (
    <div>
      <PageHeader title="Platform Admin" description="Cross-tenant administration" />
      <div className="mb-6">
        <Tabs tabs={SECTIONS} active={section} onChange={(key) => navigate(`/app/admin/${key}`)} />
      </div>
      {section === "health" && <HealthSection />}
      {section === "users" && <UsersSection />}
      {section === "organizations" && <OrganizationsSection />}
      {section === "plans" && <PlansSection />}
      {section === "coupons" && <CouponsSection />}
      {section === "venue-instruments" && <VenueInstrumentsSection />}
      {section === "grants" && <GrantsSection />}
    </div>
  );
}

function VenueInstrumentsSection() {
  const { data: mappings, isLoading } = useAdminVenueInstruments();
  const { data: brokers } = useBrokerCatalog();
  const { data: instruments } = useInstruments();
  const client = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);

  const brokerNames = new Map((brokers ?? []).map((broker) => [broker.id, broker.name]));

  async function toggle(mappingId: string, active: boolean) {
    try {
      await api(`/admin/venue-instruments/${mappingId}`, {
        method: "PATCH",
        skipOrg: true,
        body: { is_active: !active },
      });
      client.invalidateQueries({ queryKey: ["admin-venue-instruments"] });
      toastSuccess(active ? "Mapping disabled" : "Mapping enabled");
    } catch (error) {
      toastError("Mapping update failed", error instanceof ApiError ? error.detail : undefined);
    }
  }

  return (
    <Card
      title="Venue instrument mappings"
      actions={
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          Add mapping
        </Button>
      }
    >
      {isLoading ? (
        <SkeletonRows rows={5} cols={7} />
      ) : !mappings || mappings.length === 0 ? (
        <EmptyState
          title="No venue mappings"
          body="Live routing stays blocked until canonical instruments are mapped to broker symbols."
        />
      ) : (
        <Table headers={["Broker", "Canonical", "Venue", "Exchange", "Token", "Lot", "Status", ""]}>
          {mappings.map((mapping) => (
            <tr key={mapping.id}>
              <Td>{brokerNames.get(mapping.broker_id) ?? mapping.broker_id.slice(0, 8)}</Td>
              <Td className="font-medium">{mapping.canonical_symbol}</Td>
              <Td className="font-mono text-xs">{mapping.venue_symbol}</Td>
              <Td>{mapping.exchange}</Td>
              <Td className="max-w-36 truncate font-mono text-xs">
                {mapping.instrument_token ?? "—"}
              </Td>
              <Td className="tabular-nums">{mapping.lot_size}</Td>
              <Td>
                <Badge color={mapping.is_active ? "green" : "slate"}>
                  {mapping.is_active ? "active" : "disabled"}
                </Badge>
              </Td>
              <Td>
                <Button size="sm" variant="ghost" onClick={() => toggle(mapping.id, mapping.is_active)}>
                  {mapping.is_active ? "Disable" : "Enable"}
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      )}
      {createOpen && (
        <CreateVenueMappingModal
          brokers={brokers ?? []}
          instruments={instruments ?? []}
          onClose={() => setCreateOpen(false)}
          onCreated={() => {
            setCreateOpen(false);
            client.invalidateQueries({ queryKey: ["admin-venue-instruments"] });
          }}
        />
      )}
    </Card>
  );
}

function CreateVenueMappingModal({
  brokers,
  instruments,
  onClose,
  onCreated,
}: {
  brokers: import("@/types/api").BrokerCatalogEntry[];
  instruments: import("@/types/api").Instrument[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const liveBrokers = brokers.filter((broker) => broker.supports_live);
  const [brokerId, setBrokerId] = useState(liveBrokers[0]?.id ?? "");
  const [instrumentId, setInstrumentId] = useState(instruments[0]?.id ?? "");
  const [venueSymbol, setVenueSymbol] = useState(instruments[0]?.symbol ?? "");
  const [exchange, setExchange] = useState(instruments[0]?.exchange ?? "");
  const [instrumentToken, setInstrumentToken] = useState("");
  const [tickSize, setTickSize] = useState(instruments[0]?.tick_size ?? "");
  const [lotSize, setLotSize] = useState(instruments[0]?.lot_size ?? "");
  const [multiplier, setMultiplier] = useState("1");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function selectInstrument(id: string) {
    setInstrumentId(id);
    const instrument = instruments.find((candidate) => candidate.id === id);
    if (instrument) {
      setVenueSymbol(instrument.symbol);
      setExchange(instrument.exchange);
      setTickSize(instrument.tick_size);
      setLotSize(instrument.lot_size);
    }
  }

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      await api("/admin/venue-instruments", {
        method: "POST",
        skipOrg: true,
        body: {
          broker_id: brokerId,
          instrument_id: instrumentId,
          venue_symbol: venueSymbol,
          exchange,
          instrument_token: instrumentToken || null,
          tick_size: tickSize,
          lot_size: lotSize,
          contract_multiplier: multiplier,
          venue_metadata: {},
        },
      });
      toastSuccess("Venue mapping created");
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to create mapping");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Add venue instrument mapping" wide>
      <div className="space-y-4">
        {error && (
          <div className="rounded-lg border border-loss-500/40 bg-loss-500/10 px-3 py-2 text-sm text-loss-600 dark:text-loss-400">
            {error}
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Broker" required>
            <Select value={brokerId} onChange={(event) => setBrokerId(event.target.value)}>
              {liveBrokers.map((broker) => (
                <option key={broker.id} value={broker.id}>
                  {broker.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Canonical instrument" required>
            <Select value={instrumentId} onChange={(event) => selectInstrument(event.target.value)}>
              {instruments.map((instrument) => (
                <option key={instrument.id} value={instrument.id}>
                  {instrument.symbol} — {instrument.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Venue symbol" required>
            <Input value={venueSymbol} onChange={(event) => setVenueSymbol(event.target.value)} />
          </Field>
          <Field label="Exchange" required>
            <Input value={exchange} onChange={(event) => setExchange(event.target.value)} />
          </Field>
          <Field label="Instrument token" hint="Required by venues such as Angel One">
            <Input
              value={instrumentToken}
              onChange={(event) => setInstrumentToken(event.target.value)}
            />
          </Field>
          <Field label="Contract multiplier">
            <Input
              type="number"
              min="0.0000000001"
              step="any"
              value={multiplier}
              onChange={(event) => setMultiplier(event.target.value)}
            />
          </Field>
          <Field label="Tick size" required>
            <Input
              type="number"
              min="0.0000000001"
              step="any"
              value={tickSize}
              onChange={(event) => setTickSize(event.target.value)}
            />
          </Field>
          <Field label="Lot size" required>
            <Input
              type="number"
              min="0.0000000001"
              step="any"
              value={lotSize}
              onChange={(event) => setLotSize(event.target.value)}
            />
          </Field>
        </div>
        <Button
          className="w-full"
          onClick={submit}
          loading={submitting}
          disabled={!brokerId || !instrumentId || !venueSymbol.trim() || !exchange.trim()}
        >
          Create mapping
        </Button>
      </div>
    </Modal>
  );
}

function HealthSection() {
  const { data: health } = useSystemHealth();
  const { data: brokers } = useBrokerMonitor();

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Database"
          value={health?.database ? "Healthy" : "Down"}
          valueClass={health?.database ? "text-profit-500" : "text-loss-500"}
        />
        <StatCard
          label="Redis"
          value={health?.redis ? "Healthy" : "Down"}
          valueClass={health?.redis ? "text-profit-500" : "text-loss-500"}
        />
        <StatCard label="Outbox backlog" value={String(health?.outbox_backlog ?? "—")} />
        <StatCard label="Active runs" value={String(health?.active_runs ?? "—")} />
      </div>
      <Card title="Process heartbeats">
        <dl className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs text-slate-500">Market data age</dt>
            <dd className="mt-0.5 font-medium tabular-nums">
              {health?.market_data_age_seconds != null
                ? `${health.market_data_age_seconds.toFixed(0)}s`
                : "no heartbeat"}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Engine age</dt>
            <dd className="mt-0.5 font-medium tabular-nums">
              {health?.engine_heartbeat_age_seconds != null
                ? `${health.engine_heartbeat_age_seconds.toFixed(0)}s`
                : "no heartbeat"}
            </dd>
          </div>
        </dl>
      </Card>
      <Card title="Broker connections by status">
        {!brokers || Object.keys(brokers).length === 0 ? (
          <EmptyState title="No broker connections" />
        ) : (
          <div className="flex flex-wrap gap-3">
            {Object.entries(brokers).map(([status, count]) => (
              <div
                key={status}
                className="rounded-lg border border-slate-200 px-4 py-2 dark:border-surface-700"
              >
                <p className="text-xs text-slate-500">{status}</p>
                <p className="text-xl font-semibold tabular-nums">{count}</p>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function UsersSection() {
  const [search, setSearch] = useState("");
  const { data: users, isLoading } = useAdminUsers(search);
  const client = useQueryClient();

  async function toggle(userId: string, suspend: boolean) {
    try {
      await api(`/admin/users/${userId}/${suspend ? "suspend" : "reactivate"}`, {
        method: "POST",
        skipOrg: true,
      });
      client.invalidateQueries({ queryKey: ["admin-users"] });
      toastSuccess(suspend ? "User suspended" : "User reactivated");
    } catch (error) {
      toastError("Action failed", error instanceof ApiError ? error.detail : undefined);
    }
  }

  return (
    <Card
      title="Users"
      actions={
        <Input
          placeholder="Search users…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          className="w-48"
        />
      }
    >
      {isLoading ? (
        <SkeletonRows rows={5} cols={5} />
      ) : !users || users.length === 0 ? (
        <EmptyState title="No users" />
      ) : (
        <Table headers={["User", "Status", "MFA", "Admin", "Joined", ""]}>
          {users.map((user) => (
            <tr key={user.id}>
              <Td>
                <div>
                  <p className="font-medium">{user.full_name}</p>
                  <p className="text-xs text-slate-400">{user.email}</p>
                </div>
              </Td>
              <Td>
                <Badge color={statusColor(user.status)}>{user.status}</Badge>
              </Td>
              <Td>{user.mfa_enabled ? "✓" : "—"}</Td>
              <Td>{user.is_platform_admin ? <Badge color="violet">admin</Badge> : "—"}</Td>
              <Td className="text-xs text-slate-400">{dateOnly(user.created_at)}</Td>
              <Td>
                {user.status === "suspended" ? (
                  <Button size="sm" variant="ghost" onClick={() => toggle(user.id, false)}>
                    Reactivate
                  </Button>
                ) : (
                  <Button size="sm" variant="ghost" onClick={() => toggle(user.id, true)}>
                    Suspend
                  </Button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}

function OrganizationsSection() {
  const { data: orgs, isLoading } = useAdminOrganizations();
  return (
    <Card title="Organizations">
      {isLoading ? (
        <SkeletonRows rows={5} cols={4} />
      ) : !orgs || orgs.length === 0 ? (
        <EmptyState title="No organizations" />
      ) : (
        <Table headers={["Name", "Slug", "Plan", "Status", "Created"]}>
          {orgs.map((org) => (
            <tr key={org.id}>
              <Td className="font-medium">{org.name}</Td>
              <Td className="font-mono text-xs">{org.slug}</Td>
              <Td>{org.plan_code ? <Badge color="blue">{org.plan_code}</Badge> : "—"}</Td>
              <Td>
                {org.subscription_status ? (
                  <Badge color={statusColor(org.subscription_status)}>
                    {org.subscription_status}
                  </Badge>
                ) : (
                  "—"
                )}
              </Td>
              <Td className="text-xs text-slate-400">{dateTime(org.created_at)}</Td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}

function PlansSection() {
  const { data: plans, isLoading } = useAdminPlans();
  const client = useQueryClient();
  const [editingBilling, setEditingBilling] = useState<Plan | null>(null);

  async function toggleActive(planId: string, isActive: boolean) {
    try {
      await api(`/admin/plans/${planId}`, {
        method: "PATCH",
        skipOrg: true,
        body: { is_active: !isActive },
      });
      client.invalidateQueries({ queryKey: ["admin-plans"] });
      client.invalidateQueries({ queryKey: ["plans"] });
      toastSuccess(isActive ? "Plan disabled" : "Plan enabled");
    } catch (error) {
      toastError("Action failed", error instanceof ApiError ? error.detail : undefined);
    }
  }

  return (
    <Card title="Plans">
      {isLoading ? (
        <SkeletonRows rows={4} cols={5} />
      ) : (
        <Table headers={["Code", "Name", "Monthly", "Yearly", "Recurring", "Active", ""]}>
          {(plans ?? []).map((plan) => (
            <tr key={plan.id}>
              <Td className="font-mono text-xs">{plan.code}</Td>
              <Td className="font-medium">{plan.name}</Td>
              <Td className="tabular-nums">{money(plan.price_monthly, plan.currency)}</Td>
              <Td className="tabular-nums">{money(plan.price_yearly, plan.currency)}</Td>
              <Td>
                <Badge
                  color={
                    Object.keys(plan.provider_prices ?? {}).length > 0 ? "green" : "amber"
                  }
                >
                  {Object.keys(plan.provider_prices ?? {}).length > 0
                    ? "configured"
                    : "missing"}
                </Badge>
              </Td>
              <Td>
                <Badge color={plan.is_active ? "green" : "slate"}>
                  {plan.is_active ? "active" : "disabled"}
                </Badge>
              </Td>
              <Td>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => setEditingBilling(plan)}>
                    Billing refs
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => toggleActive(plan.id, plan.is_active)}
                  >
                    {plan.is_active ? "Disable" : "Enable"}
                  </Button>
                </div>
              </Td>
            </tr>
          ))}
        </Table>
      )}
      {editingBilling && (
        <PlanBillingRefsModal
          plan={editingBilling}
          onClose={() => setEditingBilling(null)}
          onSaved={() => {
            setEditingBilling(null);
            client.invalidateQueries({ queryKey: ["admin-plans"] });
            client.invalidateQueries({ queryKey: ["plans"] });
          }}
        />
      )}
    </Card>
  );
}

function PlanBillingRefsModal({
  plan,
  onClose,
  onSaved,
}: {
  plan: Plan;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({
    "stripe:monthly": plan.provider_prices?.["stripe:monthly"] ?? "",
    "stripe:yearly": plan.provider_prices?.["stripe:yearly"] ?? "",
    "razorpay:monthly": plan.provider_prices?.["razorpay:monthly"] ?? "",
    "razorpay:yearly": plan.provider_prices?.["razorpay:yearly"] ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const providerPrices = Object.fromEntries(
        Object.entries(values)
          .map(([key, value]) => [key, value.trim()])
          .filter(([, value]) => value),
      );
      await api(`/admin/plans/${plan.id}`, {
        method: "PATCH",
        skipOrg: true,
        body: { provider_prices: providerPrices },
      });
      toastSuccess("Recurring billing references saved");
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not save billing references");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={`Recurring billing — ${plan.name}`}>
      <div className="space-y-4">
        <p className="text-xs text-slate-500">
          Enter recurring Price IDs from Stripe and Plan IDs from Razorpay. Paid checkout is
          blocked for provider/cycle pairs without a reference.
        </p>
        {error && <p className="text-sm text-loss-500">{error}</p>}
        {Object.keys(values).map((key) => (
          <Field key={key} label={key.replace(":", " / ")}>
            <Input
              value={values[key]}
              onChange={(event) =>
                setValues((current) => ({ ...current, [key]: event.target.value }))
              }
              placeholder={key.startsWith("stripe") ? "price_…" : "plan_…"}
            />
          </Field>
        ))}
        <Button className="w-full" onClick={save} loading={saving}>
          Save billing references
        </Button>
      </div>
    </Modal>
  );
}

function CouponsSection() {
  const { data: coupons, isLoading } = useAdminCoupons();
  const [createOpen, setCreateOpen] = useState(false);
  const client = useQueryClient();

  async function deactivate(id: string) {
    await api(`/admin/coupons/${id}/deactivate`, { method: "POST", skipOrg: true }).catch(
      () => undefined,
    );
    client.invalidateQueries({ queryKey: ["admin-coupons"] });
    toastSuccess("Coupon deactivated");
  }

  return (
    <Card
      title="Coupons"
      actions={
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          Create coupon
        </Button>
      }
    >
      {isLoading ? (
        <SkeletonRows rows={4} cols={5} />
      ) : !coupons || coupons.length === 0 ? (
        <EmptyState title="No coupons" />
      ) : (
        <Table headers={["Code", "Discount", "Redeemed", "Valid until", "Active", ""]}>
          {coupons.map((coupon) => (
            <tr key={coupon.id}>
              <Td className="font-mono text-xs">{coupon.code}</Td>
              <Td>
                {coupon.percent_off
                  ? `${coupon.percent_off}%`
                  : money(coupon.amount_off, coupon.currency)}
              </Td>
              <Td className="tabular-nums">
                {coupon.redeemed_count}
                {coupon.max_redemptions ? ` / ${coupon.max_redemptions}` : ""}
              </Td>
              <Td className="text-xs text-slate-400">
                {coupon.valid_until ? dateOnly(coupon.valid_until) : "—"}
              </Td>
              <Td>
                <Badge color={coupon.is_active ? "green" : "slate"}>
                  {coupon.is_active ? "active" : "inactive"}
                </Badge>
              </Td>
              <Td>
                {coupon.is_active && (
                  <Button size="sm" variant="ghost" onClick={() => deactivate(coupon.id)}>
                    Deactivate
                  </Button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      )}
      {createOpen && (
        <CreateCouponModal
          onClose={() => setCreateOpen(false)}
          onCreated={() => {
            setCreateOpen(false);
            client.invalidateQueries({ queryKey: ["admin-coupons"] });
          }}
        />
      )}
    </Card>
  );
}

function CreateCouponModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [code, setCode] = useState("");
  const [discountType, setDiscountType] = useState<"percent" | "amount">("percent");
  const [value, setValue] = useState("");
  const [maxRedemptions, setMaxRedemptions] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      await api("/admin/coupons", {
        method: "POST",
        skipOrg: true,
        body: {
          code,
          description: "",
          percent_off: discountType === "percent" ? value : null,
          amount_off: discountType === "amount" ? value : null,
          currency: "INR",
          max_redemptions: maxRedemptions ? Number(maxRedemptions) : null,
          applies_plan_codes: [],
        },
      });
      toastSuccess("Coupon created");
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to create");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Create coupon">
      <div className="space-y-3">
        {error && (
          <div className="rounded-lg border border-loss-500/40 bg-loss-500/10 px-3 py-2 text-sm text-loss-600 dark:text-loss-400">
            {error}
          </div>
        )}
        <Field label="Code" required>
          <Input value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Discount type">
            <Select
              value={discountType}
              onChange={(event) => setDiscountType(event.target.value as "percent" | "amount")}
            >
              <option value="percent">Percent off</option>
              <option value="amount">Amount off</option>
            </Select>
          </Field>
          <Field label={discountType === "percent" ? "Percent (1-100)" : "Amount"}>
            <Input type="number" value={value} onChange={(event) => setValue(event.target.value)} />
          </Field>
        </div>
        <Field label="Max redemptions" hint="Leave blank for unlimited">
          <Input
            type="number"
            value={maxRedemptions}
            onChange={(event) => setMaxRedemptions(event.target.value)}
          />
        </Field>
        <Button className="w-full" onClick={submit} loading={submitting}>
          Create coupon
        </Button>
      </div>
    </Modal>
  );
}

function GrantsSection() {
  const [orgId, setOrgId] = useState("");
  const [planCode, setPlanCode] = useState("pro");
  const [days, setDays] = useState("30");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { data: orgs } = useAdminOrganizations();
  const { data: plans } = useAdminPlans();

  async function submit() {
    setSubmitting(true);
    try {
      await api("/admin/subscriptions/grant", {
        method: "POST",
        skipOrg: true,
        body: { organization_id: orgId, plan_code: planCode, days: Number(days), note },
      });
      toastSuccess("Subscription granted");
      setNote("");
    } catch (error) {
      toastError("Grant failed", error instanceof ApiError ? error.detail : undefined);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card title="Grant manual subscription">
      <div className="max-w-lg space-y-3">
        <Field label="Organization">
          <Select value={orgId} onChange={(event) => setOrgId(event.target.value)}>
            <option value="">Select an organization…</option>
            {(orgs ?? []).map((org) => (
              <option key={org.id} value={org.id}>
                {org.name}
              </option>
            ))}
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Plan">
            <Select value={planCode} onChange={(event) => setPlanCode(event.target.value)}>
              {(plans ?? []).map((plan) => (
                <option key={plan.id} value={plan.code}>
                  {plan.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Duration (days)">
            <Input type="number" value={days} onChange={(event) => setDays(event.target.value)} />
          </Field>
        </div>
        <Field label="Note">
          <Input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Reason for grant" />
        </Field>
        <Button onClick={submit} loading={submitting} disabled={!orgId}>
          Grant subscription
        </Button>
      </div>
    </Card>
  );
}
