/**
 * Operations wallboard — System Health on one screen, meant to be left running.
 *
 * Read-only. No order, strategy, risk or broker control exists on this page, and
 * a test asserts that.
 *
 * Layout, top to bottom: overall verdict and clock; the Indian market strip;
 * the platform status matrix (API, database, Redis and every background
 * process, plus the data sources); the execution agent's telemetry — the
 * System Health page's metrics and charts; the fleet (execution agents and
 * trading devices); incidents; and LLS monitoring.
 *
 * The governing rule is that this board must never claim to know something it
 * does not:
 *
 * * The database and Redis are shown healthy only on a real probe — the API's
 *   own `SELECT 1`/`PING` for platform admins, the public readiness probe for
 *   everyone else. An HTTP 200 from some other endpoint is never read as one.
 * * Background processes are judged by the heartbeat each writes to Redis. A
 *   missing heartbeat is CRITICAL; one that is late is STALE.
 * * Agent telemetry prefers the nullable twins (`cpu_usage`, `api_success_rate`,
 *   `signal_fill_rate`): the plain fields default to 0/100 on the server when
 *   an agent reported nothing. See `preferNullable` in `@/lib/wallboard`.
 * * Incidents distinguish "the store answered and there are none" from "the
 *   store did not answer". Only the first may print NO ACTIVE INCIDENTS.
 * * The overall verdict never says HEALTHY while a required check is UNKNOWN.
 *   Optional components that are simply not set up (no devices registered, no
 *   LLS publisher yet) are shown, but do not hold the verdict hostage.
 *
 * Tenancy: every query goes through the existing platform hooks, which are
 * gated on an active organisation and authorised server-side.
 */

import { clsx } from "clsx";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router";

import { BrandMark } from "@/components/BrandMark";
import { Glyph, type GlyphName } from "@/components/icons";
import { Seo } from "@/components/Seo";
import { ApiError, MFA_REQUIRED_CODE } from "@/lib/api";
import { type Device, useDevices } from "@/lib/devices";
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
import { pctText, type QuoteRow, SESSION_LABEL, useMarketPulse } from "@/lib/markets";
import { readFreshness } from "@/lib/monitoring";
import {
  ageText,
  heartbeatState,
  pickMachine,
  reportingMachines,
  secondsSince,
  useBuildInfo,
  useDependencyProbe,
  usePlatformHealth,
} from "@/lib/systemHealth";
import {
  clockLabel,
  connectionState,
  dateTimeLabel,
  known,
  lastSuccessfulUpdate,
  latestInstant,
  markStaleOnError,
  readEstablishedCount,
  rollUp,
  unknown,
  type OperationalState,
  type QuerySnapshot,
  type Reading,
} from "@/lib/wallboard";
import { useAuth } from "@/stores/auth";
import type { OpsEvent, OpsMachine } from "@/types/api";

import { Gauge, Panel, ServiceTile, Stat, StatusDot, TONE } from "./wallboard/parts";
import { TelemetryPanel } from "./wallboard/TelemetryPanel";

/* -------------------------------- helpers --------------------------------- */

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

const SEVERITY_STYLE: Record<string, string> = {
  CRITICAL: "bg-rose-500/15 text-rose-300 ring-rose-400/40",
  ERROR: "bg-orange-400/10 text-orange-300 ring-orange-400/35",
  WARNING: "bg-amber-400/10 text-amber-300 ring-amber-400/30",
  INFO: "bg-white/5 text-slate-400 ring-white/10",
};

const HEADLINE: Record<OperationalState, string> = {
  HEALTHY: "All systems operational",
  DEGRADED: "Degraded — some components need attention",
  STALE: "Some signals are late",
  CRITICAL: "Service disruption",
  UNKNOWN: "Status incomplete — some checks have not answered",
};

const OVERALL_FRAME: Record<OperationalState, string> = {
  HEALTHY: "bg-emerald-400/[0.07] ring-emerald-400/25",
  DEGRADED: "bg-orange-400/[0.08] ring-orange-400/30",
  STALE: "bg-sky-400/[0.07] ring-sky-400/25",
  CRITICAL: "bg-rose-500/[0.12] ring-rose-400/40",
  UNKNOWN: "bg-amber-400/[0.07] ring-amber-400/25",
};

const DEVICE_STATE: Record<Device["status"], { text: string; state: OperationalState }> = {
  online: { text: "ONLINE", state: "HEALTHY" },
  offline: { text: "OFFLINE", state: "CRITICAL" },
  never_seen: { text: "NO REPORT", state: "UNKNOWN" },
  revoked: { text: "REVOKED", state: "UNKNOWN" },
};

const IST_TIME = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Kolkata",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});
const IST_DAY = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short" });
const IST_DATE = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Kolkata",
  weekday: "short",
  day: "2-digit",
  month: "short",
});

function indexValue(quote: QuoteRow | undefined): string | null {
  return quote?.price === null || quote?.price === undefined
    ? null
    : quote.price.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

/** "4s ago", "2m 10s ago" — or "never" when there is no report at all. */
function ago(seconds: number | null): string {
  return seconds === null ? "never" : `${ageText(seconds)} ago`;
}

/* ------------------------------ small pieces ------------------------------ */

function Ticker({
  title,
  value,
  change,
  note,
  children,
}: {
  title: string;
  value: string | null;
  change?: number | null;
  note?: string;
  children?: React.ReactNode;
}) {
  const tone =
    change === null || change === undefined
      ? "text-slate-400 bg-white/5"
      : change > 0
        ? "text-emerald-300 bg-emerald-400/10"
        : change < 0
          ? "text-rose-300 bg-rose-400/10"
          : "text-slate-300 bg-white/5";
  return (
    <div className="flex min-w-0 flex-col justify-center gap-0.5 rounded-xl bg-white/[0.03] px-3 py-2 ring-1 ring-white/[0.07]">
      <span className="truncate text-[clamp(9px,0.55vw,12px)] font-medium uppercase tracking-[0.14em] text-slate-500">{title}</span>
      <span className="flex min-w-0 items-baseline gap-2">
        <span
          className={clsx(
            "truncate font-data text-[clamp(14px,1.05vw,22px)] font-semibold tabular-nums",
            value === null ? "text-amber-200/80" : "text-slate-50",
          )}
        >
          {value ?? "UNKNOWN"}
        </span>
        {change !== undefined && change !== null ? (
          <span className={clsx("rounded-md px-1.5 py-px font-data text-[clamp(9px,0.58vw,12px)] font-semibold", tone)}>
            {pctText(change)}
          </span>
        ) : null}
        {note ? <span className="truncate text-[clamp(9px,0.55vw,12px)] text-slate-500">{note}</span> : null}
      </span>
      {children}
    </div>
  );
}

function HeaderButton({
  icon,
  children,
  onClick,
  title,
}: {
  icon: "monitor" | "expand" | "collapse";
  children: string;
  onClick: () => void;
  title: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[clamp(10px,0.6vw,13px)] font-medium text-slate-300 ring-1 ring-white/10 transition-colors hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-accent-400"
    >
      <Glyph name={icon} className="size-3.5" />
      {children}
    </button>
  );
}

/** One machine or device: identity, three utilisation gauges, status — one line. */
function FleetRow({
  name,
  meta,
  cpu,
  ram,
  disk,
  status,
  state,
}: {
  name: string;
  meta: string;
  cpu: number | null | undefined;
  ram: number | null | undefined;
  disk: number | null | undefined;
  status: string;
  state: OperationalState;
}) {
  return (
    <li className="grid grid-cols-[minmax(0,1.4fr)_repeat(3,minmax(0,0.8fr))_5.5rem] items-center gap-x-3 rounded-lg px-2 py-0.5 hover:bg-white/[0.02]">
      <div className="min-w-0">
        <p className="truncate text-[clamp(11px,0.66vw,14px)] font-medium text-slate-100">{name}</p>
        <p className="truncate font-data text-[clamp(9px,0.52vw,11px)] text-slate-500">{meta}</p>
      </div>
      <Gauge name="CPU" value={cpu} />
      <Gauge name="RAM" value={ram} />
      <Gauge name="DISK" value={disk} />
      <span className={clsx("flex items-center justify-end gap-1.5 font-data text-[clamp(9px,0.55vw,12px)] font-semibold tracking-[0.1em]", TONE[state].text)}>
        <StatusDot state={state} className="size-1.5" />
        {status}
      </span>
    </li>
  );
}

function MachineRow({ machine, now }: { machine: OpsMachine; now: number }) {
  const online = machine.status === "online";
  const meta = [
    `heartbeat ${ago(secondsSince(machine.last_heartbeat, now))}`,
    machine.queue_depth === null || machine.queue_depth === undefined ? null : `queue ${machine.queue_depth}`,
    typeof machine.internet_ms === "number" ? `net ${Math.round(machine.internet_ms)} ms` : null,
    typeof machine.broker_ping_ms === "number" ? `broker ${Math.round(machine.broker_ping_ms)} ms` : null,
  ].filter(Boolean);
  return (
    <FleetRow
      name={machine.hostname || machine.name || machine.id}
      meta={meta.join(" · ")}
      cpu={machine.cpu}
      ram={machine.ram}
      disk={machine.disk}
      status={online ? "ONLINE" : (machine.status ?? "UNKNOWN").toUpperCase()}
      state={online ? "HEALTHY" : "CRITICAL"}
    />
  );
}

function DeviceRow({ device, now }: { device: Device; now: number }) {
  const status = DEVICE_STATE[device.status];
  const latency = device.health?.latency_ms;
  return (
    <FleetRow
      name={device.name}
      meta={`${device.kind} · seen ${ago(secondsSince(device.last_seen_at, now))}${typeof latency === "number" ? ` · ${Math.round(latency)} ms` : ""}`}
      cpu={device.health?.cpu}
      ram={device.health?.ram}
      disk={device.health?.disk}
      status={status.text}
      state={status.state}
    />
  );
}

function SubHeading({ children, aside }: { children: string; aside?: React.ReactNode }) {
  return (
    <h3 className="mb-1 flex items-center justify-between gap-2 px-2 text-[clamp(9px,0.55vw,12px)] font-semibold uppercase tracking-[0.14em] text-slate-500">
      <span>{children}</span>
      {aside}
    </h3>
  );
}

/* -------------------------------- the page -------------------------------- */

export function WallboardPage() {
  const isAdmin = useAuth((state) => state.user?.is_platform_admin ?? false);

  const overview = useOpsOverview();
  const machines = useOpsMachines();
  const alerts = useOpsAlerts();
  const monitoringState = useMonitoringState({ limit: 200 });
  const monitoringSources = useMonitoringSources();
  const quotes = useMarketQuotes();
  const pulse = useMarketPulse();
  const devices = useDevices();
  const platform = usePlatformHealth(isAdmin);
  const probe = useDependencyProbe();
  const build = useBuildInfo();

  const agentMachines = useMemo(() => reportingMachines(machines.data), [machines.data]);
  const [chosenMachine, setChosenMachine] = useState<string | null>(null);
  const activeMachine = pickMachine(agentMachines, chosenMachine);
  // The most recent snapshots whatever their age, so an agent that went quiet
  // still shows its last known figures (labelled historical) instead of nothing.
  const health = useOpsSystemHealth(
    { machine_id: activeMachine || undefined, limit: 240 },
    { refetchInterval: 15_000 },
  );

  const [now, setNow] = useState(() => Date.now());
  const [fullscreen, setFullscreen] = useState(false);
  const [displayMode, setDisplayMode] = useState(false);
  const [idle, setIdle] = useState(false);

  // A single interval for the wall clock, cleared on unmount. Data refresh is
  // React Query's job: it serialises its own refetches, so a slow response
  // cannot build a backlog the way a bare setInterval(fetch) would.
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const sync = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", sync);
    sync();
    return () => document.removeEventListener("fullscreenchange", sync);
  }, []);

  const toggleFullscreen = useCallback(() => {
    // Absence of the API is normal (iOS Safari); display mode still works, so
    // this degrades rather than failing.
    if (document.fullscreenElement) {
      void document.exitFullscreen?.();
      return;
    }
    void document.documentElement.requestFullscreen?.().catch(() => undefined);
  }, []);

  // Keyboard: F fullscreen, D display mode, Esc leaves display mode.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest?.("input, textarea, select, [contenteditable='true']")) return;
      if (event.key === "f" || event.key === "F") toggleFullscreen();
      else if (event.key === "d" || event.key === "D") setDisplayMode((value) => !value);
      else if (event.key === "Escape") setDisplayMode(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleFullscreen]);

  // Display mode: keep the screen awake and hide an idle cursor.
  useEffect(() => {
    if (!displayMode) return;
    let timer = window.setTimeout(() => setIdle(true), 3_000);
    const wake = () => {
      setIdle(false);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setIdle(true), 3_000);
    };
    window.addEventListener("mousemove", wake);
    window.addEventListener("keydown", wake);

    let lock: WakeLockSentinel | null = null;
    let released = false;
    navigator.wakeLock
      ?.request("screen")
      .then((sentinel) => {
        if (released) void sentinel.release().catch(() => undefined);
        else lock = sentinel;
      })
      .catch(() => undefined);

    return () => {
      released = true;
      window.clearTimeout(timer);
      window.removeEventListener("mousemove", wake);
      window.removeEventListener("keydown", wake);
      void lock?.release().catch(() => undefined);
    };
  }, [displayMode]);

  const queries = useMemo(
    () => [
      snapshot(overview),
      snapshot(machines),
      snapshot(alerts),
      snapshot(health),
      snapshot(monitoringState),
      snapshot(monitoringSources),
      snapshot(quotes),
      snapshot(probe),
    ],
    [overview, machines, alerts, health, monitoringState, monitoringSources, quotes, probe],
  );
  const connection = connectionState(queries);
  const lastUpdate = lastSuccessfulUpdate(queries);
  const lastUpdateAge = lastUpdate.state === "UNKNOWN" ? null : secondsSince(lastUpdate.value, now);

  /* --- telemetry availability: the gate that keeps zeros honest ----------- */

  const telemetryConfigured = overview.isSuccess && overview.data?.telemetry_configured === true;
  const awaitingTelemetry = overview.data?.awaiting_telemetry !== false;
  const telemetryEstablished = telemetryConfigured && !awaitingTelemetry;
  const machineRows: OpsMachine[] = useMemo(() => machines.data ?? [], [machines.data]);

  /* --- platform: API, database, Redis, background processes --------------- */

  const apiReading: Reading<string> =
    connection === "DEGRADED"
      ? known("DEGRADED", "Some requests failing", "from this browser")
      : connection === "CONNECTED"
        ? known("HEALTHY", probe.data ? `${probe.data.round_trip_ms} ms` : "Reachable", "round trip from this browser")
        : unknown("no request has completed yet");

  const adminUnavailable = (): string => {
    if (!isAdmin) return "visible to platform admins";
    if (platform.error instanceof ApiError && platform.error.code === MFA_REQUIRED_CODE) {
      return "turn on 2FA to see this";
    }
    return platform.isError ? "admin health check did not answer" : "waiting for the first check";
  };

  const dependencyReading = (
    probeName: "postgres" | "redis",
    healthy: boolean | undefined,
    latency: number | null | undefined,
  ): Reading<string> => {
    if (platform.data && healthy !== undefined) {
      return markStaleOnError(
        healthy
          ? known("HEALTHY", typeof latency === "number" ? `${latency.toFixed(1)} ms` : "Reachable", "probe from the API server")
          : known("CRITICAL", "Unreachable", "the API server's probe failed"),
        snapshot(platform),
      );
    }
    const dependency = probe.data?.dependencies.find((item) => item.name === probeName);
    if (!dependency) return unknown(probe.isError ? "readiness probe did not answer" : "no probe has answered yet");
    return markStaleOnError(
      dependency.healthy
        ? known("HEALTHY", "Reachable", "readiness probe")
        : known("CRITICAL", "Unreachable", dependency.detail ? `probe: ${dependency.detail}` : "readiness probe failed"),
      snapshot(probe),
    );
  };

  const databaseReading = dependencyReading("postgres", platform.data?.database, platform.data?.database_latency_ms);
  const redisReading = dependencyReading("redis", platform.data?.redis, platform.data?.redis_latency_ms);

  const serviceReading = (name: string, extra?: string): Reading<string> => {
    if (!platform.data) return unknown(adminUnavailable());
    const service = platform.data.services?.find((item) => item.name === name);
    if (!service) return unknown("not reported by this API version");
    const state = heartbeatState(service.age_seconds, service.stale_after_seconds);
    const suffix = extra ? ` · ${extra}` : "";
    const reading =
      state === "HEALTHY"
        ? known("HEALTHY", "Running", `heartbeat ${ageText(service.age_seconds)} ago${suffix}`)
        : state === "STALE"
          ? known("STALE", "Overdue", `last heartbeat ${ageText(service.age_seconds)} ago${suffix}`)
          : known("CRITICAL", "No heartbeat", `silent for 2+ min, or not started${suffix}`);
    return markStaleOnError(reading, snapshot(platform));
  };

  /* --- data sources -------------------------------------------------------- */

  const marketAsOf = latestInstant((quotes.data ?? []).map((row) => row.as_of));
  const quotesReading: Reading<string> = useMemo(() => {
    if (!quotes.isSuccess && !quotes.data) return unknown("market-info unavailable");
    const count = quotes.data?.length ?? 0;
    if (count === 0) return unknown("no instruments in universe");
    if (marketAsOf.state === "UNKNOWN") return unknown("provider returned no market timestamp");
    // Never LIVE because the page refreshed — this states what the provider
    // stamped, and nothing more.
    return known("HEALTHY", `${count} quoted`, `provider as of ${clockLabel(marketAsOf.value)}`);
  }, [quotes.isSuccess, quotes.data, marketAsOf.state, marketAsOf.value]);

  const universe = pulse.data?.universe;
  const nseReading: Reading<string> = (() => {
    if (!pulse.data || !universe) return unknown(pulse.isError ? "market pulse did not answer" : "waiting for market pulse");
    if (universe.source !== "nse" || !universe.trade_date) {
      return known("DEGRADED", "Built-in list", "no NSE pre-open capture yet");
    }
    const captured = `${universe.trade_date}T09:08:00+05:30`;
    const days = secondsSince(captured, now);
    const value = `Pre-open ${IST_DAY.format(Date.parse(captured))}`;
    return days !== null && days > 4 * 86_400
      ? known("STALE", value, "no newer capture in 4 days")
      : known("HEALTHY", value, "captured 09:08 IST each trading day");
  })();

  const agentsReading: Reading<string> = useMemo(() => {
    if (!overview.isSuccess) return unknown("operations overview unavailable");
    if (!telemetryConfigured) return unknown("telemetry store not configured");
    if (awaitingTelemetry) return unknown("awaiting first telemetry");
    const total = overview.data?.machine_count ?? null;
    const online = overview.data?.online_machines ?? null;
    if (total === null || online === null) return unknown("machine counts not reported");
    if (total === 0) return unknown("no machines registered");
    if (online === total) return known("HEALTHY", `${online}/${total} online`);
    if (online === 0) return known("CRITICAL", `0/${total} online`, "no machine is reporting");
    return known("DEGRADED", `${online}/${total} online`);
  }, [overview.isSuccess, overview.data, telemetryConfigured, awaitingTelemetry]);

  const fleet = useMemo(() => (devices.data ?? []).filter((device) => device.status !== "revoked"), [devices.data]);
  const devicesReading: Reading<string> = (() => {
    if (!devices.isSuccess) return unknown(devices.isError ? "device list did not answer" : "waiting for device list");
    if (fleet.length === 0) return unknown("none registered");
    const online = fleet.filter((device) => device.status === "online").length;
    const offline = fleet.filter((device) => device.status === "offline").length;
    if (offline > 0) return known("DEGRADED", `${online}/${fleet.length} online`, `${offline} silent for 3+ min`);
    if (online === fleet.length) return known("HEALTHY", `${online}/${fleet.length} online`);
    return known("STALE", `${online}/${fleet.length} online`, "awaiting first report");
  })();

  const receiverReading: Reading<string> = useMemo(() => {
    if (!monitoringState.isSuccess && !monitoringState.data) return unknown("monitoring read API unavailable");
    if (monitoringState.data?.configured !== true) return unknown("receiver database not configured");
    const count = monitoringState.data?.count ?? 0;
    // Configured and empty is an established fact, but not evidence of health.
    if (count === 0) return unknown("configured; no messages received");
    return known("HEALTHY", `${count} observations`);
  }, [monitoringState.isSuccess, monitoringState.data]);

  const pipelineReading: Reading<string> = useMemo(() => {
    if (!machines.isSuccess && !machines.data) return unknown("machine telemetry unavailable");
    const depth = maxNullable(machineRows.map((machine) => machine.queue_depth));
    const transports = machineRows
      .map((machine) => machine.transport_state)
      .filter((value): value is string => Boolean(value));
    if (depth === null && transports.length === 0) return unknown("no pipeline metric reported");
    if (depth === null) return known("HEALTHY", transports[0].toUpperCase(), "transport state only");
    return known(depth > 0 ? "DEGRADED" : "HEALTHY", `Queue ${depth}`, transports[0] ? `transport ${transports[0]}` : null);
  }, [machines.isSuccess, machines.data, machineRows]);

  const tiles: { key: string; icon: GlyphName; title: string; reading: Reading<string>; optional?: boolean }[] = [
    { key: "api", icon: "signal", title: "API", reading: apiReading },
    { key: "database", icon: "database", title: "Database", reading: databaseReading },
    { key: "redis", icon: "layers", title: "Redis cache", reading: redisReading },
    { key: "market_data", icon: "pulse", title: "Market data feed", reading: serviceReading("market_data") },
    {
      key: "trading_engine",
      icon: "bolt",
      title: "Trading engine",
      reading: serviceReading("trading_engine", platform.data ? `${platform.data.active_runs} active runs` : undefined),
    },
    { key: "scheduler", icon: "clock", title: "Scheduler", reading: serviceReading("scheduler") },
    {
      key: "relay",
      icon: "inbox",
      title: "Outbox relay",
      reading: serviceReading("relay", platform.data ? `backlog ${platform.data.outbox_backlog}` : undefined),
    },
    { key: "email", icon: "mail", title: "E-mail worker", reading: serviceReading("email") },
    { key: "quotes", icon: "chart", title: "Market quotes", reading: quotesReading },
    { key: "nse", icon: "history", title: "NSE snapshots", reading: nseReading },
    { key: "agents", icon: "server", title: "Execution agents", reading: agentsReading, optional: true },
    { key: "devices", icon: "monitor", title: "Trading devices", reading: devicesReading, optional: true },
    { key: "lls", icon: "radar", title: "LLS receiver", reading: receiverReading, optional: true },
    { key: "pipeline", icon: "list", title: "Agent upload queue", reading: pipelineReading, optional: true },
  ];

  // Optional components that are simply not set up are shown but not counted;
  // a required check that has not answered keeps the verdict off HEALTHY.
  const counted = tiles.filter((tile) => !(tile.optional && tile.reading.state === "UNKNOWN"));
  const overall = rollUp(counted.map((tile) => tile.reading.state));
  const healthyCount = tiles.filter((tile) => tile.reading.state === "HEALTHY").length;
  const attentionCount = tiles.filter((tile) => ["DEGRADED", "STALE", "CRITICAL"].includes(tile.reading.state)).length;
  const unknownCount = tiles.length - healthyCount - attentionCount;

  /* --- monitoring.v1 -------------------------------------------------------- */

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

  const latestEvidence = latestInstant(sourceRows.map((row) => row.last_seen_at));

  /* --- incidents ------------------------------------------------------------ */

  const incidents = useMemo(
    () => (alerts.data ?? []).slice().sort((a, b) => severityRank(b) - severityRank(a)),
    [alerts.data],
  );
  // An empty list only means "no incidents" when the store was able to answer.
  // Unconfigured telemetry also returns [], and the two must not look the same.
  const incidentStateKnown = alerts.isSuccess && telemetryConfigured;
  const incidentState: OperationalState = !incidentStateKnown
    ? "UNKNOWN"
    : incidents.length === 0
      ? "HEALTHY"
      : severityRank(incidents[0]) >= 4
        ? "CRITICAL"
        : severityRank(incidents[0]) >= 3
          ? "DEGRADED"
          : "STALE";

  /* --- market session ------------------------------------------------------- */

  const schedule = getIndianMarketDaySchedule(new Date(now));
  const sessionText = pulse.data?.session
    ? SESSION_LABEL[pulse.data.session.state]
    : schedule.type === "open"
      ? "Trading day"
      : schedule.type === "weekend"
        ? "Closed — weekend"
        : schedule.reason;
  const sessionOpen = pulse.data?.session.state === "open" || pulse.data?.session.state === "pre_open";

  const environment = build.data?.environment ?? monitoringState.data?.receiver_deployment_environment ?? null;
  const buildLabel = build.data
    ? `${build.data.version}${build.data.build_sha && build.data.build_sha !== "unknown" ? ` · ${build.data.build_sha.slice(0, 7)}` : ""}`
    : ((import.meta.env.VITE_APP_VERSION as string | undefined) ?? null);

  const flow = pulse.data?.institutional_flows[0];
  const breadth = pulse.data?.breadth;
  const breadthTotal = breadth ? breadth.advances + breadth.declines + breadth.unchanged : 0;

  const visibleAgents = agentMachines.slice(0, 3);
  const visibleDevices = fleet.slice(0, 4);

  return (
    <div
      className={clsx(
        "relative isolate flex min-h-[100dvh] w-full flex-col gap-3 bg-[#05080e] p-3 text-slate-200 wall:h-[100dvh] wall:overflow-hidden",
        displayMode && "fixed inset-0 z-50",
        displayMode && idle && "cursor-none",
      )}
      data-testid="wallboard"
    >
      <Seo title="System Health Wallboard" noindex />
      <div aria-hidden className="am-radial am-grid pointer-events-none absolute inset-0 -z-10 opacity-80" />

      {/* --------------------------------- header -------------------------------- */}
      <header className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-3 rounded-2xl bg-[#0a1019]/85 px-4 py-2.5 ring-1 ring-white/[0.07]">
        <div className="flex items-center gap-3">
          <BrandMark to="/app/dashboard" compact />
          <div>
            <h1 className="text-[clamp(15px,1.05vw,24px)] font-semibold tracking-tight text-white">System Health</h1>
            <p className="text-[clamp(9px,0.52vw,11px)] font-medium uppercase tracking-[0.2em] text-slate-500">
              ALGOMATRIC operations wallboard
            </p>
          </div>
        </div>

        <div
          className={clsx("flex min-w-0 items-center gap-3 rounded-xl px-3.5 py-1.5 ring-1", OVERALL_FRAME[overall])}
          role="status"
          aria-label="Overall status"
        >
          <StatusDot state={overall} className="size-3" />
          <div className="min-w-0">
            <p className={clsx("font-data text-[clamp(13px,0.9vw,20px)] font-bold tracking-[0.14em]", TONE[overall].text)}>{overall}</p>
            <p className="text-[clamp(10px,0.6vw,13px)] text-slate-300 xl:truncate">
              {HEADLINE[overall]}
              <span className="text-slate-500">
                {" · "}
                {healthyCount} of {tiles.length} healthy
                {attentionCount ? ` · ${attentionCount} need attention` : ""}
                {unknownCount ? ` · ${unknownCount} unknown` : ""}
              </span>
            </p>
          </div>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-x-5 gap-y-2">
          <div className="flex flex-col items-end">
            <span className="text-[clamp(9px,0.52vw,11px)] font-medium uppercase tracking-[0.16em] text-slate-500">NSE session</span>
            <span className={clsx("flex items-center gap-1.5 text-[clamp(11px,0.68vw,14px)] font-semibold", sessionOpen ? "text-emerald-300" : "text-slate-300")}>
              {sessionOpen ? <StatusDot state="HEALTHY" className="size-1.5" /> : null}
              {sessionText}
            </span>
          </div>
          <div className="flex flex-col items-end" aria-label="Indian Standard Time">
            <span className="font-data text-[clamp(18px,1.45vw,32px)] font-semibold leading-none tabular-nums text-white">
              {IST_TIME.format(now)}
            </span>
            <span className="text-[clamp(9px,0.52vw,11px)] font-medium uppercase tracking-[0.16em] text-slate-500">
              IST · {IST_DATE.format(now)}
            </span>
          </div>
          <dl className="flex flex-col items-end">
            <dt className="sr-only">Connection</dt>
            <dd
              className={clsx(
                "flex items-center gap-1.5 font-data text-[clamp(10px,0.6vw,13px)] font-semibold tracking-[0.1em]",
                connection === "CONNECTED" ? "text-emerald-300" : "text-amber-300",
              )}
            >
              <StatusDot state={connection === "CONNECTED" ? "HEALTHY" : connection === "DEGRADED" ? "DEGRADED" : "UNKNOWN"} className="size-1.5" />
              {connection === "DEGRADED" ? "CONNECTION DEGRADED" : connection}
            </dd>
            <dt className="sr-only">Last update</dt>
            <dd className="text-[clamp(9px,0.55vw,12px)] text-slate-500">
              {lastUpdateAge === null ? "No update yet" : `Updated ${ageText(lastUpdateAge)} ago`} · every 15s
            </dd>
          </dl>
          <div className="flex items-center gap-1.5">
            {displayMode ? (
              <HeaderButton icon="collapse" onClick={() => setDisplayMode(false)} title="Leave display mode (Esc)">
                Exit display mode
              </HeaderButton>
            ) : (
              <>
                <HeaderButton icon="monitor" onClick={() => setDisplayMode(true)} title="Keep the screen awake and hide the cursor (D)">
                  Display mode
                </HeaderButton>
                <HeaderButton icon={fullscreen ? "collapse" : "expand"} onClick={toggleFullscreen} title="Toggle fullscreen (F)">
                  {fullscreen ? "Exit fullscreen" : "Fullscreen"}
                </HeaderButton>
              </>
            )}
            <Link
              to="/app/dashboard"
              className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[clamp(10px,0.6vw,13px)] font-medium text-slate-400 ring-1 ring-white/10 transition-colors hover:bg-white/5 hover:text-white"
            >
              <Glyph name="close" className="size-3.5" />
              Exit
            </Link>
          </div>
        </div>
      </header>

      {/* ------------------------------ market strip ----------------------------- */}
      <div className="grid shrink-0 grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6" data-testid="market-strip">
        {(["^NSEI", "^NSEBANK", "^BSESN"] as const).map((symbol) => {
          const quote = pulse.data?.indices.find((row) => row.symbol === symbol);
          return <Ticker key={symbol} title={quote?.name ?? symbol} value={indexValue(quote)} change={quote?.change_pct ?? null} />;
        })}
        <Ticker
          title="India VIX"
          value={indexValue(pulse.data?.vix)}
          change={pulse.data?.vix.change_pct ?? null}
          note={pulse.data?.regime.volatility.label}
        />
        <Ticker
          title="F&O advance / decline"
          value={breadth ? `${breadth.advances} / ${breadth.declines}` : null}
          note={breadth?.pct_advancing != null ? `${breadth.pct_advancing}% up` : undefined}
        >
          {breadth && breadthTotal > 0 ? (
            <div className="mt-1 flex h-1 overflow-hidden rounded-full bg-white/[0.06]" aria-hidden>
              <div className="bg-emerald-400" style={{ width: `${(breadth.advances / breadthTotal) * 100}%` }} />
              <div className="bg-slate-500" style={{ width: `${(breadth.unchanged / breadthTotal) * 100}%` }} />
              <div className="bg-rose-400" style={{ width: `${(breadth.declines / breadthTotal) * 100}%` }} />
            </div>
          ) : null}
        </Ticker>
        <Ticker
          title="FII net (₹ cr)"
          value={flow?.fii_net == null ? null : Math.round(flow.fii_net).toLocaleString("en-IN")}
          note={flow?.trade_date ?? undefined}
        />
      </div>

      {/* ------------------------- platform status matrix ------------------------ */}
      <section aria-label="Platform services" className="grid shrink-0 grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 wall:grid-cols-7 2xl:grid-cols-7">
        {tiles.map((tile) => (
          <ServiceTile key={tile.key} icon={tile.icon} title={tile.title} reading={tile.reading} />
        ))}
      </section>

      {/* --------------------------------- body ---------------------------------- */}
      <div className="grid min-h-0 flex-1 gap-3 xl:grid-cols-12">
        <TelemetryPanel
          className="min-h-[560px] xl:col-span-7 wall:min-h-0"
          machines={agentMachines}
          activeMachine={activeMachine}
          onSelectMachine={setChosenMachine}
          health={health.data}
          isLoading={health.isLoading}
          isError={health.isError}
          now={now}
        />

        <div className="grid min-h-0 gap-3 xl:col-span-5 wall:grid-rows-[minmax(0,1.2fr)_minmax(0,1fr)]">
          <Panel
            title="Fleet"
            icon="server"
            state={rollUp(
              [agentsReading.state, devicesReading.state].filter((state, index) =>
                state !== "UNKNOWN" || (index === 0 ? agentMachines.length > 0 : fleet.length > 0),
              ),
            )}
            bodyClassName="flex flex-col gap-3"
          >
            <div>
              <SubHeading aside={<span className="font-data normal-case tracking-normal">{agentsReading.value ?? agentsReading.detail}</span>}>
                Execution agents
              </SubHeading>
              {agentMachines.length === 0 ? (
                <p className="px-2 text-[clamp(10px,0.6vw,13px)] text-amber-300/90">
                  {machines.isError ? "Machine list did not answer." : "No execution agent has reported yet."}
                </p>
              ) : (
                <ul className="flex flex-col">
                  {visibleAgents.map((machine) => (
                    <MachineRow key={machine.id} machine={machine} now={now} />
                  ))}
                  {agentMachines.length > visibleAgents.length ? (
                    <li className="px-2 text-[clamp(9px,0.52vw,11px)] text-slate-500">+{agentMachines.length - visibleAgents.length} more</li>
                  ) : null}
                </ul>
              )}
            </div>
            <div>
              <SubHeading aside={<span className="font-data normal-case tracking-normal">{devicesReading.value ?? devicesReading.detail}</span>}>
                Trading devices
              </SubHeading>
              {!devices.isSuccess ? (
                <p className="px-2 font-data text-[clamp(10px,0.6vw,13px)] font-semibold tracking-[0.1em] text-amber-300">DEVICE STATE UNKNOWN</p>
              ) : fleet.length === 0 ? (
                <p className="px-2 text-[clamp(10px,0.6vw,13px)] text-slate-400">
                  <span className="font-data font-semibold tracking-[0.1em] text-amber-300">NO DEVICES REGISTERED</span>
                  <span className="ml-2 text-slate-500">Add one under Devices to see it here.</span>
                </p>
              ) : (
                <ul className="flex flex-col">
                  {visibleDevices.map((device) => (
                    <DeviceRow key={device.id} device={device} now={now} />
                  ))}
                  {fleet.length > visibleDevices.length ? (
                    <li className="px-2 text-[clamp(9px,0.52vw,11px)] text-slate-500">+{fleet.length - visibleDevices.length} more</li>
                  ) : null}
                </ul>
              )}
            </div>
          </Panel>

          <div className="grid min-h-0 gap-3 md:grid-cols-2">
            <Panel title="Incidents" icon="alert" state={incidentState}>
              {!incidentStateKnown ? (
                <div className="flex h-full flex-col justify-center gap-1 px-1">
                  <p className="font-data text-[clamp(11px,0.72vw,15px)] font-bold tracking-[0.12em] text-amber-300">INCIDENT STATE UNKNOWN</p>
                  <p className="text-[clamp(10px,0.58vw,12px)] text-slate-500">
                    {alerts.isError
                      ? "The incident store did not answer."
                      : "Telemetry store is not configured — an empty result cannot be read as “no incidents”."}
                  </p>
                </div>
              ) : incidents.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
                  <span className="grid size-9 place-items-center rounded-full bg-emerald-400/10 ring-1 ring-emerald-400/30">
                    <Glyph name="shield" className="size-4.5 text-emerald-300" />
                  </span>
                  <p className="font-data text-[clamp(11px,0.72vw,15px)] font-bold tracking-[0.12em] text-emerald-300">NO ACTIVE INCIDENTS</p>
                </div>
              ) : (
                <ul className="flex flex-col gap-1">
                  {incidents.slice(0, 8).map((event) => {
                    const severity = severityLabel(event);
                    return (
                      <li
                        key={event.id}
                        className="grid grid-cols-[auto_auto_minmax(0,1fr)] items-center gap-x-2.5 rounded-lg bg-white/[0.02] px-2 py-1.5 ring-1 ring-white/[0.04]"
                      >
                        <span className="font-data text-[clamp(9px,0.55vw,12px)] text-slate-500">
                          {clockLabel(event.time ?? event.received_at ?? event.event_ts)}
                        </span>
                        <span className={clsx("rounded px-1.5 py-px font-data text-[clamp(8px,0.5vw,11px)] font-bold tracking-[0.1em] ring-1", SEVERITY_STYLE[severity])}>
                          {severity}
                        </span>
                        <span className="min-w-0">
                          <span className="block truncate text-[clamp(10px,0.62vw,13px)] text-slate-200">{event.message ?? "UNKNOWN"}</span>
                          <span className="block truncate font-data text-[clamp(8px,0.5vw,11px)] text-slate-500">
                            {event.source ?? event.machine_id ?? "UNKNOWN"}
                          </span>
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Panel>

            <Panel title="LLS monitoring" icon="radar" state={receiverReading.state}>
              <dl className="grid grid-cols-2 gap-1.5">
                <Stat
                  title="Sources"
                  reading={readEstablishedCount(sourceRows.length, sourcesEstablished, "monitoring sources did not answer")}
                />
                <Stat title="Accepted" reading={sum((row) => row.accepted_count)} format={(value) => value.toLocaleString("en-IN")} />
                <Stat title="Duplicates" reading={sum((row) => row.duplicate_count)} />
                <Stat title="Refused · gap" reading={sum((row) => row.refused_gap_count)} />
                <Stat title="Refused · old" reading={sum((row) => row.refused_old_count)} />
                <Stat
                  title="Stale sources"
                  reading={readEstablishedCount(freshnessCounts.staleStates, freshnessCounts.established, "monitoring state did not answer")}
                />
                <Stat
                  title="Unknown freshness"
                  reading={readEstablishedCount(freshnessCounts.unknownStates, freshnessCounts.established, "monitoring state did not answer")}
                />
                <Stat
                  title="Latest evidence"
                  reading={
                    latestEvidence.state === "UNKNOWN" || !sourcesEstablished
                      ? unknown("no accepted message recorded")
                      : known("HEALTHY", clockLabel(latestEvidence.value))
                  }
                />
              </dl>
            </Panel>
          </div>
        </div>
      </div>

      {/* --------------------------------- footer -------------------------------- */}
      <footer className="flex shrink-0 flex-wrap items-baseline gap-x-6 gap-y-1 rounded-xl bg-[#0a1019]/70 px-4 py-1.5 font-data text-[clamp(9px,0.55vw,12px)] ring-1 ring-white/[0.06]">
        <span className="text-slate-500">
          MARKET DATA AS OF{" "}
          <span className="text-slate-200">{marketAsOf.state === "UNKNOWN" ? "UNKNOWN" : dateTimeLabel(marketAsOf.value)}</span>
        </span>
        <span className="text-slate-500">
          LAST SUCCESSFUL UPDATE{" "}
          <span className="text-slate-200">{lastUpdate.state === "UNKNOWN" ? "UNKNOWN" : dateTimeLabel(lastUpdate.value)}</span>
        </span>
        <span className="text-slate-500">
          ENVIRONMENT <span className={environment ? "text-slate-200" : "text-amber-300"}>{environment ?? "UNKNOWN"}</span>
        </span>
        <span className="text-slate-500">
          BUILD <span className={buildLabel ? "text-slate-200" : "text-amber-300"}>{buildLabel ?? "UNKNOWN"}</span>
        </span>
        <span className="text-slate-500">
          TELEMETRY{" "}
          <span className={telemetryEstablished ? "text-slate-200" : "text-amber-300"}>
            {telemetryConfigured ? (awaitingTelemetry ? "AWAITING" : "ESTABLISHED") : "NOT CONFIGURED"}
          </span>
        </span>
        <span className="ml-auto text-slate-600" title="These are not collected by the platform, so the board does not show a number for them.">
          NOT MEASURED: feed error counts · ingestion rate &amp; latency · quarantine · DB connection pool
        </span>
      </footer>
    </div>
  );
}
