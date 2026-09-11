// monitoring.v1 — what LLS published, presented without embellishment.
//
// Every value renders through `QualifiedValue`, so nothing on this screen can
// quietly become a zero. Every state badge reads what the source asserted; none
// is computed from the browser clock.
//
// What this page deliberately does NOT do:
//
//   - invent a freshness timer (monitoring.v1 has no validity horizon)
//   - compute a coverage percentage the source did not supply
//   - collapse `runtime` into LIVE / HISTORICAL
//   - infer a deployment tier from the source's `environment`
//   - offer any control that could change anything in LLS
//
// It is read-only, and there is no code path here that could make it otherwise.

import { clsx } from "clsx";
import { useMemo, useState } from "react";

import {
  CoverageBadge,
  EnvironmentBadge,
  FreshnessBadge,
  RuntimeBadges,
  TrustBadge,
} from "@/components/monitoring/FreshnessBadge";
import { QualifiedValue } from "@/components/monitoring/QualifiedValue";
import { Card, EmptyState, PageHeader, SkeletonRows, Table, Td } from "@/components/ui";
import { useMonitoringSources, useMonitoringState } from "@/lib/hooks";
import { formatInstant, isQualified, type MonitoringStateItem } from "@/lib/monitoring";

export function MonitoringPage() {
  const [messageType, setMessageType] = useState<string | null>(null);
  const state = useMonitoringState(messageType ? { message_type: messageType } : {});
  const sources = useMonitoringSources();

  const types = useMemo(
    () => [...new Set((state.data?.items ?? []).map((item) => item.message_type))].sort(),
    [state.data],
  );

  return (
    <div>
      <PageHeader
        title="LLS monitoring"
        description="Observations published by the LLS Monitoring Backend over monitoring.v1. Read-only."
      />

      {state.isLoading ? <SkeletonRows /> : null}

      {/* "No data" and "no monitoring database" are different facts, and a
          reader acting on them would do different things. */}
      {!state.isLoading && state.data && !state.data.configured ? (
        <Card className="mb-4 border-amber-300 bg-amber-50">
          <p className="text-sm font-semibold text-amber-900">
            Monitoring storage is not configured on this deployment
          </p>
          <p className="mt-1 text-xs text-amber-800">
            This is not the same as “nothing is wrong”. Nothing is being received or stored, so
            this page can say nothing about LLS at all.
          </p>
        </Card>
      ) : null}

      {state.data ? (
        <p className="mb-3 text-xs text-slate-500">
          Receiver deployment tier:{" "}
          <span className="font-mono text-slate-700">
            {state.data.receiver_deployment_environment}
          </span>
          {state.data.receiver_deployment_environment === "UNKNOWN" ? (
            <span className="ml-2 text-amber-700">
              not configured — never inferred from the source
            </span>
          ) : null}
        </p>
      ) : null}

      {types.length > 1 ? (
        <div className="mb-3 flex flex-wrap gap-2">
          <TypeChip label="all" active={messageType === null} onClick={() => setMessageType(null)} />
          {types.map((type) => (
            <TypeChip
              key={type}
              label={type}
              active={messageType === type}
              onClick={() => setMessageType(type)}
            />
          ))}
        </div>
      ) : null}

      {!state.isLoading && state.data?.configured && state.data.count === 0 ? (
        <EmptyState
          title="No monitoring messages received"
          body="The receiver is configured and reachable, but the LLS Monitoring Backend has not published anything for this deployment yet."
        />
      ) : null}

      <SourcesCard sources={sources.data} />

      {(state.data?.items ?? []).map((item) => (
        <MessageCard key={item.message_id} item={item} />
      ))}
    </div>
  );
}

function TypeChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "rounded px-2 py-1 font-mono text-xs ring-1",
        active
          ? "bg-slate-800 text-white ring-slate-800"
          : "bg-white text-slate-600 ring-slate-300 hover:bg-slate-50",
      )}
    >
      {label}
    </button>
  );
}

function SourcesCard({ sources }: { sources: ReturnType<typeof useMonitoringSources>["data"] }) {
  if (!sources || sources.length === 0) return null;
  return (
    <Card className="mt-4">
      <h3 className="mb-2 text-sm font-semibold text-slate-800">Delivery</h3>
      <p className="mb-2 text-xs text-slate-500">
        monitoring.v1 requires ordered acceptance. A refused message was never accepted and appears
        nowhere below as data — these counters exist so out-of-order delivery is visible.
      </p>
      <Table
        headers={[
          "Source",
          "Instance",
          "Last accepted",
          "Accepted",
          "Duplicate",
          "Refused (gap)",
          "Refused (old)",
          "Last seen",
        ]}
      >
        {sources.map((source) => (
          <tr key={`${source.source_id}:${source.source_instance}`}>
            <Td>{source.source_id}</Td>
            <Td className="font-mono text-xs">{source.source_instance}</Td>
            <Td className="font-mono text-xs">{source.last_accepted_sequence}</Td>
            <Td className="font-mono text-xs">{source.accepted_count}</Td>
            <Td className="font-mono text-xs">{source.duplicate_count}</Td>
            <Td>
              <span
                className={clsx(
                  "font-mono text-xs",
                  source.refused_gap_count > 0
                    ? "font-semibold text-rose-700"
                    : "text-slate-500",
                )}
              >
                {source.refused_gap_count}
              </span>
            </Td>
            <Td>
              <span
                className={clsx(
                  "font-mono text-xs",
                  source.refused_old_count > 0
                    ? "font-semibold text-rose-700"
                    : "text-slate-500",
                )}
              >
                {source.refused_old_count}
              </span>
            </Td>
            <Td className="font-mono text-xs">{formatInstant(source.last_seen_at)}</Td>
          </tr>
        ))}
      </Table>
    </Card>
  );
}

function MessageCard({ item }: { item: MonitoringStateItem }) {
  return (
    <Card className="mt-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs font-semibold text-slate-800">{item.message_type}</span>
        {item.capture_ref ? (
          <span className="font-mono text-[11px] text-slate-500">{item.capture_ref}</span>
        ) : null}
        <EnvironmentBadge sourceEnvironment={item.source_environment} />
        <TrustBadge trust={item.trust} />
        <CoverageBadge coverage={item.coverage} />
      </div>

      <FreshnessBadge freshness={item.freshness} className="mb-2" />

      <div className="mb-2">
        <span className="mr-2 text-xs text-slate-500">captures</span>
        <RuntimeBadges runtime={item.runtime} />
      </div>

      <div className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
        {Object.entries(item.payload).map(([key, value]) => (
          <PayloadEntry key={key} name={key} value={value} />
        ))}
      </div>

      <div className="mt-2 grid gap-x-6 gap-y-0.5 border-t border-slate-100 pt-2 text-[11px] text-slate-500 sm:grid-cols-2">
        {/* Distinct time domains. Collapsing them is how a delayed dashboard
            starts looking live. */}
        <span>source generated: {formatInstant(item.generated_at)}</span>
        <span>received: {formatInstant(item.received_at)}</span>
        <span>
          {item.source_id} / {item.source_instance} · seq {item.source_sequence}
        </span>
        <span className="truncate" title={item.message_id}>
          {item.message_id}
        </span>
      </div>
    </Card>
  );
}

function PayloadEntry({ name, value }: { name: string; value: unknown }) {
  if (isQualified(value)) {
    return (
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-xs text-slate-500">{name}</span>
        <QualifiedValue value={value} />
      </div>
    );
  }

  if (value && typeof value === "object" && !Array.isArray(value)) {
    const entries = Object.entries(value as Record<string, unknown>);
    return (
      <div className="sm:col-span-2">
        <span className="text-xs font-medium text-slate-600">{name}</span>
        <div className="ml-3 border-l border-slate-200 pl-3">
          {entries.map(([key, nested]) => (
            <PayloadEntry key={key} name={key} value={nested} />
          ))}
        </div>
      </div>
    );
  }

  if (Array.isArray(value)) {
    return (
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-xs text-slate-500">{name}</span>
        <span className="font-mono text-xs text-slate-600">{value.length} item(s)</span>
      </div>
    );
  }

  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-xs text-slate-500">{name}</span>
      <span className="font-mono text-xs text-slate-700">
        {value === null || value === undefined ? "NOT REPORTED" : String(value)}
      </span>
    </div>
  );
}

export default MonitoringPage;
