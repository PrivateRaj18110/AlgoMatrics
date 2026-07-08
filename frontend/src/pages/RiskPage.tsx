import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

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
  Table,
  Td,
  statusColor,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useKillSwitches, useRiskLimits, useRiskViolations } from "@/lib/hooks";
import { dateTime, money } from "@/lib/format";
import { toastError, toastSuccess } from "@/stores/toast";
import type { RiskLimits } from "@/types/api";

export function RiskPage() {
  const { data: limits, isLoading } = useRiskLimits();
  const { data: killSwitches } = useKillSwitches();
  const { data: violations } = useRiskViolations();
  const [editing, setEditing] = useState<RiskLimits | null>(null);
  const [engageOpen, setEngageOpen] = useState(false);
  const client = useQueryClient();

  function invalidate() {
    client.invalidateQueries({ queryKey: ["risk-limits"] });
    client.invalidateQueries({ queryKey: ["kill-switches"] });
    client.invalidateQueries({ queryKey: ["risk-violations"] });
  }

  async function releaseSwitch(id: string) {
    try {
      await api(`/risk/kill-switches/${id}`, { method: "DELETE" });
      invalidate();
      toastSuccess("Kill switch released");
    } catch (error) {
      toastError("Release failed", error instanceof ApiError ? error.detail : undefined);
    }
  }

  const orgLimits = limits?.find((entry) => entry.account_id === null);

  return (
    <div>
      <PageHeader
        title="Risk"
        description="Pre-trade limits, kill switches, and violations"
        actions={
          <Button variant="danger" onClick={() => setEngageOpen(true)}>
            Engage kill switch
          </Button>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card
          title="Organization limits"
          className="lg:col-span-2"
          actions={
            orgLimits && (
              <Button size="sm" variant="secondary" onClick={() => setEditing(orgLimits)}>
                Edit
              </Button>
            )
          }
        >
          {isLoading ? (
            <SkeletonRows rows={4} cols={2} />
          ) : !orgLimits ? (
            <EmptyState title="No limits configured" />
          ) : (
            <dl className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
              <Limit label="Max order quantity" value={orgLimits.max_order_quantity} />
              <Limit label="Max order value" value={money(orgLimits.max_order_value)} />
              <Limit label="Max daily loss" value={money(orgLimits.max_daily_loss)} />
              <Limit label="Max open positions" value={String(orgLimits.max_open_positions)} />
              <Limit label="Max exposure" value={money(orgLimits.max_exposure_value)} />
              <Limit label="Max drawdown" value={`${orgLimits.max_drawdown_pct}%`} />
            </dl>
          )}
        </Card>

        <Card title="Active kill switches">
          {!killSwitches || killSwitches.length === 0 ? (
            <EmptyState title="No kill switches engaged" body="Trading is unrestricted." />
          ) : (
            <ul className="space-y-3">
              {killSwitches.map((entry) => (
                <li key={entry.id} className="rounded-lg border border-loss-500/40 bg-loss-500/5 p-3">
                  <div className="flex items-center justify-between">
                    <Badge color="red">{entry.scope}</Badge>
                    <Button size="sm" variant="ghost" onClick={() => releaseSwitch(entry.id)}>
                      Release
                    </Button>
                  </div>
                  <p className="mt-1 text-sm">{entry.reason}</p>
                  <p className="mt-1 text-xs text-slate-400">{dateTime(entry.engaged_at)}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card className="mt-6" title="Risk violations">
        {!violations || violations.items.length === 0 ? (
          <EmptyState title="No violations" body="Risk events and breaches appear here." />
        ) : (
          <Table headers={["Type", "Severity", "Message", "When"]}>
            {violations.items.map((event) => (
              <tr key={event.id}>
                <Td className="font-mono text-xs">{event.event_type}</Td>
                <Td>
                  <Badge color={statusColor(event.severity)}>{event.severity}</Badge>
                </Td>
                <Td className="max-w-md text-slate-600 dark:text-slate-300">{event.message}</Td>
                <Td className="text-xs text-slate-400">{dateTime(event.occurred_at)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      {editing && (
        <EditLimitsModal
          limits={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            invalidate();
          }}
        />
      )}

      {engageOpen && (
        <EngageKillSwitchModal
          onClose={() => setEngageOpen(false)}
          onEngaged={() => {
            setEngageOpen(false);
            invalidate();
          }}
        />
      )}
    </div>
  );
}

function Limit({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="mt-0.5 font-medium tabular-nums">{value}</dd>
    </div>
  );
}

function EditLimitsModal({
  limits,
  onClose,
  onSaved,
}: {
  limits: RiskLimits;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    max_order_quantity: limits.max_order_quantity,
    max_order_value: limits.max_order_value,
    max_daily_loss: limits.max_daily_loss,
    max_open_positions: String(limits.max_open_positions),
    max_exposure_value: limits.max_exposure_value,
    max_drawdown_pct: limits.max_drawdown_pct,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      await api(`/risk/limits/${limits.id}`, {
        method: "PATCH",
        body: {
          max_order_quantity: form.max_order_quantity,
          max_order_value: form.max_order_value,
          max_daily_loss: form.max_daily_loss,
          max_open_positions: Number(form.max_open_positions),
          max_exposure_value: form.max_exposure_value,
          max_drawdown_pct: form.max_drawdown_pct,
        },
      });
      toastSuccess("Risk limits updated");
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Update failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Edit risk limits">
      <div className="space-y-3">
        {error && (
          <div className="rounded-lg border border-loss-500/40 bg-loss-500/10 px-3 py-2 text-sm text-loss-600 dark:text-loss-400">
            {error}
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Max order quantity">
            <Input
              type="number"
              value={form.max_order_quantity}
              onChange={(event) => setForm({ ...form, max_order_quantity: event.target.value })}
            />
          </Field>
          <Field label="Max order value">
            <Input
              type="number"
              value={form.max_order_value}
              onChange={(event) => setForm({ ...form, max_order_value: event.target.value })}
            />
          </Field>
          <Field label="Max daily loss">
            <Input
              type="number"
              value={form.max_daily_loss}
              onChange={(event) => setForm({ ...form, max_daily_loss: event.target.value })}
            />
          </Field>
          <Field label="Max open positions">
            <Input
              type="number"
              value={form.max_open_positions}
              onChange={(event) => setForm({ ...form, max_open_positions: event.target.value })}
            />
          </Field>
          <Field label="Max exposure value">
            <Input
              type="number"
              value={form.max_exposure_value}
              onChange={(event) => setForm({ ...form, max_exposure_value: event.target.value })}
            />
          </Field>
          <Field label="Max drawdown %">
            <Input
              type="number"
              value={form.max_drawdown_pct}
              onChange={(event) => setForm({ ...form, max_drawdown_pct: event.target.value })}
            />
          </Field>
        </div>
        <Button className="w-full" onClick={submit} loading={submitting}>
          Save limits
        </Button>
      </div>
    </Modal>
  );
}

function EngageKillSwitchModal({
  onClose,
  onEngaged,
}: {
  onClose: () => void;
  onEngaged: () => void;
}) {
  const [scope, setScope] = useState("organization");
  const [scopeRef, setScopeRef] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (reason.trim().length < 3) {
      setError("Provide a reason (at least 3 characters).");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api("/risk/kill-switches", {
        method: "POST",
        body: { scope, scope_ref: scopeRef, reason },
      });
      toastSuccess("Kill switch engaged");
      onEngaged();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to engage");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Engage kill switch">
      <div className="space-y-3">
        {error && (
          <div className="rounded-lg border border-loss-500/40 bg-loss-500/10 px-3 py-2 text-sm text-loss-600 dark:text-loss-400">
            {error}
          </div>
        )}
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-600 dark:text-amber-400">
          A kill switch blocks new order submission for its scope until released.
        </div>
        <Field label="Scope">
          <Select value={scope} onChange={(event) => setScope(event.target.value)}>
            <option value="organization">Organization (all trading)</option>
            <option value="account">Account</option>
            <option value="strategy">Strategy run</option>
          </Select>
        </Field>
        {scope !== "organization" && (
          <Field label="Scope reference (account / run ID)">
            <Input value={scopeRef} onChange={(event) => setScopeRef(event.target.value)} />
          </Field>
        )}
        <Field label="Reason" required>
          <Input value={reason} onChange={(event) => setReason(event.target.value)} />
        </Field>
        <Button className="w-full" variant="danger" onClick={submit} loading={submitting}>
          Engage kill switch
        </Button>
      </div>
    </Modal>
  );
}
