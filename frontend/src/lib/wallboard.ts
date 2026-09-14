/**
 * The operational state model shared by the heat map and the health wallboard.
 *
 * One rule drives everything in this file: **absence is not zero, and absence is
 * not health.** A wallboard that shows `0 errors` when error telemetry was never
 * collected is worse than a blank screen, because a blank screen does not get
 * trusted. Every reader here therefore returns an explicit UNKNOWN rather than a
 * plausible-looking number.
 *
 * This matters concretely against the ops API. `SystemHealthPoint` declares
 * non-optional fields with defaults — `api_success_pct: float = 100.0`,
 * `status: str = "STABLE"`, `queue_size: int = 0` — so a metric the agent never
 * reported arrives as a confident 100%. Several of those fields have nullable
 * twins (`api_success_rate`, `cpu_usage`, `signal_fill_rate`) which are the
 * honest ones. `preferNullable` exists for exactly that pairing.
 */

/**
 * Explicit operational states.
 *
 * Deliberately not a boolean. `STALE` is not `CRITICAL` (a feed that stopped
 * updating is not a feed that vanished), and `UNKNOWN` is not `DEGRADED` (not
 * being able to measure something is not evidence that it is broken).
 */
export type OperationalState = "HEALTHY" | "DEGRADED" | "STALE" | "CRITICAL" | "UNKNOWN";

/** Roll-up precedence. UNKNOWN outranks HEALTHY: see {@link rollUp}. */
const PRECEDENCE: Record<OperationalState, number> = {
  CRITICAL: 5,
  DEGRADED: 4,
  STALE: 3,
  UNKNOWN: 2,
  HEALTHY: 1,
};

/**
 * A single displayable fact, and whether we actually know it.
 *
 * `value === null` whenever `state === "UNKNOWN"`; that invariant is what lets
 * the render layer print the word UNKNOWN without re-deciding the question.
 */
export interface Reading<T> {
  state: OperationalState;
  value: T | null;
  /** Short, human reason. Shown next to the state so a viewer is never guessing. */
  detail: string | null;
}

export function unknown<T>(detail: string): Reading<T> {
  return { state: "UNKNOWN", value: null, detail };
}

export function known<T>(state: Exclude<OperationalState, "UNKNOWN">, value: T, detail: string | null = null): Reading<T> {
  return { state, value, detail };
}

/**
 * Combine component states into one overall state.
 *
 * The ordering is the point. A missing metric never escalates to CRITICAL —
 * "A missing metric is NOT unhealthy" — but it does prevent the board claiming
 * HEALTHY, because HEALTHY is an assertion about the whole system and we cannot
 * make it on partial information. An empty list is UNKNOWN, never HEALTHY.
 */
export function rollUp(states: readonly OperationalState[]): OperationalState {
  if (states.length === 0) return "UNKNOWN";
  return states.reduce<OperationalState>(
    (worst, current) => (PRECEDENCE[current] > PRECEDENCE[worst] ? current : worst),
    "HEALTHY",
  );
}

/**
 * Read a number that the API may have defaulted.
 *
 * `nullable` is believed; `defaulted` is never used as a fallback, only as a
 * cross-check. When the nullable twin is absent the answer is UNKNOWN even
 * though `defaulted` holds a perfectly renderable number — that number is a
 * Pydantic default, not a measurement.
 */
export function preferNullable(
  nullable: number | null | undefined,
  _defaulted?: number | null,
  detail = "not reported by the source",
): Reading<number> {
  if (nullable === null || nullable === undefined || !Number.isFinite(nullable)) {
    return unknown(detail);
  }
  return known("HEALTHY", nullable);
}

/** A plain nullable number, with no defaulted twin to guard against. */
export function readNumber(
  value: number | string | null | undefined,
  detail = "not reported",
): Reading<number> {
  if (value === null || value === undefined || value === "") return unknown(detail);
  const amount = typeof value === "string" ? Number.parseFloat(value) : value;
  if (!Number.isFinite(amount)) return unknown(detail);
  return known("HEALTHY", amount);
}

/** A nullable ISO instant. Missing timestamps never become "now". */
export function readInstant(
  value: string | null | undefined,
  detail = "no timestamp reported",
): Reading<string> {
  if (!value || typeof value !== "string") return unknown(detail);
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return unknown("timestamp not parseable");
  return known("HEALTHY", value);
}

/**
 * A count that is only assertable when the source was actually reachable.
 *
 * `established` is the caller's proof that the question was answered — a
 * successful query against a configured store. Without it, an empty result is
 * indistinguishable from an unasked question, so the answer is UNKNOWN.
 *
 * This is what keeps "NO ACTIVE INCIDENTS" off the screen when the incident
 * store simply failed to answer.
 */
export function readEstablishedCount(
  count: number | null | undefined,
  established: boolean,
  detail = "source did not answer",
): Reading<number> {
  if (!established) return unknown(detail);
  if (count === null || count === undefined || !Number.isFinite(count)) return unknown(detail);
  return known("HEALTHY", count);
}

/** The largest of a set of instants, ignoring the ones we do not have. */
export function latestInstant(values: readonly (string | null | undefined)[]): Reading<string> {
  let best: { iso: string; at: number } | null = null;
  for (const value of values) {
    if (!value) continue;
    const at = Date.parse(value);
    if (Number.isNaN(at)) continue;
    if (best === null || at > best.at) best = { iso: value, at };
  }
  if (best === null) return unknown("no timestamp reported");
  return known("HEALTHY", best.iso);
}

/**
 * The state of our own connection to the API.
 *
 * Deliberately narrow: this describes *this browser's* ability to reach the API
 * and nothing else. It is never promoted into a statement about the database,
 * the feeds or the receiver — inferring those from an HTTP 200 is the single
 * most common way an operations board comes to lie.
 */
export type ConnectionState = "CONNECTED" | "DEGRADED" | "UNKNOWN";

export interface QuerySnapshot {
  isError: boolean;
  isSuccess: boolean;
  /** Epoch ms of the last successful fetch; 0 when there has never been one. */
  dataUpdatedAt: number;
  hasData: boolean;
}

export function connectionState(queries: readonly QuerySnapshot[]): ConnectionState {
  if (queries.length === 0) return "UNKNOWN";
  if (queries.some((query) => query.isError)) return "DEGRADED";
  if (queries.some((query) => query.isSuccess)) return "CONNECTED";
  return "UNKNOWN";
}

/** Most recent successful fetch across a set of queries, as an ISO instant. */
export function lastSuccessfulUpdate(queries: readonly QuerySnapshot[]): Reading<string> {
  const times = queries.map((query) => query.dataUpdatedAt).filter((at) => at > 0);
  if (times.length === 0) return unknown("no successful update yet");
  return known("HEALTHY", new Date(Math.max(...times)).toISOString());
}

/**
 * Demote a reading when its query is currently failing.
 *
 * The value is kept — losing the last known state on a transient blip makes a
 * wallboard useless — but it is re-labelled STALE so nobody reads it as current.
 * A reading we never had stays UNKNOWN rather than becoming STALE, because
 * there is nothing to be stale about.
 */
export function markStaleOnError<T>(reading: Reading<T>, query: QuerySnapshot): Reading<T> {
  if (!query.isError) return reading;
  if (reading.state === "UNKNOWN") return reading;
  return {
    state: "STALE",
    value: reading.value,
    detail: reading.detail ? `${reading.detail} — last known` : "last known value, not current",
  };
}

/** Render helper: the text a viewer sees for a reading, never a bare zero. */
export function readingText(
  reading: Reading<number>,
  format: (value: number) => string = (value) => String(value),
): string {
  if (reading.state === "UNKNOWN" || reading.value === null) return "UNKNOWN";
  return format(reading.value);
}

/**
 * Short clock label for an ISO instant, in the viewer's zone.
 *
 * Returns UNKNOWN rather than the epoch or the current time when the instant is
 * missing, which is the whole reason this is not `new Date(x).toLocaleTimeString()`
 * at each call site.
 */
export function clockLabel(value: string | null | undefined): string {
  if (!value) return "UNKNOWN";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return "UNKNOWN";
  return new Date(parsed).toLocaleTimeString(undefined, { hour12: false });
}

export function dateTimeLabel(value: string | null | undefined): string {
  if (!value) return "UNKNOWN";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return "UNKNOWN";
  return new Date(parsed).toLocaleString(undefined, { hour12: false });
}
