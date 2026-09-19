// Source-asserted state badges.
//
// The previous version of this file re-evaluated a validity horizon on a
// one-second timer. monitoring.v1 has no horizon: the producer asserts its own
// freshness, and the contract requires the receiver to use source validity and
// trust rather than arrival time.
//
// So there is no timer and no clock arithmetic here. These components read what
// the source said and show it. That is a deliberate reduction in cleverness: a
// badge that can change on its own is a badge that can lie on its own.

import { clsx } from "clsx";

import {
  environmentMeaning,
  formatInstant,
  isLiveMarket,
  isRecognisedStatus,
  readFreshness,
  readStatus,
  statusMeaning,
} from "@/lib/monitoring";

const STATE_CLASS: Record<string, string> = {
  LIVE: "bg-emerald-100 text-emerald-900 ring-emerald-300 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-400/35",
  FRESH: "bg-emerald-100 text-emerald-900 ring-emerald-300 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-400/35",
  OBSERVED: "bg-emerald-100 text-emerald-900 ring-emerald-300 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-400/35",
  STALE: "bg-orange-100 text-orange-900 ring-orange-300 dark:bg-orange-500/10 dark:text-orange-300 dark:ring-orange-400/35",
  // Not green. Not being able to say is not the same as saying it is fine.
  UNKNOWN: "bg-amber-100 text-amber-900 ring-amber-300 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-400/35",
  INCOMPLETE: "bg-amber-100 text-amber-900 ring-amber-300 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-400/35",
  UNTRUSTED: "bg-rose-100 text-rose-900 ring-rose-300 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-400/35",
};

const UNRECOGNISED = "bg-fuchsia-100 text-fuchsia-900 ring-fuchsia-400 dark:bg-fuchsia-500/20 dark:text-fuchsia-200 dark:ring-fuchsia-400/70";

function badgeClass(state: string | null): string {
  if (state === null) return "bg-amber-100 text-amber-900 ring-amber-300 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-400/35";
  if (!isRecognisedStatus(state)) return UNRECOGNISED;
  return STATE_CLASS[state] ?? UNRECOGNISED;
}

/**
 * The source's freshness assertion, with the time the source derived it.
 *
 * `derivedAt` is the **source's** clock, not ours. It is shown beside the state
 * because the first question about any monitoring panel is "as of when?", and
 * answering it with our own receipt time would be answering a different question.
 */
export function FreshnessBadge({
  freshness,
  className,
}: {
  freshness: Record<string, unknown> | undefined | null;
  className?: string;
}) {
  const read = readFreshness(freshness);
  return (
    <span className={clsx("inline-flex flex-wrap items-baseline gap-2", className)}>
      <span
        className={clsx(
          "inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-wide ring-1",
          badgeClass(read.source),
        )}
        title={
          read.source
            ? `${statusMeaning(read.source)}${read.reason ? `\nReason: ${read.reason}` : ""}`
            : "The source did not state a freshness value for this observation."
        }
      >
        {read.source ?? "FRESHNESS NOT STATED"}
      </span>
      <span className="font-mono text-[11px] text-slate-500">
        SOURCE DERIVED: {formatInstant(read.derivedAt)}
      </span>
      {read.source && !read.recognised ? (
        <span className="text-[11px] text-fuchsia-700 dark:text-fuchsia-300">unrecognised state, shown unmodified</span>
      ) : null}
    </span>
  );
}

/**
 * Market reality, from the producer's `environment` field.
 *
 * Anything that is not `live_trading` is marked distinctly. Historical and
 * simulated data on a monitoring screen is legitimate and useful; it is only
 * dangerous when indistinguishable from live trading.
 */
export function EnvironmentBadge({
  sourceEnvironment,
  className,
}: {
  sourceEnvironment: string;
  className?: string;
}) {
  const live = isLiveMarket(sourceEnvironment);
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-wide ring-1",
        live
          ? "bg-emerald-100 text-emerald-900 ring-emerald-400 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-400/35"
          : "bg-violet-100 text-violet-900 ring-violet-400 dark:bg-violet-500/10 dark:text-violet-300 dark:ring-violet-400/35",
        className,
      )}
      title={environmentMeaning(sourceEnvironment)}
    >
      {sourceEnvironment}
    </span>
  );
}

/**
 * The capture identifiers the producer sent.
 *
 * Rendered as the list it is. Never collapsed into LIVE / HISTORICAL — those are
 * not what this field means, and inventing a classification from it would be
 * exactly the reinterpretation the contract forbids.
 */
export function RuntimeBadges({
  runtime,
  className,
}: {
  runtime: unknown[];
  className?: string;
}) {
  if (!runtime || runtime.length === 0) {
    return (
      <span
        className={clsx(
          "inline-flex items-center rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-amber-900 ring-1 ring-amber-300 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-400/35",
          className,
        )}
        title="The source listed no capture identifiers for this observation."
      >
        NO CAPTURE REPORTED
      </span>
    );
  }
  return (
    <span className={clsx("inline-flex flex-wrap items-center gap-1", className)}>
      {runtime.map((entry, index) => (
        <span
          key={`${String(entry)}-${index}`}
          className="inline-flex items-center rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-700 ring-1 ring-slate-300 dark:bg-white/[0.05] dark:text-slate-300 dark:ring-white/15"
          title="A capture identifier reported by the source."
        >
          {String(entry)}
        </span>
      ))}
    </span>
  );
}

/** Trust, exactly as the producer stated it. */
export function TrustBadge({
  trust,
  className,
}: {
  trust: Record<string, unknown> | undefined | null;
  className?: string;
}) {
  const status = readStatus(trust);
  if (status === null) {
    return (
      <span
        className={clsx(
          "inline-flex items-center rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-amber-900 ring-1 ring-amber-300 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-400/35",
          className,
        )}
        title="The source did not state a trust status for this observation."
      >
        TRUST NOT STATED
      </span>
    );
  }
  const weak = status === "UNTRUSTED" || status === "UNKNOWN";
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-wide ring-1",
        weak ? "bg-rose-100 text-rose-900 ring-rose-300 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-400/35" : "bg-slate-100 text-slate-700 ring-slate-300 dark:bg-white/[0.05] dark:text-slate-300 dark:ring-white/15",
        className,
      )}
      title="Stated by the source. Successful delivery never upgrades this."
    >
      {status}
    </span>
  );
}

/** Coverage status, exactly as the producer stated it. */
export function CoverageBadge({
  coverage,
  className,
}: {
  coverage: Record<string, unknown> | undefined | null;
  className?: string;
}) {
  const status = readStatus(coverage);
  const captureStatus =
    typeof coverage?.capture_status === "string" ? coverage.capture_status : null;
  if (status === null) {
    return (
      <span
        className={clsx(
          "inline-flex items-center rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-amber-900 ring-1 ring-amber-300 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-400/35",
          className,
        )}
        title="The source did not state coverage. No percentage is computed here."
      >
        COVERAGE NOT STATED
      </span>
    );
  }
  return (
    <span className={clsx("inline-flex items-baseline gap-1", className)}>
      <span
        className={clsx(
          "inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-wide ring-1",
          badgeClass(status),
        )}
        title="Stated by the source. No coverage ratio is computed from message arrival."
      >
        {status}
      </span>
      {captureStatus ? (
        <span className="font-mono text-[10px] text-slate-500">{captureStatus}</span>
      ) : null}
    </span>
  );
}
