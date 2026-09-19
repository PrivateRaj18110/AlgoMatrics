// Small building blocks shared by the AI-CIO tabs.

import { clsx } from "clsx";

import { DIRECTION_LABEL, type Catalyst, type MoveDirection } from "@/lib/movers";

const IST_TIME = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Kolkata",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const IST_DAY = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short" });

/** "18:32" today, "18 Sep 18:32" otherwise (IST). */
export function istStamp(value: string | null | undefined, today?: string): string {
  if (!value) return "—";
  const at = new Date(value);
  if (Number.isNaN(at.getTime())) return "—";
  const day = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(at);
  return day === today ? IST_TIME.format(at) : `${IST_DAY.format(at)} ${IST_TIME.format(at)}`;
}

export function istDay(value: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    weekday: "short",
    day: "2-digit",
    month: "short",
  }).format(new Date(`${value}T12:00:00+05:30`));
}

/** Probability as a ring: the arc is the chance, the number is the chance. */
export function ProbabilityRing({ probability, size = 56 }: { probability: number; size?: number }) {
  const pct = Math.max(0, Math.min(1, probability));
  const radius = 15.5;
  const circumference = 2 * Math.PI * radius;
  const tone = pct >= 0.5 ? "#34d399" : pct >= 0.25 ? "#22b8d4" : pct >= 0.1 ? "#fbbf24" : "#94a3b8";
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg viewBox="0 0 36 36" className="size-full -rotate-90" aria-hidden>
        <circle cx="18" cy="18" r={radius} fill="none" stroke="currentColor" strokeWidth="3" className="text-slate-200 dark:text-white/[0.08]" />
        <circle
          cx="18"
          cy="18"
          r={radius}
          fill="none"
          stroke={tone}
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray={`${pct * circumference} ${circumference}`}
        />
      </svg>
      <span className="absolute inset-0 grid place-items-center font-data text-[13px] font-semibold tabular-nums text-slate-900 dark:text-white">
        {pct < 0.01 ? "<1" : Math.round(pct * 100)}
        <span className="text-[9px] font-medium text-slate-500">%</span>
      </span>
    </div>
  );
}

export function ChanceBar({ probability }: { probability: number }) {
  const pct = Math.max(0, Math.min(1, probability));
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-200 dark:bg-white/[0.08]">
        <div
          className={clsx(
            "h-full rounded-full",
            pct >= 0.5 ? "bg-profit-500" : pct >= 0.25 ? "bg-accent-500" : pct >= 0.1 ? "bg-amber-400" : "bg-slate-400",
          )}
          style={{ width: `${Math.max(2, pct * 100)}%` }}
        />
      </div>
      <span className="w-10 font-data text-xs tabular-nums text-slate-700 dark:text-slate-200">
        {pct < 0.01 ? "<1%" : `${(pct * 100).toFixed(pct < 0.1 ? 1 : 0)}%`}
      </span>
    </div>
  );
}

const DIRECTION_STYLE: Record<MoveDirection, string> = {
  up: "bg-profit-500/10 text-profit-700 ring-profit-500/25 dark:text-profit-400",
  down: "bg-loss-500/10 text-loss-700 ring-loss-500/25 dark:text-loss-400",
  either: "bg-slate-500/10 text-slate-600 ring-slate-500/20 dark:text-slate-300",
};

export function DirectionChip({ direction, confidence }: { direction: MoveDirection; confidence?: string }) {
  const arrow = direction === "up" ? "▲" : direction === "down" ? "▼" : "↕";
  return (
    <span
      className={clsx(
        "inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1",
        DIRECTION_STYLE[direction],
      )}
    >
      <span aria-hidden>{arrow}</span>
      {DIRECTION_LABEL[direction]}
      {confidence && direction !== "either" ? <span className="font-normal opacity-70">· {confidence}</span> : null}
    </span>
  );
}

/** Five dots: how much a filing is likely to matter. */
export function ImpactMeter({ impact }: { impact: number }) {
  const filled = Math.round(Math.max(0, Math.min(1, impact)) * 5);
  return (
    <span className="inline-flex items-center gap-0.5" title={`Impact ${Math.round(impact * 100)} / 100`} aria-label={`Impact ${Math.round(impact * 100)} of 100`}>
      {Array.from({ length: 5 }, (_, i) => (
        <span
          key={i}
          className={clsx(
            "size-1.5 rounded-full",
            i < filled
              ? impact >= 0.6
                ? "bg-accent-500"
                : impact >= 0.4
                  ? "bg-accent-400/80"
                  : "bg-slate-400"
              : "bg-slate-200 dark:bg-white/[0.08]",
          )}
        />
      ))}
    </span>
  );
}

export function CatalystChip({ catalyst }: { catalyst: Catalyst }) {
  const tone =
    catalyst.direction > 0
      ? "border-profit-500/30 text-profit-700 dark:text-profit-400"
      : catalyst.direction < 0
        ? "border-loss-500/30 text-loss-700 dark:text-loss-400"
        : "border-slate-300 text-slate-600 dark:border-white/10 dark:text-slate-300";
  const body = (
    <>
      {catalyst.label}
      {catalyst.url ? <span aria-hidden className="opacity-60">↗</span> : null}
    </>
  );
  const className = clsx("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium", tone);
  return catalyst.url ? (
    <a href={catalyst.url} target="_blank" rel="noreferrer noopener" className={clsx(className, "hover:bg-slate-50 dark:hover:bg-white/5")} title={catalyst.title}>
      {body}
    </a>
  ) : (
    <span className={className} title={catalyst.title}>
      {body}
    </span>
  );
}

export function Metric({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: "good" | "bad" }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-medium tracking-wide text-slate-500 uppercase">{label}</p>
      <p
        className={clsx(
          "mt-0.5 font-data text-xl font-semibold tabular-nums",
          tone === "good" ? "text-profit-600 dark:text-profit-400" : tone === "bad" ? "text-loss-600 dark:text-loss-400" : "text-slate-900 dark:text-white",
        )}
      >
        {value}
      </p>
      {hint ? <p className="mt-0.5 text-[11px] text-slate-500">{hint}</p> : null}
    </div>
  );
}
