import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  SkeletonRows,
  Spinner,
  statusColor,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useBrokerCatalog, useBrokerConnections } from "@/lib/hooks";
import { money } from "@/lib/format";
import { toastError, toastSuccess } from "@/stores/toast";
import type { BrokerCatalogEntry, BrokerConnection } from "@/types/api";

export function BrokersPage({ embedded = false }: { embedded?: boolean }) {
  const { data: connections, isLoading } = useBrokerConnections();
  const [wizardOpen, setWizardOpen] = useState(false);
  const [toRemove, setToRemove] = useState<BrokerConnection | null>(null);
  const [verifyingId, setVerifyingId] = useState<string | null>(null);
  const [removing, setRemoving] = useState(false);
  const client = useQueryClient();

  function invalidate() {
    client.invalidateQueries({ queryKey: ["broker-connections"] });
    client.invalidateQueries({ queryKey: ["accounts"] });
  }

  async function verify(connection: BrokerConnection) {
    setVerifyingId(connection.id);
    try {
      await api(`/broker-connections/${connection.id}/verify`, { method: "POST" });
      invalidate();
      toastSuccess("Verification complete");
    } catch (error) {
      toastError("Verification failed", error instanceof ApiError ? error.detail : undefined);
    } finally {
      setVerifyingId(null);
    }
  }

  async function remove() {
    if (!toRemove) return;
    setRemoving(true);
    try {
      await api(`/broker-connections/${toRemove.id}`, { method: "DELETE" });
      invalidate();
      toastSuccess("Broker connection removed");
      setToRemove(null);
    } catch (error) {
      toastError("Remove failed", error instanceof ApiError ? error.detail : undefined);
    } finally {
      setRemoving(false);
    }
  }

  return (
    <div>
      {embedded ? (
        <div className="mb-4 flex items-center justify-between gap-3">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Connect and manage broker accounts. Credentials are encrypted at rest.
          </p>
          <Button onClick={() => setWizardOpen(true)}>Add broker</Button>
        </div>
      ) : (
        <PageHeader
          title="Brokers"
          description="Connect and manage broker accounts. Credentials are encrypted at rest."
          actions={<Button onClick={() => setWizardOpen(true)}>Add broker</Button>}
        />
      )}

      {isLoading ? (
        <Card>
          <SkeletonRows rows={3} cols={4} />
        </Card>
      ) : !connections || connections.length === 0 ? (
        <Card>
          <EmptyState
            title="No broker connections"
            body="Add the Paper Trading simulator to start paper trading immediately, or connect a live broker."
            action={<Button onClick={() => setWizardOpen(true)}>Add your first broker</Button>}
          />
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {connections.map((connection) => (
            <Card key={connection.id} title={connection.name}>
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm text-slate-500">{connection.broker_name}</p>
                  <div className="mt-2 flex items-center gap-2">
                    <Badge color={statusColor(connection.status)}>{connection.status}</Badge>
                    {connection.failure_reason && (
                      <span className="text-xs text-loss-500">{connection.failure_reason}</span>
                    )}
                  </div>
                </div>
                <div className="flex gap-1.5">
                  <Button
                    size="sm"
                    variant="secondary"
                    loading={verifyingId === connection.id}
                    onClick={() => verify(connection)}
                  >
                    Test
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setToRemove(connection)}>
                    Remove
                  </Button>
                </div>
              </div>
              {connection.accounts.length > 0 && (
                <div className="mt-3 space-y-2 border-t border-slate-100 pt-3 dark:border-surface-800">
                  {connection.accounts.map((account) => (
                    <div key={account.id} className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2">
                        <Badge color={account.mode === "live" ? "red" : "blue"}>{account.mode}</Badge>
                        <span>{account.name}</span>
                      </div>
                      <span className="tabular-nums text-slate-500">
                        {money(account.equity, account.base_currency)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}

      <AddBrokerWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        onDone={() => {
          setWizardOpen(false);
          invalidate();
        }}
      />

      <ConfirmDialog
        open={Boolean(toRemove)}
        onClose={() => setToRemove(null)}
        onConfirm={remove}
        title="Remove broker connection"
        body={`Remove "${toRemove?.name}"? Associated accounts will be closed. This cannot be undone.`}
        confirmLabel="Remove"
        danger
        loading={removing}
      />
    </div>
  );
}

function AddBrokerWizard({
  open,
  onClose,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const { data: catalog, isLoading } = useBrokerCatalog();
  const [step, setStep] = useState(1);
  const [selected, setSelected] = useState<BrokerCatalogEntry | null>(null);
  const [name, setName] = useState("");
  const [mode, setMode] = useState<"paper" | "live">("paper");
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setStep(1);
    setSelected(null);
    setName("");
    setMode("paper");
    setCredentials({});
    setError(null);
  }

  function choose(broker: BrokerCatalogEntry) {
    setSelected(broker);
    setName(`${broker.name} account`);
    setMode(broker.supports_paper ? "paper" : "live");
    const defaults: Record<string, string> = {};
    if (broker.code === "paper") {
      defaults.starting_balance = "1000000";
      defaults.base_currency = "INR";
    }
    setCredentials(defaults);
    setStep(2);
  }

  async function submit() {
    if (!selected) return;
    setSubmitting(true);
    setError(null);
    try {
      await api("/broker-connections", {
        method: "POST",
        body: { broker_code: selected.code, name, credentials, account_mode: mode },
      });
      toastSuccess("Broker connected");
      reset();
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to add broker");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      title={step === 1 ? "Choose a broker" : `Connect ${selected?.name}`}
      wide
    >
      {step === 1 ? (
        isLoading ? (
          <div className="flex justify-center py-8">
            <Spinner className="size-6 text-accent-500" />
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {(catalog ?? []).map((broker) => (
              <button
                key={broker.id}
                onClick={() => choose(broker)}
                className="rounded-lg border border-slate-200 p-4 text-left transition-colors hover:border-accent-500 dark:border-surface-700"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">{broker.name}</span>
                  <div className="flex gap-1">
                    {broker.supports_paper && <Badge color="blue">paper</Badge>}
                    {broker.supports_live && <Badge color="green">live</Badge>}
                  </div>
                </div>
                <p className="mt-1 text-xs text-slate-500">{broker.description}</p>
              </button>
            ))}
          </div>
        )
      ) : (
        <div className="space-y-4">
          {error && (
            <div className="rounded-lg border border-loss-500/40 bg-loss-500/10 px-3 py-2 text-sm text-loss-600 dark:text-loss-400">
              {error}
            </div>
          )}
          <Field label="Connection name" required>
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </Field>
          {selected && selected.supports_paper && selected.supports_live && (
            <Field label="Account mode">
              <Select value={mode} onChange={(event) => setMode(event.target.value as "paper" | "live")}>
                <option value="paper">Paper</option>
                <option value="live">Live</option>
              </Select>
            </Field>
          )}
          {selected?.credential_fields.map((field) => (
            <Field key={field.name} label={field.label} hint={field.help_text} required>
              <Input
                type={field.secret ? "password" : "text"}
                value={credentials[field.name] ?? ""}
                autoComplete="off"
                onChange={(event) =>
                  setCredentials((prev) => ({ ...prev, [field.name]: event.target.value }))
                }
              />
            </Field>
          ))}
          {mode === "live" && (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-600 dark:text-amber-400">
              Live mode routes real orders to the venue. Ensure your plan includes live trading and
              your credentials are correct — they are verified before activation.
            </div>
          )}
          <div className="flex justify-between pt-2">
            <Button variant="ghost" onClick={() => setStep(1)}>
              Back
            </Button>
            <Button onClick={submit} loading={submitting}>
              Connect &amp; verify
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
