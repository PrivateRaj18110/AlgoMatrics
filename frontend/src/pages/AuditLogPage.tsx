import { useState } from "react";

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
import { useAuditEvents } from "@/lib/hooks";
import { dateTime } from "@/lib/format";
import type { AuditEntry } from "@/types/api";

export function AuditLogPage() {
  const [actionPrefix, setActionPrefix] = useState("");
  const [correlationId, setCorrelationId] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data, isLoading, isError, refetch } = useAuditEvents({
    actionPrefix: actionPrefix || undefined,
    correlationId: correlationId || undefined,
    resourceType: resourceType || undefined,
  });

  return (
    <div>
      <PageHeader
        title="Audit log"
        description="Immutable, hash-chained organization activity for security and operational review"
      />
      <Card>
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          <Field label="Action prefix">
            <Input
              value={actionPrefix}
              onChange={(event) => setActionPrefix(event.target.value)}
              placeholder="orders., brokers., billing."
            />
          </Field>
          <Field label="Resource type">
            <Input
              value={resourceType}
              onChange={(event) => setResourceType(event.target.value)}
              placeholder="user, order, strategy"
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
        {isLoading ? (
          <SkeletonRows rows={8} cols={5} />
        ) : isError ? (
          <EmptyState
            title="Audit events could not be loaded"
            action={
              <button className="text-sm text-accent-500 hover:underline" onClick={() => refetch()}>
                Retry
              </button>
            }
          />
        ) : !data || data.items.length === 0 ? (
          <EmptyState title="No matching audit events" />
        ) : (
          <Table headers={["Time", "Action", "Resource", "Actor", "Chain", ""]}>
            {data.items.map((entry) => (
              <AuditRow
                key={entry.id}
                entry={entry}
                open={expanded === entry.id}
                onToggle={() => setExpanded(expanded === entry.id ? null : entry.id)}
              />
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

function AuditRow({
  entry,
  open,
  onToggle,
}: {
  entry: AuditEntry;
  open: boolean;
  onToggle: () => void;
}) {
  const hasDetail = Boolean(entry.before_state || entry.after_state);
  return (
    <>
      <tr>
        <Td className="whitespace-nowrap">{dateTime(entry.occurred_at)}</Td>
        <Td className="font-medium">{entry.action}</Td>
        <Td>
          <div>{entry.resource_type}</div>
          <div className="max-w-52 truncate text-xs text-slate-500">{entry.resource_id}</div>
        </Td>
        <Td>
          <Badge color={entry.actor_type === "user" ? "blue" : "slate"}>{entry.actor_type}</Badge>
          {entry.actor_user_id && (
            <div className="mt-1 max-w-36 truncate text-xs text-slate-500">
              {entry.actor_user_id}
            </div>
          )}
        </Td>
        <Td className="text-xs text-slate-500">
          {entry.sequence !== null && <div>#{entry.sequence}</div>}
          {entry.correlation_id && (
            <div className="max-w-40 truncate" title={entry.correlation_id}>
              {entry.correlation_id}
            </div>
          )}
        </Td>
        <Td>
          {hasDetail && (
            <button className="text-xs text-accent-500 hover:underline" onClick={onToggle}>
              {open ? "Hide" : "Details"}
            </button>
          )}
        </Td>
      </tr>
      {open && hasDetail && (
        <tr>
          <Td colSpan={6} className="bg-slate-50 dark:bg-slate-900/40">
            <div className="grid gap-4 py-2 sm:grid-cols-2">
              <StateBlock title="Before" state={entry.before_state} />
              <StateBlock title="After" state={entry.after_state} />
            </div>
            {entry.entry_hash && (
              <div className="pb-2 font-mono text-[11px] text-slate-400">
                entry_hash: {entry.entry_hash}
              </div>
            )}
          </Td>
        </tr>
      )}
    </>
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
      <pre className="max-h-48 overflow-auto rounded bg-slate-100 p-2 text-xs dark:bg-slate-800">
        {state ? JSON.stringify(state, null, 2) : "—"}
      </pre>
    </div>
  );
}
