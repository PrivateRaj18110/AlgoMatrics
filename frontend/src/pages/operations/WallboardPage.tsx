/**
 * Operations wallboard — one screen, no scrolling, meant to be left running.
 *
 * Read-only. No order, strategy, risk or broker control exists on this page, and
 * a test asserts that.
 *
 * The governing rule is that this board must never claim to know something it
 * does not. Concretely, that means several panels here are deliberately UNKNOWN
 * even though a number could be rendered:
 *
 * * **Database** has no health signal in the API. An HTTP 200 from an endpoint
 *   that happens to touch Postgres is not a database health check, so the panel
 *   says UNKNOWN rather than inferring one.
 * * **Process memory, queue workers, feed counts, ingestion latency** have no
 *   authoritative source. `SystemHealthPoint` will happily return
 *   `api_success_pct = 100.0` and `status = "STABLE"` for an agent that reported
 *   nothing at all — those are Pydantic defaults, not measurements — so this page
 *   reads the nullable twins (`api_success_rate`, `cpu_usage`) and treats their
 *   absence as UNKNOWN. See `preferNullable` in `@/lib/wallboard`.
 * * **Incidents** distinguish "the store answered and there are none" from "the
 *   store did not answer". Only the first may print NO ACTIVE INCIDENTS.
 *
 * Tenancy: every query goes through the existing platform hooks, which are
 * gated on an active organisation and authorised server-side. Nothing here
 * passes an organisation as a parameter, and no filtering in this file is
 * load-bearing for security.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router";

import {
  useMarketQuotes,
  useMonitoringSources,
  useMonitoringState,
  useOpsAlerts,
  useOpsMachines,
  useOpsOverview,
  useOpsSystemHealth,
} from "@/lib/hooks";
import { getIndianMarketDaySchedule } from "@/lib/marketSessions";
import { readFreshness } from "@/lib/monitoring";
import {
  clockLabel,
  connectionState,
  dateTimeLabel,
  known,
  lastSuccessfulUpdate,
  latestInstant,
  markStaleOnError,
  preferNullable,
  readEstablishedCount,
  readingText,
  rollUp,
  unknown,
  type OperationalState,
  type QuerySnapshot,
  type Reading,
} from "@/lib/wallboard";
import type { OpsEvent, OpsMachine } from "@/types/api";

/* ------------------------------ presentation ------------------------------ */

const STATE_STYLE: Record<OperationalState, { chip: string; bar: string }> = {
  HEALTHY: { chip: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/40", bar: "bg-emerald-400" },
  DEGRADED: { chip: "bg-orange-500/15 text-orange-300 ring-orange-500/40", bar: "bg-orange-400" },
  STALE: { chip: "bg-sky-500/15 text-sky-300 ring-sky-500/40", bar: "bg-sky-400" },
  CRITICAL: { chip: "bg-rose-500/20 text-rose-300 ring-rose-500/50", bar: "bg-rose-400" },
  // Amber, never grey-green. Not being able to say is not the same as saying it is fine.
  UNKNOWN: { chip: "bg-amber-500/15 text-amber-300 ring-amber-500/40", bar: "bg-amber-400" },
};

/** State as text, always — colour alone must never carry the meaning. */
function StateChip({ state, className = "" }: { state: OperationalState; className?: string }) {
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[clamp(9px,0.65vw,13px)] font-bold tracking-widest ring-1 ${STATE_STYLE[state].chip} ${className}`}
    >
      {state}
    </span>
  );
}

function Panel({
  title,
  state,
  children,
}: {
  title: string;
  state?: OperationalState;
  children: React.ReactNode;
}) {
  return (
    <section className="flex min-h-0 min-w-0 flex-col rounded-lg bg-[#0d121b] p-2 ring-1 ring-slate-800">
      <h2 className="mb-1.5 flex shrink-0 items-center justify-between gap-2 font-mono text-[clamp(9px,0.62vw,12px)] font-semibold tracking-[0.18em] text-slate-500">
        <span className="truncate">{title}</span>
        {state ? <StateChip state={state} /> : null}
      </h2>
      <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
    </section>
  );
}

/** A large status card for row 1. */
function StatusCard({
  label,
  reading,
  format,
}: {
  label: string;
  reading: Reading<string>;
  format?: string;
}) {
  const style = STATE_STYLE[reading.state];
  return (
    <section className="flex min-w-0 flex-col justify-between rounded-lg bg-[#0d121b] p-2 ring-1 ring-slate-800">
      <div className={`mb-1 h-0.5 w-full rounded-full ${style.bar}`} aria-hidden="true" />
      <h2 className="truncate font-mono text-[clamp(9px,0.62vw,12px)] font-semibold tracking-[0.16em] text-slate-500">
        {label}
      </h2>
      <p className="mt-1 truncate font-mono text-[clamp(13px,1.35vw,26px)] font-bold text-slate-100">
        {reading.state === "UNKNOWN" ? "UNKNOWN" : (reading.value ?? "UNKNOWN")}
      </p>
      <div className="mt-1 flex items-baseline justify-between gap-2">
        <StateChip state={reading.state} />
        {format ? (
          <span className="truncate font-mono text-[clamp(8px,0.55vw,11px)] text-slate-500">
            {format}
          </span>
        ) : null}
      </div>
      {reading.detail ? (
        <p className="mt-1 line-clamp-2 font-mono text-[clamp(8px,0.55vw,11px)] leading-tight text-slate-500">
          {reading.detail}
        </p>
      ) : null}
    </section>
  );
}

/** One label/value pair inside a panel. Values print UNKNOWN, never a bare 0. */
function Metric({
  label,
  reading,
  format = (value: number) => String(value),
}: {
  label: string;
  reading: Reading<number | string>;
  format?: (value: number) => string;
}) {
  const text =
    reading.state === "UNKNOWN" || reading.value === null
      ? "UNKNOWN"
      : typeof reading.value === "number"
        ? readingText(reading as Reading<number>, format)
        : reading.value;
  const tone = reading.state === "UNKNOWN" ? "text-amber-300" : "text-slate-100";
  return (
    <div className="flex min-w-0 items-baseline justify-between gap-2 border-b border-slate-800/60 py-[2px] last:border-b-0">
      <dt className="truncate font-mono text-[clamp(8px,0.58vw,11px)] tracking-wide text-slate-500">
        {label}
      </dt>
      <dd
        className={`shrink-0 font-mono text-[clamp(9px,0.72vw,14px)] font-semibold ${tone}`}
        title={reading.detail ?? undefined}
      >
        {text}
      </dd>
    </div>
  );
}

/* -------------------------------- the page -------------------------------- */

function snapshot(query: {
  isError: boolean;
  isSuccess: boolean;
  dataUpdatedAt: number;
  data?: unknown;
}): QuerySnapshot {
  return {
    isError: query.isError,
    isSuccess: query.isSuccess,
    dataUpdatedAt: query.dataUpdatedAt,
    hasData: query.data !== undefined,
  };
}

function maxNullable(values: readonly (number | null | undefined)[]): number | null {
  const usable = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  return usable.length === 0 ? null : Math.max(...usable);
}

function severityRank(event: OpsEvent): number {
  const raw = (event.severity ?? event.level ?? "").toLowerCase();
  if (raw.includes("critical") || raw.includes("fatal")) return 4;
  if (raw.includes("error")) return 3;
  if (raw.includes("warn")) return 2;
  return 1;
}

function severityLabel(event: OpsEvent): string {
  const rank = severityRank(event);
  return rank === 4 ? "CRITICAL" : rank === 3 ? "ERROR" : rank === 2 ? "WARNING" : "INFO";
}

export function WallboardPage() {
  const overview = useOpsOverview();
  const machines = useOpsMachines();
  const alerts = useOpsAlerts();
  const health = useOpsSystemHealth({}, { refetchInterval: 15_000 });
  const monitoringState = useMonitoringState({ limit: 200 });
  const monitoringSources = useMonitoringSources();
  const quotes = useMarketQuotes();

  const [now, setNow] = useState(() => new Date());
  const [fullscreen, setFullscreen] = useState(false);
  const [chromeHidden, setChromeHidden] = useState(false);

  // A single interval for the wall clock, cleared on unmount. Data refresh is
  // React Query's job: it serialises its own refetches, so a slow response
  // cannot build a backlog the way a bare setInterval(fetch) would.
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const sync = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", sync);
    sync();
    return () => document.removeEventListener("fullscreenchange", sync);
  }, []);

  const toggleFullscreen = useCallback(() => {
    // Absence of the API is normal (iOS Safari); the display-mode toggle below
    // still works, so this degrades rather than failing.
    if (document.fullscreenElement) {
      void document.exitFullscreen?.();
      return;
    }
    void document.documentElement.requestFullscreen?.().catch(() => undefined);
  }, []);

  const queries = useMemo(
    () => [
      snapshot(overview),
      snapshot(machines),
      snapshot(alerts),
      snapshot(health),
      snapshot(monitoringState),
      snapshot(monitoringSources),
      snapshot(quotes),
    ],
    [overview, machines, alerts, health, monitoringState, monitoringSources, quotes],
  );

  const connection = connectionState(queries);
  const lastUpdate = lastSuccessfulUpdate(queries);

  /* --- telemetry availability: the gate that keeps zeros honest ----------- */

  const telemetryConfigured = overview.isSuccess && overview.data?.telemetry_configured === true;
  const awaitingTelemetry = overview.data?.awaiting_telemetry !== false;
  const telemetryEstablished = telemetryConfigured && !awaitingTelemetry;

  const machineRows: OpsMachine[] = useMemo(() => machines.data ?? [], [machines.data]);

  /* --- row 1: primary system status -------------------------------------- */

  const systemCard: Reading<string> = useMemo(() => {
    if (!overview.isSuccess) return unknown("operations overview unavailable");
    if (!telemetryConfigured) return unknown("telemetry store not configured");
    if (awaitingTelemetry) return unknown("awaiting first telemetry");
    const total = overview.data?.machine_count ?? null;
    const online = overview.data?.online_machines ?? null;
    if (total === null || online === null) return unknown("machine counts not reported");
    if (total === 0) return unknown("no machines registered");
    if (online === total) return known("HEALTHY", `${online}/${total} ONLINE`);
    if (online === 0) return known("CRITICAL", `0/${total} ONLINE`, "no machine is reporting");
    return known("DEGRADED", `${online}/${total} ONLINE`);
  }, [overview.isSuccess, overview.data, telemetryConfigured, awaitingTelemetry]);

  const marketAsOf = latestInstant((quotes.data ?? []).map((row) => row.as_of));
  const marketCard: Reading<string> = useMemo(() => {
    if (!quotes.isSuccess && !quotes.data) return unknown("market-info unavailable");
    const count = quotes.data?.length ?? 0;
    if (count === 0) return unknown("no instruments in universe");
    if (marketAsOf.state === "UNKNOWN") {
      return unknown("provider returned no market timestamp");
    }
    // Never LIVE because the page refreshed — this states what the provider
    // stamped and what the exchange calendar says, and nothing more.
    return known("HEALTHY", `${count} QUOTED`, `provider as of ${clockLabel(marketAsOf.value)}`);
  }, [quotes.isSuccess, quotes.data, marketAsOf.state, marketAsOf.value]);

  const receiverCard: Reading<string> = useMemo(() => {
    if (!monitoringState.isSuccess && !monitoringState.data) {
      return unknown("monitoring read API unavailable");
    }
    if (monitoringState.data?.configured !== true) {
      return unknown("receiver database not configured");
    }
    const count = monitoringState.data?.count ?? 0;
    if (count === 0) {
      // Configured and empty is an established fact, not a missing one — but it
      // is still not evidence that the receiver is healthy.
      return unknown("configured; no messages received");
    }
    return known("HEALTHY", `${count} OBSERVATIONS`);
  }, [monitoringState.isSuccess, monitoringState.data]);

  // The canonical example of what this board must not do: a 200 from an
  // endpoint is not a database health check.
  const databaseCard: Reading<string> = unknown("no database health signal is exposed by the API");

  const apiCard: Reading<string> = useMemo(() => {
    if (connection === "CONNECTED") {
      return known("HEALTHY", "REACHABLE", "from this browser only");
    }
    if (connection === "DEGRADED") {
      return known("DEGRADED", "REQUESTS FAILING", "from this browser only");
    }
    return unknown("no request has completed yet");
  }, [connection]);

  const pipelineCard: Reading<string> = useMemo(() => {
    if (!machines.isSuccess && !machines.data) return unknown("machine telemetry unavailable");
    const depth = maxNullable(machineRows.map((machine) => machine.queue_depth));
    const transports = machineRows
      .map((machine) => machine.transport_state)
      .filter((value): value is string => Boolean(value));
    if (depth === null && transports.length === 0) return unknown("no pipeline metric reported");
    if (depth === null) return known("HEALTHY", transports[0].toUpperCase(), "transport state only");
    return known(depth > 0 ? "DEGRADED" : "HEALTHY", `QUEUE ${depth}`, transports[0]?.toUpperCase());
  }, [machines.isSuccess, machines.data, machineRows]);

  const overall = rollUp([
    systemCard.state,
    marketCard.state,
    receiverCard.state,
    databaseCard.state,
    apiCard.state,
    pipelineCard.state,
  ]);

  /* --- row 3: monitoring.v1 ---------------------------------------------- */

  const sourceRows = monitoringSources.data ?? [];
  const sourcesEstablished = monitoringSources.isSuccess;
  const sum = (pick: (row: (typeof sourceRows)[number]) => number | null | undefined) =>
    readEstablishedCount(
      sourceRows.reduce((total, row) => total + (pick(row) ?? 0), 0),
      sourcesEstablished,
      "monitoring sources did not answer",
    );

  const freshnessCounts = useMemo(() => {
    const items = monitoringState.data?.items ?? [];
    let unknownStates = 0;
    let staleStates = 0;
    for (const item of items) {
      const state = readFreshness(item.freshness).source;
      if (state === "UNKNOWN") unknownStates += 1;
      if (state === "STALE") staleStates += 1;
    }
    return { unknownStates, staleStates, established: monitoringState.isSuccess };
  }, [monitoringState.data, monitoringState.isSuccess]);

  /* --- row 5: incidents --------------------------------------------------- */

  const incidents = useMemo(() => (alerts.data ?? []).slice().sort((a, b) => severityRank(b) - severityRank(a)), [alerts.data]);
  // An empty list only means "no incidents" when the store was actually able to
  // answer. Unconfigured telemetry also returns [], and the two must not look
  // the same.
  const incidentStateKnown = alerts.isSuccess && telemetryConfigured;

  /* --- market session ----------------------------------------------------- */

  const schedule = getIndianMarketDaySchedule(now);
  const sessionLabel =
    schedule.type === "open"
      ? "SCHEDULED TRADING DAY"
      : schedule.type === "weekend"
        ? "CLOSED — WEEKEND"
        : schedule.reason.toUpperCase();

  const environment = monitoringState.data?.receiver_deployment_environment ?? null;
  const build = (import.meta.env.VITE_APP_VERSION as string | undefined) ?? null;

  return (
    <div
      className={`flex h-[100dvh] w-full flex-col gap-1.5 overflow-hidden bg-[#05070b] p-1.5 text-slate-200 ${
        chromeHidden ? "fixed inset-0 z-50" : ""
      }`}
      data-testid="wallboard"
    >
      {/* ------------------------------ top bar ------------------------------ */}
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-x-4 gap-y-1 rounded-lg bg-[#0d121b] px-3 py-1.5 ring-1 ring-slate-800">
        <div className="flex items-center gap-3">
          <h1 className="font-mono text-[clamp(12px,1.1vw,22px)] font-bold tracking-[0.2em] text-slate-100">
            ALGOMATRIC SYSTEM HEALTH
          </h1>
          <StateChip state={overall} className="!text-[clamp(10px,0.85vw,16px)]" />
        </div>
        <dl className="flex flex-wrap items-baseline gap-x-5 gap-y-0.5 font-mono text-[clamp(8px,0.6vw,12px)]">
          <div className="flex items-baseline gap-1.5">
            <dt className="text-slate-500">ENVIRONMENT</dt>
            <dd className={environment ? "text-slate-100" : "text-amber-300"}>
              {environment ?? "UNKNOWN"}
            </dd>
          </div>
          <div className="flex items-baseline gap-1.5">
            <dt className="text-slate-500">LAST UPDATE</dt>
            <dd className="text-slate-100">
              {lastUpdate.state === "UNKNOWN" ? "UNKNOWN" : clockLabel(lastUpdate.value)}
            </dd>
          </div>
          <div className="flex items-baseline gap-1.5">
            <dt className="text-slate-500">CONNECTION</dt>
            <dd className={connection === "CONNECTED" ? "text-emerald-300" : "text-amber-300"}>
              {connection === "DEGRADED" ? "CONNECTION DEGRADED" : connection}
            </dd>
          </div>
          <div className="flex items-baseline gap-1.5">
            <dt className="text-slate-500">AUTO REFRESH</dt>
            <dd className="text-slate-100">10–20s</dd>
          </div>
        </dl>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setChromeHidden((value) => !value)}
            className="rounded px-2 py-1 font-mono text-[clamp(8px,0.6vw,12px)] tracking-widest text-slate-300 ring-1 ring-slate-700 hover:bg-slate-800"
          >
            {chromeHidden ? "EXIT DISPLAY MODE" : "DISPLAY MODE"}
          </button>
          <button
            type="button"
            onClick={toggleFullscreen}
            className="rounded px-2 py-1 font-mono text-[clamp(8px,0.6vw,12px)] tracking-widest text-slate-300 ring-1 ring-slate-700 hover:bg-slate-800"
          >
            {fullscreen ? "EXIT FULLSCREEN" : "FULLSCREEN"}
          </button>
          <Link
            to="/app/dashboard"
            className="rounded px-2 py-1 font-mono text-[clamp(8px,0.6vw,12px)] tracking-widest text-slate-400 ring-1 ring-slate-700 hover:bg-slate-800"
          >
            EXIT
          </Link>
        </div>
      </header>

      {/* ------------------------- row 1: status cards ----------------------- */}
      <div className="grid shrink-0 grid-cols-2 gap-1.5 sm:grid-cols-3 xl:grid-cols-6">
        <StatusCard label="SYSTEM" reading={systemCard} />
        <StatusCard label="MARKET FEEDS" reading={marketCard} />
        <StatusCard label="MONITORING RECEIVER" reading={receiverCard} />
        <StatusCard label="DATABASE" reading={databaseCard} />
        <StatusCard label="API" reading={apiCard} />
        <StatusCard label="DATA PIPELINE" reading={pipelineCard} />
      </div>

      {/* --------------------- rows 2-4: detail panels ----------------------- */}
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-1.5 md:grid-cols-2 xl:grid-cols-3">
        <Panel title="MARKET / FEED HEALTH" state={marketCard.state}>
          <dl>
            <Metric
              label="SECURITIES QUOTED"
              reading={readEstablishedCount(quotes.data?.length, quotes.isSuccess, "market-info did not answer")}
            />
            <Metric
              label="LAST MARKET UPDATE"
              reading={
                marketAsOf.state === "UNKNOWN"
                  ? marketAsOf
                  : known("HEALTHY", dateTimeLabel(marketAsOf.value))
              }
            />
            <Metric label="MARKET SESSION" reading={known("HEALTHY", sessionLabel)} />
            <Metric label="FEEDS CONNECTED" reading={unknown("no feed-health API exists")} />
            <Metric label="FEEDS DEGRADED" reading={unknown("no feed-health API exists")} />
            <Metric label="FEED ERRORS" reading={unknown("feed error telemetry is not collected")} />
            <Metric label="INGESTION RATE" reading={unknown("not measured by the platform")} />
          </dl>
        </Panel>

        <Panel title="MONITORING / LLS OBSERVABILITY" state={receiverCard.state}>
          <dl>
            <Metric
              label="PUBLISHER SOURCES"
              reading={readEstablishedCount(sourceRows.length, sourcesEstablished, "monitoring sources did not answer")}
            />
            <Metric label="ACCEPTED" reading={sum((row) => row.accepted_count)} />
            <Metric label="DUPLICATES" reading={sum((row) => row.duplicate_count)} />
            <Metric label="REFUSED — SEQUENCE GAP" reading={sum((row) => row.refused_gap_count)} />
            <Metric label="REFUSED — OLD SEQUENCE" reading={sum((row) => row.refused_old_count)} />
            <Metric
              label="LATEST EVIDENCE"
              reading={(() => {
                const latest = latestInstant(sourceRows.map((row) => row.last_seen_at));
                return latest.state === "UNKNOWN" || !sourcesEstablished
                  ? unknown("no accepted message recorded")
                  : known("HEALTHY", dateTimeLabel(latest.value));
              })()}
            />
            <Metric
              label="SOURCE FRESHNESS = STALE"
              reading={readEstablishedCount(freshnessCounts.staleStates, freshnessCounts.established, "monitoring state did not answer")}
            />
            <Metric
              label="SOURCE FRESHNESS = UNKNOWN"
              reading={readEstablishedCount(freshnessCounts.unknownStates, freshnessCounts.established, "monitoring state did not answer")}
            />
            <Metric label="QUARANTINED" reading={unknown("not exposed on the platform read surface")} />
            <Metric label="INGESTION LATENCY" reading={unknown("contract defines none; not inferred")} />
          </dl>
        </Panel>

        <Panel title="INFRASTRUCTURE" state={pipelineCard.state}>
          <dl>
            <Metric
              label="CPU — PEAK ACROSS MACHINES"
              reading={markStaleOnError(
                preferNullable(maxNullable(machineRows.map((m) => m.cpu)), null, "not reported by any agent"),
                snapshot(machines),
              )}
              format={(value) => `${value.toFixed(0)}%`}
            />
            <Metric
              label="SYSTEM MEMORY — PEAK"
              reading={preferNullable(maxNullable(machineRows.map((m) => m.ram)), null, "not reported by any agent")}
              format={(value) => `${value.toFixed(0)}%`}
            />
            <Metric
              label="DISK — PEAK"
              reading={preferNullable(maxNullable(machineRows.map((m) => m.disk)), null, "not reported by any agent")}
              format={(value) => `${value.toFixed(0)}%`}
            />
            <Metric
              label="INTERNET LATENCY"
              reading={preferNullable(maxNullable(machineRows.map((m) => m.internet_ms)), null, "not reported by any agent")}
              format={(value) => `${value.toFixed(0)}ms`}
            />
            <Metric
              label="API SUCCESS RATE"
              reading={preferNullable(
                health.data?.latest?.api_success_rate,
                health.data?.latest?.api_success_pct,
                "agent reported no success rate",
              )}
              format={(value) => `${(value * 100).toFixed(1)}%`}
            />
            <Metric label="PROCESS MEMORY" reading={unknown("process RSS is not reported separately")} />
            <Metric label="POSTGRESQL" reading={unknown("no database health signal is exposed")} />
            <Metric label="DATABASE CONNECTIONS" reading={unknown("not exposed by the API")} />
            <Metric label="WORKER STATUS" reading={unknown("not exposed by the API")} />
          </dl>
        </Panel>
      </div>

      {/* ------------------------- row 5: incidents -------------------------- */}
      <Panel
        title="INCIDENTS / ALERTS"
        state={
          !incidentStateKnown
            ? "UNKNOWN"
            : incidents.length === 0
              ? "HEALTHY"
              : severityRank(incidents[0]) >= 4
                ? "CRITICAL"
                : severityRank(incidents[0]) >= 3
                  ? "DEGRADED"
                  : "STALE"
        }
      >
        <div className="h-full min-h-[3.5rem] overflow-hidden">
          {!incidentStateKnown ? (
            <p className="font-mono text-[clamp(10px,0.8vw,16px)] font-bold tracking-widest text-amber-300">
              INCIDENT STATE UNKNOWN
              <span className="ml-3 font-normal tracking-normal text-slate-500">
                {alerts.isError
                  ? "the incident store did not answer"
                  : "telemetry store is not configured — an empty result cannot be read as “no incidents”"}
              </span>
            </p>
          ) : incidents.length === 0 ? (
            <p className="font-mono text-[clamp(10px,0.8vw,16px)] font-bold tracking-widest text-emerald-300">
              NO ACTIVE INCIDENTS
            </p>
          ) : (
            <ul className="flex h-full flex-col gap-[2px] overflow-hidden">
              {incidents.slice(0, 6).map((event) => (
                <li
                  key={event.id}
                  className="grid grid-cols-[auto_auto_1fr_auto] items-baseline gap-x-3 border-b border-slate-800/60 pb-[2px] font-mono text-[clamp(8px,0.6vw,12px)] last:border-b-0"
                >
                  <span className="text-slate-500">
                    {clockLabel(event.time ?? event.received_at ?? event.event_ts)}
                  </span>
                  <span
                    className={
                      severityRank(event) >= 4
                        ? "font-bold text-rose-300"
                        : severityRank(event) >= 3
                          ? "font-bold text-orange-300"
                          : severityRank(event) >= 2
                            ? "text-amber-300"
                            : "text-slate-400"
                    }
                  >
                    {severityLabel(event)}
                  </span>
                  <span className="truncate text-slate-200">{event.message ?? "UNKNOWN"}</span>
                  <span className="truncate text-slate-500">
                    {event.source ?? event.machine_id ?? "UNKNOWN"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Panel>

      {/* ------------------------------ bottom bar --------------------------- */}
      <footer className="flex shrink-0 flex-wrap items-baseline justify-between gap-x-5 gap-y-0.5 rounded-lg bg-[#0d121b] px-3 py-1 font-mono text-[clamp(8px,0.55vw,11px)] ring-1 ring-slate-800">
        <span className="text-slate-500">
          DATA AS OF{" "}
          <span className="text-slate-200">
            {marketAsOf.state === "UNKNOWN" ? "UNKNOWN" : dateTimeLabel(marketAsOf.value)}
          </span>
        </span>
        <span className="text-slate-500">
          SYSTEM TIME <span className="text-slate-200">{now.toLocaleTimeString(undefined, { hour12: false })}</span>
        </span>
        <span className="text-slate-500">
          LAST SUCCESSFUL UPDATE{" "}
          <span className="text-slate-200">
            {lastUpdate.state === "UNKNOWN" ? "UNKNOWN" : dateTimeLabel(lastUpdate.value)}
          </span>
        </span>
        <span className="text-slate-500">
          API <span className="text-slate-200">{connection}</span>
        </span>
        <span className="text-slate-500">
          BUILD <span className={build ? "text-slate-200" : "text-amber-300"}>{build ?? "UNKNOWN"}</span>
        </span>
        <span className="text-slate-500">
          TELEMETRY{" "}
          <span className={telemetryEstablished ? "text-slate-200" : "text-amber-300"}>
            {telemetryConfigured ? (awaitingTelemetry ? "AWAITING" : "ESTABLISHED") : "NOT CONFIGURED"}
          </span>
        </span>
      </footer>
    </div>
  );
}
