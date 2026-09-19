import { clsx } from "clsx";
import { useDeferredValue, useState } from "react";

import { Glyph } from "@/components/icons";
import {
  Badge,
  Card,
  EmptyState,
  Field,
  Input,
  PageHeader,
  SkeletonRows,
  Table,
  Td,
} from "@/components/ui";
import { describeDevice, describeLocation, flagEmoji } from "@/lib/device";
import { dateTime, timeAgo } from "@/lib/format";
import { useAuditEvents } from "@/lib/hooks";
import type { AuditEntry } from "@/types/api";

// Colour by the action's family so a column of events can be scanned by kind.
const ACTION_TONE: Array<[prefix: string, classes: string]> = [
  ["auth.login_", "bg-loss-500/10 text-loss-700 ring-loss-500/25 dark:text-loss-400"],
  ["auth.", "bg-accent-500/10 text-accent-700 ring-accent-500/25 dark:text-accent-300"],
  ["admin.", "bg-violet-500/10 text-violet-700 ring-violet-500/25 dark:text-violet-300"],
  ["orders.", "bg-profit-500/10 text-profit-700 ring-profit-500/25 dark:text-profit-400"],
  ["members.", "bg-amber-500/10 text-amber-700 ring-amber-500/25 dark:text-amber-300"],
];

function actionClasses(action: string): string {
  const match = ACTION_TONE.find(([prefix]) => action.startsWith(prefix));
  return (
    match?.[1] ??
    "bg-slate-100 text-slate-700 ring-slate-200 dark:bg-white/[0.06] dark:text-slate-300 dark:ring-white/10"
  );
}

export function AuditLogPage() {
  const [actionPrefix, setActionPrefix] = useState("");
  const [correlationId, setCorrelationId] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [ipAddress, setIpAddress] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const filters = useDeferredValue({ actionPrefix, correlationId, resourceType, ipAddress });

  const { data, isLoading, isError, refetch } = useAuditEvents({
    actionPrefix: filters.actionPrefix || undefined,
    correlationId: filters.correlationId || undefined,
    resourceType: filters.resourceType || undefined,
    ipAddress: filters.ipAddress.trim() || undefined,
  });

  return (
    <div className="am-fade-in">
      <PageHeader
        eyebrow="Security · Tamper-evident"
        title="Audit log"
        description="Every action with who did it, from where and on what device. Entries are hash-chained: altering any one breaks every entry after it."
        actions={
          data ? (
            <Badge color="slate">
              <Glyph name="list" className="size-3" />
              {data.total.toLocaleString()} events
            </Badge>
          ) : null
        }
      />
      <Card bodyClassName="p-0">
        <div className="grid gap-3 border-b border-slate-100 p-5 sm:grid-cols-2 xl:grid-cols-4 dark:border-white/[0.06]">
          <Field label="Action prefix">
            <Input
              value={actionPrefix}
              onChange={(event) => setActionPrefix(event.target.value)}
              placeholder="auth., orders., admin."
            />
          </Field>
          <Field label="Resource type">
            <Input
              value={resourceType}
              onChange={(event) => setResourceType(event.target.value)}
              placeholder="user, order, strategy"
            />
          </Field>
          <Field label="IP address">
            <Input
              value={ipAddress}
              onChange={(event) => setIpAddress(event.target.value)}
              placeholder="e.g. 49.36.12.8"
              inputMode="decimal"
            />
          </Field>
          <Field label="Correlation ID">
            <Input
              value={correlationId}
              onChange={(event) => setCorrelationId(event.target.value)}
              placeholder="trace a single operation"
            />
          </Field>
        </div>
        <div className="px-2 pb-2">
          {isLoading ? (
            <SkeletonRows rows={8} cols={5} />
          ) : isError ? (
            <EmptyState
              title="Audit events could not be loaded"
              action={
                <button
                  className="text-sm text-accent-600 hover:underline dark:text-accent-400"
                  onClick={() => refetch()}
                >
                  Retry
                </button>
              }
            />
          ) : !data || data.items.length === 0 ? (
            <EmptyState title="No matching audit events" />
          ) : (
            <Table headers={["Time", "Action", "Who", "Where", "Resource", "Chain", ""]}>
              {data.items.map((entry) => (
                <AuditRow
                  key={entry.id}
                  entry={entry}
                  open={expanded === entry.id}
                  onToggle={() => setExpanded(expanded === entry.id ? null : entry.id)}
                  onFilterIp={setIpAddress}
                />
              ))}
            </Table>
          )}
        </div>
        <p className="border-t border-slate-100 px-5 py-3 text-[11px] text-slate-400 dark:border-white/[0.06] dark:text-slate-500">
          Locations are approximate, resolved on our own server.{" "}
          <a
            href="https://db-ip.com"
            target="_blank"
            rel="noreferrer"
            className="underline decoration-dotted hover:text-slate-600 dark:hover:text-slate-300"
          >
            IP geolocation by DB-IP
          </a>
          .
        </p>
      </Card>
    </div>
  );
}

function AuditRow({
  entry,
  open,
  onToggle,
  onFilterIp,
}: {
  entry: AuditEntry;
  open: boolean;
  onToggle: () => void;
  onFilterIp: (ip: string) => void;
}) {
  const location = describeLocation(entry.geo);
  const flag = flagEmoji(entry.geo?.country_code);
  return (
    <>
      <tr className={clsx(open && "bg-slate-50/80 dark:bg-white/[0.025]")}>
        <Td className="whitespace-nowrap">
          <div className="text-sm text-slate-800 dark:text-slate-100">{timeAgo(entry.occurred_at)}</div>
          <div className="text-[11px] text-slate-500">{dateTime(entry.occurred_at)}</div>
        </Td>
        <Td>
          <span
            className={clsx(
              "inline-flex rounded-md px-1.5 py-0.5 font-mono text-xs font-medium ring-1 ring-inset",
              actionClasses(entry.action),
            )}
          >
            {entry.action}
          </span>
        </Td>
        <Td>
          <Badge color={entry.actor_type === "user" ? "blue" : "slate"}>{entry.actor_type}</Badge>
          {entry.actor_user_id && (
            <div className="mt-1 max-w-36 truncate font-mono text-[11px] text-slate-500" title={entry.actor_user_id}>
              {entry.actor_user_id}
            </div>
          )}
        </Td>
        <Td>
          {entry.ip_address ? (
            <div className="min-w-0">
              <button
                type="button"
                onClick={() => onFilterIp(entry.ip_address ?? "")}
                className="font-mono text-xs text-slate-800 hover:text-accent-600 dark:text-slate-100 dark:hover:text-accent-300"
                title="Show everything from this IP"
              >
                {entry.ip_address}
              </button>
              <div className="max-w-48 truncate text-[11px] text-slate-500">
                {flag && <span className="mr-1">{flag}</span>}
                {location ?? "Location unknown"}
              </div>
              <div className="text-[11px] text-slate-400">{describeDevice(entry.user_agent)}</div>
            </div>
          ) : (
            <span className="text-xs text-slate-400">Not recorded</span>
          )}
        </Td>
        <Td>
          <div className="text-sm">{entry.resource_type}</div>
          <div className="max-w-44 truncate text-xs text-slate-500">{entry.resource_id}</div>
        </Td>
        <Td className="text-xs text-slate-500">
          {entry.sequence !== null && <div>#{entry.sequence}</div>}
          {entry.correlation_id && (
            <div className="max-w-32 truncate" title={entry.correlation_id}>
              {entry.correlation_id}
            </div>
          )}
        </Td>
        <Td>
          <button
            className="text-xs font-medium text-accent-600 hover:underline dark:text-accent-400"
            onClick={onToggle}
          >
            {open ? "Hide" : "Details"}
          </button>
        </Td>
      </tr>
      {open && (
        <tr>
          <Td colSpan={7} className="bg-slate-50/80 dark:bg-white/[0.025]">
            <div className="grid gap-4 py-3 lg:grid-cols-3">
              <ClientBlock entry={entry} location={location} flag={flag} />
              <StateBlock title="Before" state={entry.before_state} />
              <StateBlock title="After" state={entry.after_state} />
            </div>
            <div className="flex flex-wrap gap-x-6 gap-y-1 pb-2 font-mono text-[11px] text-slate-500">
              {entry.request_id && <span>request {entry.request_id}</span>}
              {entry.session_id && <span>session {entry.session_id}</span>}
              {entry.entry_hash && <span className="break-all">entry_hash {entry.entry_hash}</span>}
            </div>
          </Td>
        </tr>
      )}
    </>
  );
}

function ClientBlock({
  entry,
  location,
  flag,
}: {
  entry: AuditEntry;
  location: string | null;
  flag: string;
}) {
  const rows: Array<[string, string]> = [
    ["IP address", entry.ip_address ?? "Not recorded"],
    ["Location", location ? `${flag} ${location}`.trim() : "Unknown"],
    ["Device", describeDevice(entry.user_agent)],
  ];
  return (
    <div>
      <div className="mb-1 text-xs font-semibold text-slate-500">Client</div>
      <dl className="space-y-1 rounded-lg bg-white p-3 text-xs ring-1 ring-slate-200 dark:bg-surface-950/60 dark:ring-white/[0.06]">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-3">
            <dt className="text-slate-500">{label}</dt>
            <dd className="text-right font-medium text-slate-800 dark:text-slate-100">{value}</dd>
          </div>
        ))}
        {entry.user_agent && (
          <div className="border-t border-slate-100 pt-1.5 font-mono text-[10px] break-all text-slate-400 dark:border-white/[0.06]">
            {entry.user_agent}
          </div>
        )}
      </dl>
    </div>
  );
}

function StateBlock({
  title,
  state,
}: {
  title: string;
  state: Record<string, unknown> | null;
}) {
  return (
    <div>
      <div className="mb-1 text-xs font-semibold text-slate-500">{title}</div>
      <pre className="max-h-48 overflow-auto rounded-lg bg-white p-3 text-xs ring-1 ring-slate-200 dark:bg-surface-950/60 dark:ring-white/[0.06]">
        {state ? JSON.stringify(state, null, 2) : "—"}
      </pre>
    </div>
  );
}
