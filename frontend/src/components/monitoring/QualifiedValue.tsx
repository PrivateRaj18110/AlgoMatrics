// The one place a monitoring value becomes pixels.
//
// Every knowledge state the producer can send gets its own visible treatment,
// and none renders as a bare number pretending to be a fact. UNKNOWN renders the
// word UNKNOWN — not 0, not "—", not an empty cell, not a green tick. A reader
// glancing at this must be able to tell "the value is 0" from "nobody knows the
// value" without hovering.
//
// The producer writes `{"value": null, "status": "UNKNOWN", "reason": ...}`.
// The explicit null is preserved on the wire and is simply not rendered as a
// value here; it is never read as zero and never stripped upstream.

import { clsx } from "clsx";

import {
  formatInstant,
  isQualified,
  isRecognisedStatus,
  statusLabel,
  statusMeaning,
  type QualifiedValue as QualifiedValueModel,
} from "@/lib/monitoring";

const STATUS_CLASS: Record<string, string> = {
  // Observed values are the only ones that get to look like plain content.
  KNOWN: "text-slate-900",
  OBSERVED: "text-slate-900",
  // Absence-of-knowledge: something is wrong with our knowledge, not
  // necessarily with the trading system.
  UNKNOWN: "bg-amber-100 text-amber-900 ring-1 ring-amber-300",
  INCOMPLETE: "bg-amber-50 text-amber-800 ring-1 ring-amber-200",
  // Time and trust problems: the number on screen may mislead.
  STALE: "bg-orange-100 text-orange-900 ring-1 ring-orange-300",
  UNTRUSTED: "bg-rose-100 text-rose-900 ring-1 ring-rose-300",
  // Structural absences: nothing is wrong, the field does not apply.
  UNSUPPORTED: "bg-slate-100 text-slate-600 ring-1 ring-slate-300",
  NOT_APPLICABLE: "bg-slate-100 text-slate-500 ring-1 ring-slate-200",
  // Non-live provenance, never mistakable for real trading.
  SIMULATED: "bg-violet-100 text-violet-900 ring-1 ring-violet-300",
  SYNTHETIC_CLOCK: "bg-violet-50 text-violet-800 ring-1 ring-violet-200",
};

// An unfamiliar state is shown loudly rather than quietly — the contract
// forbids reading it as healthy, so it must not look ordinary.
const UNRECOGNISED_CLASS = "bg-fuchsia-100 text-fuchsia-900 ring-1 ring-fuchsia-400";

const PLAIN_STATUSES = new Set(["KNOWN", "OBSERVED"]);

function formatScalar(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

export interface QualifiedValueProps {
  value: unknown;
  /** Appended to a rendered value, e.g. "ms" or "%". */
  unit?: string;
  className?: string;
}

/**
 * Render one qualified value.
 *
 * A bare scalar reaching this component is a contract violation upstream and is
 * labelled as such rather than displayed as though it were qualified — silently
 * accepting it would hide exactly the regression this component exists to catch.
 */
export function QualifiedValue({ value, unit, className }: QualifiedValueProps) {
  if (!isQualified(value)) {
    return (
      <span
        className={clsx(
          "inline-flex items-center rounded px-1.5 py-0.5 font-mono text-xs",
          "bg-rose-100 text-rose-900 ring-1 ring-rose-300",
          className,
        )}
        title="This value arrived without a status. Monitoring values must be qualified."
      >
        UNQUALIFIED
      </span>
    );
  }

  const qualified = value as QualifiedValueModel;
  const { status } = qualified;
  // The producer sends `value: null` for unknowns. Present-but-null is not a
  // value to display; it is the absence the status already describes.
  const hasValue = qualified.value !== undefined && qualified.value !== null;
  const rendered = hasValue ? formatScalar(qualified.value) : "";
  const recognised = isRecognisedStatus(status);

  const detail = [
    statusMeaning(status),
    qualified.reason ? `Reason: ${qualified.reason}` : null,
  ]
    .filter(Boolean)
    .join("\n");

  if (PLAIN_STATUSES.has(status) && hasValue) {
    return (
      <span className={clsx("font-mono text-sm text-slate-900", className)} title={detail}>
        {rendered}
        {unit ? <span className="ml-0.5 text-slate-500">{unit}</span> : null}
      </span>
    );
  }

  return (
    <span className={clsx("inline-flex items-baseline gap-1.5", className)} title={detail}>
      {/* A value stays visible where one exists — a stale reading is still the
          last thing the source knew. What changes is that it no longer stands
          alone, unqualified, as if it were current fact. */}
      {hasValue ? (
        <span className="font-mono text-sm text-slate-700">
          {rendered}
          {unit ? <span className="ml-0.5 text-slate-500">{unit}</span> : null}
        </span>
      ) : null}
      <span
        className={clsx(
          "inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-wide",
          recognised ? (STATUS_CLASS[status] ?? UNRECOGNISED_CLASS) : UNRECOGNISED_CLASS,
        )}
      >
        {statusLabel(status)}
      </span>
    </span>
  );
}

/** A labelled row of one qualified value, for detail panels. */
export function QualifiedField({
  label,
  value,
  unit,
}: {
  label: string;
  value: unknown;
  unit?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1">
      <span className="text-xs text-slate-500">{label}</span>
      <QualifiedValue value={value} unit={unit} />
    </div>
  );
}

/** An instant rendered with the same "absence is information" rule. */
export function Instant({ value }: { value: string | null | undefined }) {
  return <span className="font-mono text-[11px] text-slate-500">{formatInstant(value)}</span>;
}
