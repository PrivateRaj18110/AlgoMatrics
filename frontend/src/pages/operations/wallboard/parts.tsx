// Visual building blocks of the operations wallboard. Always dark: the board is
// meant for a wall screen, whatever the console theme is.
//
// Every state is printed as a word next to its colour — colour alone never
// carries the meaning — and a value we do not have prints UNKNOWN or "—",
// never a zero.

import { clsx } from "clsx";
import { useId } from "react";

import { Glyph, type GlyphName } from "@/components/icons";
import type { OperationalState, Reading } from "@/lib/wallboard";

export const TONE: Record<
  OperationalState,
  { dot: string; text: string; chip: string; bar: string; stroke: string }
> = {
  HEALTHY: {
    dot: "bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.7)]",
    text: "text-emerald-300",
    chip: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/30",
    bar: "bg-emerald-400",
    stroke: "#34d399",
  },
  DEGRADED: {
    dot: "bg-orange-400 shadow-[0_0_10px_rgba(251,146,60,0.7)]",
    text: "text-orange-300",
    chip: "bg-orange-400/10 text-orange-300 ring-orange-400/35",
    bar: "bg-orange-400",
    stroke: "#fb923c",
  },
  STALE: {
    dot: "bg-sky-400 shadow-[0_0_10px_rgba(56,189,248,0.6)]",
    text: "text-sky-300",
    chip: "bg-sky-400/10 text-sky-300 ring-sky-400/30",
    bar: "bg-sky-400",
    stroke: "#38bdf8",
  },
  CRITICAL: {
    dot: "bg-rose-400 shadow-[0_0_12px_rgba(251,113,133,0.8)]",
    text: "text-rose-300",
    chip: "bg-rose-500/15 text-rose-300 ring-rose-400/40",
    bar: "bg-rose-400",
    stroke: "#fb7185",
  },
  // Amber, never grey-green: not being able to say is not the same as fine.
  UNKNOWN: {
    dot: "bg-amber-300/90",
    text: "text-amber-300",
    chip: "bg-amber-400/10 text-amber-300 ring-amber-400/30",
    bar: "bg-amber-300/80",
    stroke: "#fcd34d",
  },
};

/** Neutral styling for a figure that makes no health claim (e.g. memory in MB). */
export const NEUTRAL_STROKE = "#7ee4f5";

export const label = "text-[clamp(10px,0.6vw,13px)] font-medium uppercase tracking-[0.12em] text-slate-400";

export function StatusDot({ state, className }: { state: OperationalState; className?: string }) {
  return (
    <span
      aria-hidden
      className={clsx(
        "inline-block size-2 shrink-0 rounded-full",
        TONE[state].dot,
        state === "HEALTHY" && "am-live-dot",
        state === "CRITICAL" && "animate-pulse",
        className,
      )}
    />
  );
}

export function StateChip({ state, className }: { state: OperationalState; className?: string }) {
  return (
    <span
      className={clsx(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 font-data text-[clamp(9px,0.55vw,12px)] font-semibold tracking-[0.12em] ring-1",
        TONE[state].chip,
        className,
      )}
    >
      <StatusDot state={state} className="size-1.5" />
      {state}
    </span>
  );
}

/** A glass panel with a titled header. */
export function Panel({
  title,
  icon,
  state,
  aside,
  className,
  bodyClassName,
  children,
}: {
  title: string;
  icon: GlyphName;
  state?: OperationalState;
  aside?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      aria-label={title}
      className={clsx(
        "flex min-h-0 min-w-0 flex-col rounded-2xl bg-[#0a1019]/85 ring-1 ring-white/[0.07] shadow-[0_20px_60px_rgba(0,0,0,0.35)]",
        className,
      )}
    >
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-x-3 gap-y-1.5 border-b border-white/[0.06] px-4 py-2.5">
        <h2 className="flex items-center gap-2 text-[clamp(11px,0.68vw,15px)] font-semibold uppercase tracking-[0.14em] text-slate-200">
          <Glyph name={icon} className="size-4 text-accent-400" />
          {title}
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          {aside}
          {state ? <StateChip state={state} /> : null}
        </div>
      </header>
      <div className={clsx("min-h-0 flex-1 overflow-y-auto p-3", bodyClassName)}>{children}</div>
    </section>
  );
}

/** One component in the platform status matrix. */
export function ServiceTile({
  icon,
  title,
  reading,
}: {
  icon: GlyphName;
  title: string;
  reading: Reading<string>;
}) {
  const tone = TONE[reading.state];
  const value = reading.state === "UNKNOWN" || reading.value === null ? "UNKNOWN" : reading.value;
  return (
    <article
      aria-label={title}
      className="relative flex min-w-0 flex-col gap-0.5 overflow-hidden rounded-xl bg-white/[0.03] py-2 pl-3.5 pr-3 ring-1 ring-white/[0.07]"
    >
      <span aria-hidden className={clsx("absolute inset-y-2 left-0 w-[3px] rounded-r-full", tone.bar)} />
      <h3 className={clsx(label, "flex min-w-0 items-center gap-1.5")}>
        <Glyph name={icon} className="size-3.5 text-slate-500" />
        <span className="truncate">{title}</span>
      </h3>
      <p
        className={clsx(
          "truncate font-data text-[clamp(14px,0.95vw,22px)] font-semibold tabular-nums",
          reading.state === "UNKNOWN" ? "text-amber-200/80" : "text-slate-50",
        )}
      >
        {value}
      </p>
      <p className="flex min-w-0 items-center gap-1.5 text-[clamp(10px,0.56vw,12px)]" title={reading.detail ?? undefined}>
        <span className={clsx("flex shrink-0 items-center gap-1 font-data font-semibold tracking-[0.08em]", tone.text)}>
          <StatusDot state={reading.state} className="size-1.5" />
          {reading.state}
        </span>
        {reading.detail ? <span className="truncate text-slate-500">· {reading.detail}</span> : null}
      </p>
    </article>
  );
}

/** A tiny trend line. Fewer than two points draws a flat baseline, not a guess. */
export function Sparkline({
  values,
  color,
  className,
}: {
  values: readonly (number | null | undefined)[];
  color: string;
  className?: string;
}) {
  const gradient = `spark-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const clean = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (clean.length < 2) {
    return (
      <div aria-hidden className={clsx("flex items-end", className)}>
        <div className="h-px w-full bg-white/10" />
      </div>
    );
  }
  const min = Math.min(...clean);
  const max = Math.max(...clean);
  const span = max - min || 1;
  const points = clean
    .map((value, index) => {
      const x = (index / (clean.length - 1)) * 100;
      const y = 28 - ((value - min) / span) * 25;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  return (
    <svg viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden className={className}>
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity="0.32" />
          <stop offset="1" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`0,30 ${points} 100,30`} fill={`url(#${gradient})`} />
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.6"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

/** One execution metric: value, its own verdict, and the recent trend. */
export function KpiTile({
  title,
  value,
  unit,
  state,
  note,
  series,
}: {
  title: string;
  value: string | null;
  unit?: string;
  /** null = this figure makes no health claim (no threshold is known for it). */
  state: OperationalState | null;
  note?: string;
  series: readonly (number | null | undefined)[];
}) {
  const shown = value === null ? "UNKNOWN" : value;
  return (
    <div
      role="group"
      aria-label={title}
      className="flex min-h-0 min-w-0 flex-col rounded-xl bg-white/[0.025] px-3 pb-1.5 pt-2 ring-1 ring-white/[0.06]"
    >
      <div className="flex items-center justify-between gap-2">
        <span className={clsx(label, "truncate")}>{title}</span>
        {state ? (
          <span className={clsx("flex shrink-0 items-center gap-1 font-data text-[clamp(9px,0.5vw,11px)] font-semibold", TONE[state].text)}>
            <StatusDot state={state} className="size-1.5" />
            {state}
          </span>
        ) : note ? (
          <span className="shrink-0 font-data text-[clamp(9px,0.5vw,11px)] text-slate-500">{note}</span>
        ) : null}
      </div>
      <p className="mt-0.5 flex items-baseline gap-1">
        <span
          className={clsx(
            "font-data text-[clamp(16px,1.2vw,26px)] font-semibold tabular-nums",
            value === null ? "text-amber-200/80" : "text-slate-50",
          )}
        >
          {shown}
        </span>
        {value !== null && unit ? <span className="text-[clamp(10px,0.6vw,13px)] text-slate-500">{unit}</span> : null}
      </p>
      <Sparkline
        values={series}
        color={state ? TONE[state].stroke : NEUTRAL_STROKE}
        className="mt-auto h-[clamp(18px,2.2vh,34px)] w-full"
      />
    </div>
  );
}

/** A 0–100 utilisation bar. A missing value shows an empty track and "—". */
export function Gauge({ name, value }: { name: string; value: number | null | undefined }) {
  const known = typeof value === "number" && Number.isFinite(value);
  const pct = known ? Math.min(100, Math.max(0, value)) : 0;
  const color = !known ? "" : pct >= 90 ? "bg-rose-400" : pct >= 75 ? "bg-orange-400" : "bg-emerald-400";
  return (
    <div className="flex items-center gap-2" title={known ? undefined : `${name} not reported`}>
      <span className="w-7 shrink-0 font-data text-[clamp(8px,0.48vw,11px)] text-slate-500">{name}</span>
      <div className="h-1.5 min-w-6 flex-1 overflow-hidden rounded-full bg-white/[0.07]">
        {known ? <div className={clsx("h-full rounded-full", color)} style={{ width: `${pct}%` }} /> : null}
      </div>
      <span className="w-8 shrink-0 text-right font-data text-[clamp(9px,0.52vw,12px)] tabular-nums text-slate-300">
        {known ? `${Math.round(value)}%` : "—"}
      </span>
    </div>
  );
}

/** A compact label/value pair. Values print UNKNOWN, never a bare 0. */
export function Stat({ title, reading, format }: { title: string; reading: Reading<number | string>; format?: (value: number) => string }) {
  const text =
    reading.state === "UNKNOWN" || reading.value === null
      ? "UNKNOWN"
      : typeof reading.value === "number"
        ? (format ?? String)(reading.value)
        : reading.value;
  return (
    <div className="flex min-w-0 flex-col rounded-lg bg-white/[0.025] px-2.5 py-1 ring-1 ring-white/[0.05]">
      <dt className="truncate text-[clamp(9px,0.52vw,11px)] font-medium uppercase tracking-[0.1em] text-slate-500">{title}</dt>
      <dd
        className={clsx(
          "truncate font-data text-[clamp(12px,0.75vw,17px)] font-semibold tabular-nums",
          reading.state === "UNKNOWN" ? "text-amber-200/80" : "text-slate-100",
        )}
        title={reading.detail ?? undefined}
      >
        {text}
      </dd>
    </div>
  );
}
