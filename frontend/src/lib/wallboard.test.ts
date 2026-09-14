/**
 * Data-semantics tests.
 *
 * These are the load-bearing ones. Everything else on a wallboard is layout; if
 * these fail, the board is capable of lying, and a board that can lie is worse
 * than no board because people stop checking the thing it replaced.
 *
 * Each test names an equivalence that must NOT hold.
 */

import { describe, expect, it } from "vitest";

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
  readInstant,
  readNumber,
  readingText,
  rollUp,
  unknown,
  type QuerySnapshot,
} from "@/lib/wallboard";

const ok: QuerySnapshot = { isError: false, isSuccess: true, dataUpdatedAt: 1_700_000_000_000, hasData: true };
const failing: QuerySnapshot = { isError: true, isSuccess: false, dataUpdatedAt: 1_700_000_000_000, hasData: true };
const never: QuerySnapshot = { isError: false, isSuccess: false, dataUpdatedAt: 0, hasData: false };

describe("UNKNOWN is not zero", () => {
  it("renders a missing number as UNKNOWN, never 0", () => {
    const reading = readNumber(null);
    expect(reading.state).toBe("UNKNOWN");
    expect(reading.value).toBeNull();
    expect(readingText(reading)).toBe("UNKNOWN");
    expect(readingText(reading)).not.toBe("0");
  });

  it("keeps a real zero distinguishable from a missing value", () => {
    const measuredZero = readNumber(0);
    expect(measuredZero.state).toBe("HEALTHY");
    expect(measuredZero.value).toBe(0);
    expect(readingText(measuredZero)).toBe("0");
  });

  it("treats NaN and empty string as unknown rather than zero", () => {
    expect(readNumber(Number.NaN).state).toBe("UNKNOWN");
    expect(readNumber("").state).toBe("UNKNOWN");
    expect(readNumber(undefined).state).toBe("UNKNOWN");
  });

  it("an unavailable error count is UNKNOWN, not 0", () => {
    const unavailable = readEstablishedCount(0, false, "error telemetry is not collected");
    expect(unavailable.state).toBe("UNKNOWN");
    expect(readingText(unavailable)).toBe("UNKNOWN");
  });

  it("a missing feed count is UNKNOWN, not 0", () => {
    expect(readEstablishedCount(undefined, true).state).toBe("UNKNOWN");
    expect(readEstablishedCount(null, true).state).toBe("UNKNOWN");
  });
});

describe("UNKNOWN is not HEALTHY", () => {
  it("never rolls up to HEALTHY while any component is unknown", () => {
    expect(rollUp(["HEALTHY", "HEALTHY", "UNKNOWN"])).toBe("UNKNOWN");
    expect(rollUp(["HEALTHY", "HEALTHY"])).toBe("HEALTHY");
  });

  it("treats an empty component set as UNKNOWN rather than HEALTHY", () => {
    expect(rollUp([])).toBe("UNKNOWN");
  });

  it("does not escalate a missing metric to CRITICAL", () => {
    // "A missing metric is NOT unhealthy unless an authoritative rule says so."
    expect(rollUp(["UNKNOWN", "UNKNOWN"])).toBe("UNKNOWN");
    expect(rollUp(["UNKNOWN"])).not.toBe("CRITICAL");
    expect(rollUp(["UNKNOWN"])).not.toBe("DEGRADED");
  });

  it("lets real failure outrank absence", () => {
    expect(rollUp(["UNKNOWN", "CRITICAL"])).toBe("CRITICAL");
    expect(rollUp(["UNKNOWN", "DEGRADED"])).toBe("DEGRADED");
    expect(rollUp(["UNKNOWN", "STALE"])).toBe("STALE");
  });
});

describe("STALE is not LIVE, and STALE is not CRITICAL", () => {
  it("keeps the last known value but re-labels it STALE when the query is failing", () => {
    const fresh = known("HEALTHY", "REACHABLE");
    const stale = markStaleOnError(fresh, failing);
    expect(stale.state).toBe("STALE");
    expect(stale.value).toBe("REACHABLE");
    expect(stale.detail).toMatch(/last known/i);
  });

  it("does not promote an unknown reading to STALE — there is nothing to be stale about", () => {
    const missing = unknown<string>("never reported");
    expect(markStaleOnError(missing, failing).state).toBe("UNKNOWN");
    expect(markStaleOnError(missing, failing).value).toBeNull();
  });

  it("leaves a healthy reading alone while the query is succeeding", () => {
    const fresh = known("HEALTHY", 12);
    expect(markStaleOnError(fresh, ok)).toEqual(fresh);
  });

  it("ranks STALE below DEGRADED and CRITICAL", () => {
    expect(rollUp(["STALE", "DEGRADED"])).toBe("DEGRADED");
    expect(rollUp(["STALE", "CRITICAL"])).toBe("CRITICAL");
    expect(rollUp(["STALE", "HEALTHY"])).toBe("STALE");
  });
});

describe("a missing timestamp is not the current time", () => {
  it("returns UNKNOWN rather than now", () => {
    expect(readInstant(null).state).toBe("UNKNOWN");
    expect(readInstant(undefined).value).toBeNull();
    expect(clockLabel(null)).toBe("UNKNOWN");
    expect(dateTimeLabel(undefined)).toBe("UNKNOWN");
  });

  it("rejects an unparseable timestamp instead of coercing it", () => {
    expect(readInstant("not a date").state).toBe("UNKNOWN");
    expect(clockLabel("not a date")).toBe("UNKNOWN");
  });

  it("takes the latest of several instants and ignores the absent ones", () => {
    const latest = latestInstant([null, "2026-09-13T10:00:00Z", undefined, "2026-09-13T12:30:00Z"]);
    expect(latest.state).toBe("HEALTHY");
    expect(latest.value).toBe("2026-09-13T12:30:00Z");
  });

  it("returns UNKNOWN when every instant is absent", () => {
    expect(latestInstant([null, undefined, ""]).state).toBe("UNKNOWN");
  });
});

describe("an API default is not a measurement", () => {
  it("ignores api_success_pct=100 when the nullable twin is absent", () => {
    // This is the exact shape the ops API returns for an agent that reported
    // nothing: the defaulted field says 100%, the honest twin says null.
    const reading = preferNullable(null, 100, "agent reported no success rate");
    expect(reading.state).toBe("UNKNOWN");
    expect(reading.value).toBeNull();
    expect(readingText(reading)).toBe("UNKNOWN");
    expect(readingText(reading)).not.toContain("100");
  });

  it("uses the nullable twin when it is present, including a genuine zero", () => {
    expect(preferNullable(0.94, 94).value).toBeCloseTo(0.94);
    expect(preferNullable(0, 100).state).toBe("HEALTHY");
    expect(preferNullable(0, 100).value).toBe(0);
  });
});

describe("connection state and last successful update", () => {
  it("reports DEGRADED when any query is failing", () => {
    expect(connectionState([ok, failing])).toBe("DEGRADED");
  });

  it("reports UNKNOWN before anything has completed, not CONNECTED", () => {
    expect(connectionState([never])).toBe("UNKNOWN");
    expect(connectionState([])).toBe("UNKNOWN");
  });

  it("reports CONNECTED only once a query has actually succeeded", () => {
    expect(connectionState([ok, never])).toBe("CONNECTED");
  });

  it("reports UNKNOWN for last update when nothing has ever succeeded", () => {
    expect(lastSuccessfulUpdate([never]).state).toBe("UNKNOWN");
  });

  it("reports the most recent successful fetch, keeping it after a later failure", () => {
    const update = lastSuccessfulUpdate([failing, { ...ok, dataUpdatedAt: 1_700_000_500_000 }]);
    expect(update.state).toBe("HEALTHY");
    expect(update.value).toBe(new Date(1_700_000_500_000).toISOString());
  });
});
