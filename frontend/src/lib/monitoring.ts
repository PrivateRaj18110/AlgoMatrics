// monitoring.v1 — client-side model of what the LLS producer published.
//
// The previous version of this file evaluated a validity horizon (`stale_after`)
// against the browser clock on a one-second timer. **monitoring.v1 has no
// horizon.** The producer asserts freshness as a state derived from source
// validity and trust, and the contract is explicit that receiver freshness must
// use those and not arrival time.
//
// So there is no timer here, and no `evaluateFreshness`. Their absence is the
// guarantee: nothing in the browser can turn a value stale or fresh on its own,
// which means neither of the two failure modes the old model allowed can recur —
//
//   * a value the source called STALE shown as live because data arrived recently
//   * a value the source called fresh shown as stale because a local timer expired
//
// There is also deliberately no `valueOr(fallback)` helper. That is the function
// that turns a dead feed into a healthy-looking dashboard.

/** A qualified value as the producer writes it. */
export interface QualifiedValue<T = unknown> {
  status: string;
  /** Present and explicitly `null` when unknown. Never stripped. */
  value?: T | null;
  reason?: string;
}

/**
 * Knowledge states seen in the producer's contract and fixtures.
 *
 * Not used to validate. An unfamiliar status is preserved and shown as-is: the
 * contract says a client must not reinterpret an unfamiliar value as healthy.
 */
export const KNOWN_STATUSES = [
  "KNOWN",
  "OBSERVED",
  "UNKNOWN",
  "STALE",
  "UNTRUSTED",
  "INCOMPLETE",
  "UNSUPPORTED",
  "NOT_APPLICABLE",
  "SIMULATED",
  "SYNTHETIC_CLOCK",
] as const;

export type KnownStatus = (typeof KNOWN_STATUSES)[number];

export interface MonitoringStateItem {
  message_type: string;
  capture_ref: string | null;
  source_id: string;
  source_instance: string;
  /** The wire value, a string. Never re-rendered as a number. */
  source_sequence: string;
  message_id: string;
  /** The producer's market reality: live_trading, offline_fixture, replay, … */
  source_environment: string;
  /** This deployment's own tier. Never derived from the above. */
  receiver_deployment_environment: string;
  /** An array of capture identifiers, not an enum. */
  runtime: unknown[];
  source_as_of: Record<string, unknown>;
  generated_at: string | null;
  received_at: string | null;
  freshness: Record<string, unknown>;
  trust: Record<string, unknown>;
  coverage: Record<string, unknown>;
  payload: Record<string, unknown>;
}

export interface MonitoringStateResponse {
  receiver_deployment_environment: string;
  configured: boolean;
  count: number;
  items: MonitoringStateItem[];
}

export interface MonitoringSourceRow {
  source_id: string;
  source_instance: string;
  last_accepted_sequence: string;
  last_accepted_message_id: string;
  accepted_count: number;
  duplicate_count: number;
  /** Observability. A refused message was never accepted. */
  refused_gap_count: number;
  refused_old_count: number;
  observed_refusals: { expected?: number; received?: number; action?: string; at?: string }[];
  first_seen_at: string | null;
  last_seen_at: string | null;
}

/** True when `input` is a producer qualified value rather than a bare scalar. */
export function isQualified(input: unknown): input is QualifiedValue {
  return (
    typeof input === "object" &&
    input !== null &&
    !Array.isArray(input) &&
    typeof (input as { status?: unknown }).status === "string"
  );
}

export function isRecognisedStatus(status: string): boolean {
  return (KNOWN_STATUSES as readonly string[]).includes(status);
}

/**
 * The source's freshness assertion — read, never computed.
 *
 * Returns exactly what the producer said. If it said nothing, that is reported
 * as "not stated" rather than being filled in with a guess.
 */
export function readFreshness(freshness: Record<string, unknown> | undefined | null): {
  source: string | null;
  derivedAt: string | null;
  reason: string | null;
  recognised: boolean;
} {
  const source = typeof freshness?.source === "string" ? freshness.source : null;
  return {
    source,
    derivedAt: typeof freshness?.derived_at === "string" ? freshness.derived_at : null,
    reason: typeof freshness?.reason === "string" ? freshness.reason : null,
    recognised: source !== null && isRecognisedStatus(source),
  };
}

export function readStatus(node: Record<string, unknown> | undefined | null): string | null {
  return typeof node?.status === "string" ? node.status : null;
}

/** What each state means, for a tooltip or inline explanation. */
export function statusMeaning(status: string): string {
  switch (status) {
    case "KNOWN":
    case "OBSERVED":
      return "Observed by the source.";
    case "UNKNOWN":
      return "The source cannot determine this. It is not zero and not empty.";
    case "STALE":
      return "The source asserts this is past its validity. It is not live.";
    case "UNTRUSTED":
      return "A value exists, but the source does not vouch for it.";
    case "INCOMPLETE":
      return "A partial answer — some contributing evidence is missing.";
    case "UNSUPPORTED":
      return "This build of the source cannot produce this field at all.";
    case "NOT_APPLICABLE":
      return "This field has no meaning in this context.";
    case "SIMULATED":
      return "Produced by simulation, not live observation.";
    case "SYNTHETIC_CLOCK":
      return "Produced under an artificial clock; timings are not wall-clock.";
    default:
      // Unfamiliar, and explicitly not assumed to mean healthy.
      return "The source used a state this dashboard does not recognise. It is shown unmodified.";
  }
}

/** Human label. Always a word, never a dash. */
export function statusLabel(status: string): string {
  if (status === "NOT_APPLICABLE") return "N/A";
  if (status === "SYNTHETIC_CLOCK") return "SYNTHETIC CLOCK";
  return status;
}

/**
 * Whether a source environment describes real trading.
 *
 * Derived from the producer's own `environment` field — which is the only place
 * this is expressed. `runtime` is an array of capture identifiers and is never
 * used for this.
 */
export function isLiveMarket(sourceEnvironment: string): boolean {
  return sourceEnvironment === "live_trading";
}

export function environmentMeaning(sourceEnvironment: string): string {
  switch (sourceEnvironment) {
    case "live_trading":
      return "Real trading against a live broker.";
    case "broker_sandbox":
      return "Broker sandbox — not real money.";
    case "live_market_paper":
      return "Live market data, paper execution.";
    case "offline_live_shaped":
      return "Offline data shaped like live; not live.";
    case "replay":
      return "Recorded input re-processed.";
    case "offline_fixture":
      return "An offline fixture. Not live trading.";
    case "unknown":
      return "The source could not characterise this run.";
    default:
      return "An environment this dashboard does not recognise. Shown unmodified.";
  }
}

/**
 * Format an instant, or say plainly that there isn't one.
 *
 * Returns `"NOT REPORTED"` rather than an em-dash: on a monitoring surface the
 * absence of a timestamp is information and should read as information.
 */
export function formatInstant(value: string | null | undefined): string {
  if (!value) return "NOT REPORTED";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return "NOT REPORTED";
  return new Date(parsed).toISOString().replace("T", " ").replace(".000Z", "Z");
}

/** Every qualified value in a document, as `[path, status]` pairs. */
export function walkQualified(node: unknown, path = ""): [string, string][] {
  const found: [string, string][] = [];
  if (isQualified(node)) {
    found.push([path || "$", node.status]);
    return found;
  }
  if (Array.isArray(node)) {
    node.forEach((item, index) => found.push(...walkQualified(item, `${path}[${index}]`)));
    return found;
  }
  if (typeof node === "object" && node !== null) {
    for (const key of Object.keys(node).sort()) {
      const child = (node as Record<string, unknown>)[key];
      found.push(...walkQualified(child, path ? `${path}.${key}` : key));
    }
  }
  return found;
}
