// Trading devices: every machine that reports to the console, its live health,
// and what it has reported. Adding a device mints a key that is shown once.

import { clsx } from "clsx";
import { useState } from "react";

import { Glyph } from "@/components/icons";
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
  StatCard,
  Table,
  Tabs,
  Td,
  surface,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import {
  type CreatedDevice,
  curlSnippet,
  type Device,
  type DeviceEvent,
  type DeviceKind,
  type DeviceStatus,
  useCreateDevice,
  useDeviceEvents,
  useDevices,
  useRevokeDevice,
} from "@/lib/devices";
import { dateTime, timeAgo } from "@/lib/format";
import { toastError, toastSuccess } from "@/stores/toast";

const STATUS: Record<DeviceStatus, { label: string; color: "green" | "red" | "slate" | "amber" }> = {
  online: { label: "Online", color: "green" },
  offline: { label: "Offline", color: "red" },
  never_seen: { label: "No reports yet", color: "amber" },
  revoked: { label: "Revoked", color: "slate" },
};

const KIND_LABEL: Record<DeviceKind, string> = {
  trading: "Trading engine",
  vps: "VPS",
  mt5: "MT5 terminal",
  desktop: "Desktop",
  other: "Other",
};

function Meter({ label, value }: { label: string; value: number | undefined }) {
  const known = typeof value === "number";
  const tone = !known ? "bg-slate-300" : value >= 90 ? "bg-loss-500" : value >= 75 ? "bg-amber-500" : "bg-profit-500";
  return (
    <div>
      <div className="flex justify-between text-[11px]">
        <span className="text-slate-500">{label}</span>
        <span className="font-medium tabular-nums text-slate-700 dark:text-slate-200">
          {known ? `${Math.round(value)}%` : "—"}
        </span>
      </div>
      <div className="mt-1 h-1.5 rounded-full bg-slate-100 dark:bg-white/[0.06]">
        <div className={clsx("h-full rounded-full", tone)} style={{ width: `${known ? Math.min(value, 100) : 0}%` }} />
      </div>
    </div>
  );
}

function DeviceCard({
  device,
  onOpen,
  onRevoke,
}: {
  device: Device;
  onOpen: () => void;
  onRevoke: () => void;
}) {
  const status = STATUS[device.status];
  const health = device.health ?? {};
  return (
    <div className={clsx(surface, "flex flex-col p-5", device.status === "revoked" && "opacity-60")}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span
            className={clsx(
              "flex size-10 shrink-0 items-center justify-center rounded-xl ring-1 ring-inset",
              device.status === "online"
                ? "bg-profit-500/10 text-profit-600 ring-profit-500/25 dark:text-profit-400"
                : "bg-slate-500/10 text-slate-500 ring-slate-500/20",
            )}
          >
            <Glyph name="server" />
          </span>
          <div className="min-w-0">
            <p className="truncate font-semibold text-slate-900 dark:text-white">{device.name}</p>
            <p className="text-xs text-slate-500">
              {KIND_LABEL[device.kind]} · key {device.key_prefix}…
            </p>
          </div>
        </div>
        <Badge color={status.color} dot>
          {status.label}
        </Badge>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3">
        <Meter label="CPU" value={typeof health.cpu === "number" ? health.cpu : undefined} />
        <Meter label="RAM" value={typeof health.ram === "number" ? health.ram : undefined} />
        <Meter label="Disk" value={typeof health.disk === "number" ? health.disk : undefined} />
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
        <dt className="text-slate-500">Last report</dt>
        <dd className="text-right text-slate-700 dark:text-slate-200" title={device.last_seen_at ? dateTime(device.last_seen_at) : undefined}>
          {device.last_seen_at ? timeAgo(device.last_seen_at) : "never"}
        </dd>
        <dt className="text-slate-500">Latency</dt>
        <dd className="text-right tabular-nums text-slate-700 dark:text-slate-200">
          {typeof health.latency_ms === "number" ? `${Math.round(health.latency_ms)} ms` : "—"}
        </dd>
        <dt className="text-slate-500">Open positions</dt>
        <dd className="text-right tabular-nums text-slate-700 dark:text-slate-200">
          {device.positions ? device.positions.length : "—"}
        </dd>
        <dt className="text-slate-500">From</dt>
        <dd className="truncate text-right font-mono text-[11px] text-slate-500">{device.last_ip ?? "—"}</dd>
        {health.version ? (
          <>
            <dt className="text-slate-500">Version</dt>
            <dd className="text-right font-mono text-[11px] text-slate-500">{String(health.version)}</dd>
          </>
        ) : null}
      </dl>

      <div className="mt-auto flex gap-2 pt-5">
        <Button size="sm" variant="secondary" className="flex-1" onClick={onOpen}>
          <Glyph name="list" className="size-3.5" />
          Activity
        </Button>
        {device.status !== "revoked" ? (
          <Button size="sm" variant="ghost" onClick={onRevoke}>
            Revoke
          </Button>
        ) : null}
      </div>
    </div>
  );
}

const SEVERITY_COLOR: Record<DeviceEvent["severity"], "slate" | "blue" | "amber" | "red"> = {
  debug: "slate",
  info: "blue",
  warning: "amber",
  error: "red",
  critical: "red",
};

function ActivityModal({ device, onClose }: { device: Device | null; onClose: () => void }) {
  const [tab, setTab] = useState<"trade" | "log" | "alert" | "positions">("trade");
  const events = useDeviceEvents(device && tab !== "positions" ? device.id : null, tab === "positions" ? null : tab);
  return (
    <Modal open={device !== null} onClose={onClose} title={device ? `${device.name} · activity` : ""} wide>
      <div className="mb-4">
        <Tabs
          tabs={[
            { key: "trade", label: "Trades" },
            { key: "log", label: "Logs" },
            { key: "alert", label: "Alerts" },
            { key: "positions", label: "Positions" },
          ]}
          active={tab}
          onChange={(key) => setTab(key as typeof tab)}
        />
      </div>
      {tab === "positions" ? (
        !device?.positions || device.positions.length === 0 ? (
          <EmptyState title="No positions reported" body="Send a positions event to show them here." />
        ) : (
          <>
            <p className="mb-2 text-xs text-slate-500">
              As of {device.positions_at ? dateTime(device.positions_at) : "—"}
            </p>
            <Table headers={["Symbol", "Qty", "Avg", "LTP", "P&L"]} dense>
              {device.positions.map((position) => (
                <tr key={position.symbol}>
                  <Td dense className="font-medium">{position.symbol}</Td>
                  <Td dense className="tabular-nums">{position.qty}</Td>
                  <Td dense className="tabular-nums">{position.avg_price ?? "—"}</Td>
                  <Td dense className="tabular-nums">{position.ltp ?? "—"}</Td>
                  <Td
                    dense
                    className={clsx(
                      "tabular-nums",
                      (position.pnl ?? 0) > 0 && "text-profit-600 dark:text-profit-400",
                      (position.pnl ?? 0) < 0 && "text-loss-600 dark:text-loss-400",
                    )}
                  >
                    {position.pnl ?? "—"}
                  </Td>
                </tr>
              ))}
            </Table>
          </>
        )
      ) : events.isLoading ? (
        <SkeletonRows rows={5} cols={3} />
      ) : !events.data || events.data.length === 0 ? (
        <EmptyState title="Nothing reported yet" body="Events appear here as the device sends them." />
      ) : (
        <ul className="max-h-[26rem] divide-y divide-slate-100 overflow-y-auto dark:divide-white/[0.05]">
          {events.data.map((event) => (
            <li key={event.id} className="flex items-start justify-between gap-4 py-2.5">
              <div className="min-w-0">
                <p className="text-sm text-slate-800 dark:text-slate-100">{event.message}</p>
                {Object.keys(event.payload).length > 0 && event.kind !== "trade" ? (
                  <p className="mt-0.5 truncate font-mono text-[11px] text-slate-500">
                    {JSON.stringify(event.payload)}
                  </p>
                ) : null}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <Badge color={SEVERITY_COLOR[event.severity]}>{event.severity}</Badge>
                <span className="text-[11px] text-slate-500" title={dateTime(event.occurred_at)}>
                  {timeAgo(event.occurred_at)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}

function AddDeviceModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<DeviceKind>("vps");
  const [created, setCreated] = useState<CreatedDevice | null>(null);
  const create = useCreateDevice();

  const close = () => {
    setName("");
    setCreated(null);
    onClose();
  };

  const copy = (text: string, what: string) =>
    navigator.clipboard
      ?.writeText(text)
      .then(() => toastSuccess(`${what} copied`))
      .catch(() => toastError("Copy failed", "Select the text and copy it manually."));

  return (
    <Modal open={open} onClose={close} title={created ? "Device key created" : "Add a device"} wide={Boolean(created)}>
      {created ? (
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/[0.07] p-3 text-xs text-amber-900 dark:text-amber-100/80">
            <Glyph name="lock" className="mt-0.5 size-4 text-amber-500" />
            This key is shown <strong>once</strong>. Store it on the device now; only a hash is
            kept here. If it is lost, revoke the device and add it again.
          </div>
          <Field label="Device key">
            <div className="flex gap-2">
              <Input readOnly value={created.key} className="font-mono text-xs" onFocus={(event) => event.target.select()} />
              <Button variant="secondary" onClick={() => copy(created.key, "Key")}>
                Copy
              </Button>
            </div>
          </Field>
          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-[13px] font-medium text-slate-700 dark:text-slate-300">Test it from the device</span>
              <button
                type="button"
                className="text-xs font-medium text-accent-600 hover:underline dark:text-accent-400"
                onClick={() => copy(curlSnippet(created.ingest_url, created.key), "Command")}
              >
                Copy command
              </button>
            </div>
            <pre className="overflow-x-auto rounded-xl bg-surface-950 p-4 font-mono text-[11px] leading-relaxed text-slate-200">
              {curlSnippet(created.ingest_url, created.key)}
            </pre>
            <p className="mt-2 text-xs text-slate-500">
              Heartbeats every 30–60 s keep it “online”. Trades, positions, logs and alerts use the
              same URL — see docs/operations/device-ingest.md for every field.
            </p>
          </div>
          <div className="flex justify-end">
            <Button onClick={close}>Done</Button>
          </div>
        </div>
      ) : (
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate(
              { name: name.trim(), kind },
              {
                onSuccess: setCreated,
                onError: (error) =>
                  toastError("Could not add device", error instanceof ApiError ? error.detail : undefined),
              },
            );
          }}
        >
          <Field label="Name" hint="Something you will recognise on the dashboard, e.g. VPS Mumbai 1" required>
            <Input value={name} onChange={(event) => setName(event.target.value)} maxLength={120} autoFocus />
          </Field>
          <Field label="Type">
            <Select value={kind} onChange={(event) => setKind(event.target.value as DeviceKind)}>
              {Object.entries(KIND_LABEL).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={close}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending} disabled={!name.trim()}>
              Create key
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}

export function DevicesPage() {
  const devices = useDevices();
  const revoke = useRevokeDevice();
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState<Device | null>(null);
  const [revoking, setRevoking] = useState<Device | null>(null);
  const list = devices.data ?? [];
  const count = (status: DeviceStatus) => list.filter((device) => device.status === status).length;

  return (
    <div className="am-fade-in">
      <PageHeader
        eyebrow="Operations · Devices"
        title="Trading devices"
        description="Every machine that reports to the console: live health, trades, positions, logs and alerts over one URL and one key."
        actions={
          <Button size="sm" onClick={() => setAdding(true)}>
            <Glyph name="server" className="size-3.5" />
            Add device
          </Button>
        }
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Online" value={count("online")} icon={<Glyph name="signal" />} tone="profit" sub="Reported in the last 3 minutes" />
        <StatCard label="Offline" value={count("offline")} icon={<Glyph name="alert" />} tone={count("offline") ? "loss" : "neutral"} sub="Silent for over 3 minutes" />
        <StatCard label="Awaiting first report" value={count("never_seen")} icon={<Glyph name="clock" />} tone="amber" sub="Key created, nothing received" />
        <StatCard label="Revoked" value={count("revoked")} icon={<Glyph name="lock" />} tone="neutral" sub="Keys that no longer work" />
      </div>

      {devices.isLoading ? (
        <SkeletonRows rows={4} cols={3} />
      ) : list.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Glyph name="server" className="size-5" />}
            title="No devices yet"
            body="Add a device to get a key. Any machine that can send an HTTPS POST can then report heartbeats, trades, positions, logs and alerts."
            action={
              <Button size="sm" onClick={() => setAdding(true)}>
                Add your first device
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {list.map((device) => (
            <DeviceCard
              key={device.id}
              device={device}
              onOpen={() => setOpen(device)}
              onRevoke={() => setRevoking(device)}
            />
          ))}
        </div>
      )}

      <AddDeviceModal open={adding} onClose={() => setAdding(false)} />
      <ActivityModal device={open} onClose={() => setOpen(null)} />
      <ConfirmDialog
        open={revoking !== null}
        onClose={() => setRevoking(null)}
        title="Revoke this device?"
        body={`${revoking?.name ?? ""} will be refused from now on. Its history stays; to reconnect it, add it again with a new key.`}
        confirmLabel="Revoke key"
        danger
        loading={revoke.isPending}
        onConfirm={() => {
          if (!revoking) return;
          const target = revoking;
          revoke.mutate(target.id, {
            onSuccess: () => {
              toastSuccess("Device revoked", target.name);
              setRevoking(null);
            },
            onError: (error) =>
              toastError("Could not revoke", error instanceof ApiError ? error.detail : undefined),
          });
        }}
      />
    </div>
  );
}
