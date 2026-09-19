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
import { type ReactNode, useMemo, useState } from "react";

import { Glyph, type GlyphName } from "@/components/icons";
import {
  CoverageBadge,
  EnvironmentBadge,
  FreshnessBadge,
  RuntimeBadges,
  TrustBadge,
} from "@/components/monitoring/FreshnessBadge";
import { QualifiedValue } from "@/components/monitoring/QualifiedValue";
import { Card, EmptyState, PageHeader, SkeletonRows, Table, Td, surface } from "@/components/ui";
import { useMonitoringSources, useMonitoringState } from "@/lib/hooks";
import { formatInstant, isQualified, type MonitoringStateItem } from "@/lib/monitoring";
import { dateTimeLabel } from "@/lib/wallboard";

export function MonitoringPage() {
  const [messageType, setMessageType] = useState<string | null>(null);
  const state = useMonitoringState(messageType ? { message_type: messageType } : {});
  const sources = useMonitoringSources();

  const isUnavailable = Boolean(state.isError || (!state.data && sources.isError));
  const lastUpdate =
    state.dataUpdatedAt && state.dataUpdatedAt > 0
      ? dateTimeLabel(new Date(state.dataUpdatedAt).toISOString())
      : "UNKNOWN";

  const types = useMemo(
    () => [...new Set((state.data?.items ?? []).map((item) => item.message_type))].sort(),
    [state.data],
  );

  return (
    <div className="am-fade-in">
      <PageHeader
        eyebrow="Operations · monitoring.v1"
        title="LLS monitoring"
        description="Observations published by the LLS Monitoring Backend over monitoring.v1. Read-only."
        actions={
          <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-300">
            <Glyph name="eye" className="size-3.5" />
            Read-only view
          </span>
        }
      />

      {state.isLoading && !state.data && !isUnavailable ? <SkeletonRows /> : null}

      {isUnavailable ? (
        <Banner tone="rose" icon="alert" title="Monitoring service is not currently available">
          <p>
            The monitoring API could not be reached or returned an error. Observations cannot be
            loaded at this time.
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-x-6 gap-y-1 font-mono text-xs">
            <span>
              API: <span className="font-semibold text-rose-700 dark:text-rose-300">unavailable</span>
            </span>
            <span>
              Last successful update:{" "}
              <span className="font-semibold text-slate-800 dark:text-slate-100">{lastUpdate}</span>
            </span>
          </div>
        </Banner>
      ) : null}

      {/* "No data" and "no monitoring database" are different facts, and a
          reader acting on them would do different things. */}
      {!isUnavailable && !state.isLoading && state.data && !state.data.configured ? (
        <Banner
          tone="amber"
          icon="database"
          title="Monitoring storage is not configured on this deployment"
        >
          This is not the same as “nothing is wrong”. Nothing is being received or stored, so this
          page can say nothing about LLS at all.
        </Banner>
      ) : null}

      {state.data ? (
        // Every figure here is one the receiver reported as-is; none is derived.
        <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Fact icon="server" label="Receiver deployment tier">
            <span className="font-mono">{state.data.receiver_deployment_environment}</span>
            {state.data.receiver_deployment_environment === "UNKNOWN" ? (
              <span className="mt-1 block text-xs font-normal text-amber-700 dark:text-amber-400">
                not configured — never inferred from the source
              </span>
            ) : null}
          </Fact>
          <Fact icon="signal" label="Sources seen">
            {sources.data ? sources.data.length : "NOT LOADED"}
          </Fact>
          <Fact icon="inbox" label="Messages projected">
            {state.data.count}
          </Fact>
          <Fact icon="clock" label="Fetched by this browser">
            <span className="font-mono text-sm">{lastUpdate}</span>
          </Fact>
        </div>
      ) : null}

      {types.length > 1 ? (
        <div
          className="mb-5 inline-flex max-w-full flex-wrap gap-1 rounded-xl border border-slate-200 bg-slate-100/80 p-1 dark:border-white/[0.07] dark:bg-white/[0.03]"
          aria-label="Filter by message type"
        >
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

      {!isUnavailable && !state.isLoading && state.data?.configured && state.data.count === 0 ? (
        <div className={surface}>
          <EmptyState
            icon={<Glyph name="inbox" className="size-5" />}
            title="No monitoring messages received"
            body="The receiver is configured and reachable, but the LLS Monitoring Backend has not published anything for this deployment yet."
          />
        </div>
      ) : null}

      {!isUnavailable || state.data ? (
        <div className="space-y-5">
          <SourcesCard sources={sources.data} />
          {(state.data?.items ?? []).map((item) => (
            <MessageCard key={item.message_id} item={item} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

const BANNER_TONE = {
  rose: {
    box: "border-rose-200 bg-rose-50 text-slate-700 dark:border-rose-500/25 dark:bg-rose-500/[0.07] dark:text-slate-300",
    icon: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300",
    title: "text-rose-900 dark:text-rose-200",
  },
  amber: {
    box: "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-500/25 dark:bg-amber-500/[0.07] dark:text-amber-100/80",
    icon: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
    title: "text-amber-950 dark:text-amber-200",
  },
} as const;

function Banner({
  tone,
  icon,
  title,
  children,
}: {
  tone: keyof typeof BANNER_TONE;
  icon: GlyphName;
  title: string;
  children: ReactNode;
}) {
  const palette = BANNER_TONE[tone];
  return (
    <div className={clsx("mb-6 flex gap-3.5 rounded-2xl border p-4 text-sm", palette.box)}>
      <span
        className={clsx("flex size-9 shrink-0 items-center justify-center rounded-xl", palette.icon)}
        aria-hidden
      >
        <Glyph name={icon} />
      </span>
      <div className="min-w-0 text-xs leading-relaxed">
        <h3 className={clsx("mb-0.5 text-sm font-semibold", palette.title)}>{title}</h3>
        {children}
      </div>
    </div>
  );
}

function Fact({ icon, label, children }: { icon: GlyphName; label: string; children: ReactNode }) {
  return (
    <div className={clsx(surface, "flex items-start gap-3.5 p-4")}>
      <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent-500/10 text-accent-600 ring-1 ring-accent-500/20 ring-inset dark:text-accent-300">
        <Glyph name={icon} />
      </span>
      <div className="min-w-0">
        <p className="text-xs font-medium text-slate-500 dark:text-slate-400">{label}</p>
        <div className="mt-0.5 text-lg font-semibold tracking-tight text-slate-900 tabular-nums dark:text-white">
          {children}
        </div>
      </div>
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
      aria-pressed={active}
      className={clsx(
        "rounded-lg px-3 py-1.5 font-mono text-xs transition-colors",
        active
          ? "bg-white text-slate-900 shadow-sm dark:bg-accent-500/15 dark:text-accent-200 dark:shadow-[inset_0_0_0_1px_rgba(61,208,234,0.3)]"
          : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100",
      )}
    >
      {label}
    </button>
  );
}

function Counter({ value, alarm }: { value: number; alarm?: boolean }) {
  return (
    <span
      className={clsx(
        "font-mono text-xs",
        alarm && value > 0
          ? "rounded-md bg-rose-500/10 px-1.5 py-0.5 font-semibold text-rose-700 dark:text-rose-300"
          : "text-slate-600 dark:text-slate-400",
      )}
    >
      {value}
    </span>
  );
}

function SourcesCard({ sources }: { sources: ReturnType<typeof useMonitoringSources>["data"] }) {
  if (!sources || sources.length === 0) return null;
  return (
    <Card
      title="Delivery"
      subtitle="Per-source ordered-acceptance counters kept by this receiver"
      icon={<Glyph name="signal" className="size-3.5" />}
      bodyClassName="px-2 pb-2 pt-3"
    >
      <p className="mb-3 px-3 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
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
            <Td className="font-medium text-slate-800 dark:text-slate-100">{source.source_id}</Td>
            <Td className="font-mono text-xs text-slate-600 dark:text-slate-300">
              {source.source_instance}
            </Td>
            <Td className="font-mono text-xs text-slate-600 dark:text-slate-300">
              {source.last_accepted_sequence}
            </Td>
            <Td>
              <Counter value={source.accepted_count} />
            </Td>
            <Td>
              <Counter value={source.duplicate_count} />
            </Td>
            <Td>
              <Counter value={source.refused_gap_count} alarm />
            </Td>
            <Td>
              <Counter value={source.refused_old_count} alarm />
            </Td>
            <Td className="font-mono text-xs text-slate-500 dark:text-slate-400">
              {formatInstant(source.last_seen_at)}
            </Td>
          </tr>
        ))}
      </Table>
    </Card>
  );
}

function MetaItem({ label, children, title }: { label: string; children: ReactNode; title?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] font-semibold tracking-[0.14em] text-slate-400 uppercase dark:text-slate-500">
        {label}
      </dt>
      <dd className="mt-0.5 truncate font-mono text-[11px] text-slate-600 dark:text-slate-300" title={title}>
        {children}
      </dd>
    </div>
  );
}

function MessageCard({ item }: { item: MonitoringStateItem }) {
  return (
    <section className={clsx(surface, "overflow-hidden")}>
      <header className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-5 py-3.5 dark:border-white/[0.06]">
        <span className="mr-1 font-mono text-sm font-semibold text-slate-900 dark:text-white">
          {item.message_type}
        </span>
        {item.capture_ref ? (
          <span className="font-mono text-[11px] text-slate-500 dark:text-slate-400">
            {item.capture_ref}
          </span>
        ) : null}
        <span className="flex flex-1 flex-wrap items-center justify-end gap-1.5">
          <EnvironmentBadge sourceEnvironment={item.source_environment} />
          <TrustBadge trust={item.trust} />
          <CoverageBadge coverage={item.coverage} />
        </span>
      </header>

      <div className="space-y-4 p-5">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <FreshnessBadge freshness={item.freshness} />
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-500 dark:text-slate-400">captures</span>
            <RuntimeBadges runtime={item.runtime} />
          </div>
        </div>

        <div className="grid gap-x-8 gap-y-1.5 rounded-xl border border-slate-100 bg-slate-50/60 p-4 sm:grid-cols-2 dark:border-white/[0.05] dark:bg-white/[0.015]">
          {Object.entries(item.payload).map(([key, value]) => (
            <PayloadEntry key={key} name={key} value={value} />
          ))}
        </div>

        {/* Distinct time domains. Collapsing them is how a delayed dashboard
            starts looking live. */}
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetaItem label="Source generated">{formatInstant(item.generated_at)}</MetaItem>
          <MetaItem label="Received">{formatInstant(item.received_at)}</MetaItem>
          <MetaItem label="Source / instance">
            {item.source_id} / {item.source_instance} · seq {item.source_sequence}
          </MetaItem>
          <MetaItem label="Message id" title={item.message_id}>
            {item.message_id}
          </MetaItem>
        </dl>
      </div>
    </section>
  );
}

function PayloadEntry({ name, value }: { name: string; value: unknown }) {
  if (isQualified(value)) {
    return (
      <div className="flex min-h-7 items-center justify-between gap-3 border-b border-dashed border-slate-200/70 py-0.5 last:border-0 dark:border-white/[0.05]">
        <span className="text-xs text-slate-500 dark:text-slate-400">{name}</span>
        <QualifiedValue value={value} />
      </div>
    );
  }

  if (value && typeof value === "object" && !Array.isArray(value)) {
    const entries = Object.entries(value as Record<string, unknown>);
    return (
      <div className="py-1 sm:col-span-2">
        <span className="text-xs font-semibold text-slate-700 dark:text-slate-200">{name}</span>
        <div className="mt-1 ml-1 grid gap-x-8 border-l border-slate-200 pl-3 sm:grid-cols-2 dark:border-white/10">
          {entries.map(([key, nested]) => (
            <PayloadEntry key={key} name={key} value={nested} />
          ))}
        </div>
      </div>
    );
  }

  if (Array.isArray(value)) {
    return (
      <div className="flex min-h-7 items-center justify-between gap-3 py-0.5">
        <span className="text-xs text-slate-500 dark:text-slate-400">{name}</span>
        <span className="font-mono text-xs text-slate-600 dark:text-slate-300">{value.length} item(s)</span>
      </div>
    );
  }

  return (
    <div className="flex min-h-7 items-center justify-between gap-3 py-0.5">
      <span className="text-xs text-slate-500 dark:text-slate-400">{name}</span>
      <span className="font-mono text-xs text-slate-700 dark:text-slate-200">
        {value === null || value === undefined ? "NOT REPORTED" : String(value)}
      </span>
    </div>
  );
}

export default MonitoringPage;
