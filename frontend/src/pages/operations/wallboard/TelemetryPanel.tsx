// Execution telemetry: the System Health page's agent metrics, condensed for the
// wallboard. Reads the most recent snapshots the execution agent reported —
// whatever their age — and says plainly when they are historical rather than
// live, instead of leaving an empty window.

import { clsx } from "clsx";
import { useMemo } from "react";
import {
  Area,
  ComposedChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ageText, secondsSince } from "@/lib/systemHealth";
import { formatInZone } from "@/lib/time";
import { preferNullable, type OperationalState } from "@/lib/wallboard";
import type { OpsMachine, SystemHealthPoint, SystemHealthResponse } from "@/types/api";

import { KpiTile, Panel, StateChip, StatusDot, TONE } from "./parts";

type Tone = OperationalState | null;

function below(value: number, good: number, bad: OperationalState = "DEGRADED"): OperationalState {
  return value < good ? "HEALTHY" : bad;
}

function fixed(value: number | null | undefined, digits: number): string | null {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : null;
}

interface Kpi {
  title: string;
  value: string | null;
  unit?: string;
  state: Tone;
  note?: string;
  series: (number | null)[];
}

function buildKpis(latest: SystemHealthPoint | null, points: SystemHealthPoint[], live: boolean): Kpi[] {
  // Nullable twins first: the plain fields default to 0 / 100 on the server
  // when an agent reported nothing, and those defaults are not measurements.
  const cpu = latest ? preferNullable(latest.cpu_usage, latest.cpu_usage_pct, "agent reported no CPU") : null;
  const api = latest
    ? preferNullable(latest.api_success_rate, latest.api_success_pct, "agent reported no success rate")
    : null;
  const fill = latest
    ? preferNullable(latest.signal_fill_rate, latest.signal_fill_rate_pct, "agent reported no fill rate")
    : null;

  const series = (pick: (point: SystemHealthPoint) => number | null | undefined) =>
    points.map((point) => {
      const value = pick(point);
      return typeof value === "number" && Number.isFinite(value) ? value : null;
    });

  // Historical figures keep their values but are never presented as current.
  const verdict = (state: OperationalState | null): Tone => (state && !live ? "STALE" : state);
  const cpuValue = cpu?.value ?? null;
  const apiValue = api?.value ?? null;
  const fillValue = fill?.value ?? null;

  return [
    {
      title: "CPU",
      value: fixed(cpuValue, 1),
      unit: "%",
      state: verdict(cpuValue === null ? null : cpuValue < 70 ? "HEALTHY" : cpuValue < 90 ? "DEGRADED" : "CRITICAL"),
      series: series((point) => point.cpu_usage ?? null),
    },
    {
      title: "Memory",
      value: latest ? Math.round(latest.memory_mb).toLocaleString("en-IN") : null,
      unit: "MB",
      state: null,
      note: "no threshold",
      series: series((point) => point.memory_mb),
    },
    {
      title: "Tick rate",
      value: fixed(latest?.tick_rate, 1),
      unit: "/s",
      state: latest && latest.tick_rate > 0 ? verdict("HEALTHY") : null,
      note: latest ? "idle" : undefined,
      series: series((point) => point.tick_rate),
    },
    {
      title: "Tick delay",
      value: fixed(latest?.tick_delay_ms, 2),
      unit: "ms",
      state: latest ? verdict(below(latest.tick_delay_ms, 5)) : null,
      series: series((point) => point.tick_delay_ms),
    },
    {
      title: "Avg latency",
      value: fixed(latest?.avg_latency_ms, 2),
      unit: "ms",
      state: latest ? verdict(below(latest.avg_latency_ms, 10)) : null,
      series: series((point) => point.avg_latency_ms),
    },
    {
      title: "P95 latency",
      value: fixed(latest?.p95_latency_ms, 2),
      unit: "ms",
      state: latest ? verdict(below(latest.p95_latency_ms, 20)) : null,
      series: series((point) => point.p95_latency_ms),
    },
    {
      title: "P99 latency",
      value: fixed(latest?.p99_latency_ms, 2),
      unit: "ms",
      state: latest ? verdict(below(latest.p99_latency_ms, 50, "CRITICAL")) : null,
      series: series((point) => point.p99_latency_ms),
    },
    {
      title: "Queue size",
      value: latest ? String(latest.queue_size) : null,
      state: latest ? verdict(latest.queue_size === 0 ? "HEALTHY" : "DEGRADED") : null,
      series: series((point) => point.queue_size),
    },
    {
      title: "Queue wait",
      value: fixed(latest?.queue_wait_ms, 2),
      unit: "ms",
      state: latest ? verdict(below(latest.queue_wait_ms, 5)) : null,
      series: series((point) => point.queue_wait_ms),
    },
    {
      title: "API success",
      // A percentage (0–100), exactly as the agent pipeline stores it.
      value: fixed(apiValue, 1),
      unit: "%",
      state: verdict(apiValue === null ? null : apiValue >= 99 ? "HEALTHY" : "CRITICAL"),
      series: series((point) => point.api_success_rate ?? null),
    },
    {
      title: "Signal fill",
      value: fixed(fillValue, 1),
      unit: "%",
      state: verdict(fillValue === null ? null : fillValue >= 95 ? "HEALTHY" : "DEGRADED"),
      series: series((point) => point.signal_fill_rate ?? null),
    },
  ];
}

const AGENT_STATE: Record<string, OperationalState> = {
  STABLE: "HEALTHY",
  HEALTHY: "HEALTHY",
  DEGRADED: "DEGRADED",
  WARNING: "DEGRADED",
  UNSTABLE: "CRITICAL",
  CRITICAL: "CRITICAL",
};

function ChartTooltip({
  active,
  payload,
  label: time,
}: {
  active?: boolean;
  payload?: Array<{ value: number; name: string; color?: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg bg-[#0b111b]/95 px-3 py-2 text-xs shadow-xl ring-1 ring-white/10">
      <p className="mb-1 font-data text-slate-400">{time} IST</p>
      {payload.map((entry) => (
        <p key={entry.name} className="font-data tabular-nums" style={{ color: entry.color }}>
          {entry.name}: {typeof entry.value === "number" ? entry.value.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : "—"}
        </p>
      ))}
    </div>
  );
}

const AXIS = { stroke: "#475569", fontSize: 11, tickLine: false } as const;

function ChartFrame({ title, legend, children }: { title: string; legend: [string, string][]; children: React.ReactElement }) {
  return (
    <figure className="flex min-h-[180px] min-w-0 flex-col rounded-xl bg-white/[0.02] p-2.5 ring-1 ring-white/[0.05]">
      <figcaption className="mb-1 flex flex-wrap items-center justify-between gap-2 px-1">
        <span className="text-[clamp(10px,0.6vw,13px)] font-semibold uppercase tracking-[0.12em] text-slate-300">{title}</span>
        <span className="flex flex-wrap items-center gap-3">
          {legend.map(([name, color]) => (
            <span key={name} className="flex items-center gap-1.5 text-[clamp(9px,0.52vw,11px)] text-slate-400">
              <span className="h-0.5 w-3 rounded-full" style={{ background: color }} />
              {name}
            </span>
          ))}
        </span>
      </figcaption>
      <div className="min-h-0 flex-1">
        <ResponsiveContainer width="100%" height="100%">
          {children}
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

export function TelemetryPanel({
  machines,
  activeMachine,
  onSelectMachine,
  health,
  isLoading,
  isError,
  now,
  className,
}: {
  machines: OpsMachine[];
  activeMachine: string;
  onSelectMachine: (id: string) => void;
  health: SystemHealthResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  now: number;
  className?: string;
}) {
  const points = useMemo(() => health?.points ?? [], [health?.points]);
  const latest = health?.latest ?? points.at(-1) ?? null;
  const live = Boolean(health?.is_live);
  const age = secondsSince(health?.last_health_timestamp ?? latest?.timestamp, now);
  const kpis = buildKpis(latest, points, live);

  const chartData = useMemo(
    () =>
      points.map((point) => ({
        label: formatInZone(point.timestamp, "Asia/Kolkata", {
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        }),
        avg: point.avg_latency_ms,
        p95: point.p95_latency_ms,
        p99: point.p99_latency_ms,
        cpu: point.cpu_usage ?? null,
        ticks: point.tick_rate,
      })),
    [points],
  );

  const agentStatus = health?.current_health_status?.toUpperCase() ?? null;
  const panelState: OperationalState | undefined = isError
    ? "UNKNOWN"
    : !latest
      ? "UNKNOWN"
      : !live
        ? "STALE"
        : (AGENT_STATE[agentStatus ?? ""] ?? "UNKNOWN");
  const machineName =
    health?.machine_name ?? machines.find((machine) => machine.id === activeMachine)?.name ?? null;

  const aside = (
    <>
      {machines.length > 1 ? (
        <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Execution machine">
          {machines.map((machine) => {
            const selected = machine.id === activeMachine;
            return (
              <button
                key={machine.id}
                type="button"
                aria-pressed={selected}
                onClick={() => onSelectMachine(machine.id)}
                className={clsx(
                  "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[clamp(10px,0.56vw,12px)] font-medium ring-1 transition-colors",
                  selected
                    ? "bg-accent-500/15 text-accent-200 ring-accent-400/40"
                    : "text-slate-400 ring-white/10 hover:bg-white/5 hover:text-slate-200",
                )}
              >
                <StatusDot state={machine.status === "online" ? "HEALTHY" : "UNKNOWN"} className="size-1.5" />
                {machine.hostname || machine.name || machine.id}
              </button>
            );
          })}
        </div>
      ) : null}
    </>
  );

  return (
    <Panel
      title="Execution telemetry"
      icon="cpu"
      state={panelState}
      aside={aside}
      className={className}
      bodyClassName="flex flex-col gap-3"
    >
      {/* Identity strip: which machine, and how current its numbers are. */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[clamp(10px,0.6vw,13px)]">
        <span className="font-semibold text-slate-100">{machineName ?? "No execution machine"}</span>
        <span className={clsx("flex items-center gap-1.5 font-data font-semibold tracking-[0.1em]", live ? "text-emerald-300" : "text-sky-300")}>
          <StatusDot state={live ? "HEALTHY" : latest ? "STALE" : "UNKNOWN"} className="size-1.5" />
          {live ? "LIVE" : latest ? "HISTORICAL" : "NO DATA"}
        </span>
        <span className="text-slate-500">
          Last report <span className="font-data text-slate-300">{age === null ? "never" : `${ageText(age)} ago`}</span>
        </span>
        {agentStatus ? (
          <span className="text-slate-500">
            Agent says <span className={clsx("font-data font-semibold", TONE[AGENT_STATE[agentStatus] ?? "UNKNOWN"].text)}>{agentStatus}</span>
          </span>
        ) : null}
        <span className="text-slate-500">
          Window <span className="font-data text-slate-300">last {points.length} snapshots</span>
        </span>
      </div>

      {isLoading && !health ? (
        <div className="grid flex-1 place-items-center text-sm text-slate-500">Loading execution telemetry…</div>
      ) : isError && !health ? (
        <div className="grid flex-1 place-items-center text-center">
          <div>
            <StateChip state="UNKNOWN" />
            <p className="mt-2 text-sm text-slate-400">The telemetry store did not answer. No stand-in numbers are shown.</p>
          </div>
        </div>
      ) : !latest ? (
        <div className="grid flex-1 place-items-center text-center">
          <div className="max-w-md">
            <p className="font-data text-sm font-semibold tracking-[0.12em] text-amber-300">NO EXECUTION TELEMETRY YET</p>
            <p className="mt-2 text-sm text-slate-400">
              The execution agent has not sent a system-health snapshot. Figures appear here as soon as it
              reports — nothing is simulated in the meantime.
            </p>
          </div>
        </div>
      ) : (
        <>
          {!live ? (
            <p className="rounded-lg bg-sky-400/[0.07] px-3 py-1.5 text-[clamp(10px,0.6vw,13px)] text-sky-200 ring-1 ring-sky-400/20">
              The agent is not reporting right now. These are its last figures, from {ageText(age)} ago — marked STALE, not current.
            </p>
          ) : null}
          <div className="grid shrink-0 grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
            {kpis.map((kpi) => (
              <KpiTile key={kpi.title} {...kpi} />
            ))}
            <div className="flex min-w-0 flex-col justify-center rounded-xl bg-white/[0.02] px-3 py-2 ring-1 ring-white/[0.05]">
              <span className="text-[clamp(9px,0.52vw,11px)] font-medium uppercase tracking-[0.1em] text-slate-500">Last snapshot</span>
              <span className="font-data text-[clamp(13px,0.85vw,18px)] font-semibold text-slate-100">
                {latest.timestamp
                  ? formatInZone(latest.timestamp, "Asia/Kolkata", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })
                  : "UNKNOWN"}
              </span>
              <span className="text-[clamp(9px,0.52vw,11px)] text-slate-500">IST</span>
            </div>
          </div>

          <div className="grid min-h-0 flex-1 gap-2 lg:grid-cols-2">
            <ChartFrame title="Execution latency (ms)" legend={[["Avg", "#22b8d4"], ["P95", "#fbbf24"], ["P99", "#fb7185"]]}>
              <ComposedChart data={chartData} margin={{ top: 6, right: 8, left: -12, bottom: 0 }}>
                <defs>
                  <linearGradient id="wb-latency" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0" stopColor="#22b8d4" stopOpacity={0.3} />
                    <stop offset="1" stopColor="#22b8d4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
                <XAxis dataKey="label" {...AXIS} minTickGap={40} />
                <YAxis {...AXIS} axisLine={false} width={48} />
                <Tooltip content={<ChartTooltip />} />
                <Area type="monotone" dataKey="avg" name="Avg" stroke="#22b8d4" strokeWidth={1.8} fill="url(#wb-latency)" isAnimationActive={false} />
                <Line type="monotone" dataKey="p95" name="P95" stroke="#fbbf24" strokeWidth={1.4} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="p99" name="P99" stroke="#fb7185" strokeWidth={1.4} dot={false} isAnimationActive={false} />
              </ComposedChart>
            </ChartFrame>
            <ChartFrame title="Load" legend={[["CPU %", "#34d399"], ["Ticks /s", "#a78bfa"]]}>
              <ComposedChart data={chartData} margin={{ top: 6, right: 8, left: -12, bottom: 0 }}>
                <defs>
                  <linearGradient id="wb-cpu" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0" stopColor="#34d399" stopOpacity={0.28} />
                    <stop offset="1" stopColor="#34d399" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
                <XAxis dataKey="label" {...AXIS} minTickGap={40} />
                <YAxis yAxisId="pct" {...AXIS} axisLine={false} width={40} domain={[0, 100]} />
                <YAxis yAxisId="ticks" orientation="right" {...AXIS} axisLine={false} width={40} />
                <Tooltip content={<ChartTooltip />} />
                <Area yAxisId="pct" type="monotone" dataKey="cpu" name="CPU %" stroke="#34d399" strokeWidth={1.8} fill="url(#wb-cpu)" connectNulls={false} isAnimationActive={false} />
                <Line yAxisId="ticks" type="monotone" dataKey="ticks" name="Ticks /s" stroke="#a78bfa" strokeWidth={1.4} dot={false} isAnimationActive={false} />
              </ComposedChart>
            </ChartFrame>
          </div>
        </>
      )}
    </Panel>
  );
}
