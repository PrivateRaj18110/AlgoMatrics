import { describe, expect, it } from "vitest";

import {
  environmentMeaning,
  formatInstant,
  isLiveMarket,
  isQualified,
  isRecognisedStatus,
  readFreshness,
  readStatus,
  statusLabel,
  walkQualified,
} from "./monitoring";

describe("qualified values", () => {
  it("recognises the producer's shape", () => {
    expect(isQualified({ status: "UNKNOWN", value: null, reason: "x" })).toBe(true);
    expect(isQualified({ status: "OBSERVED", value: 1 })).toBe(true);
  });

  it("rejects bare scalars and arrays", () => {
    expect(isQualified(42)).toBe(false);
    expect(isQualified("OBSERVED")).toBe(false);
    expect(isQualified(null)).toBe(false);
    expect(isQualified([{ status: "UNKNOWN" }])).toBe(false);
  });

  it("labels N/A and SYNTHETIC_CLOCK readably without losing the distinction", () => {
    expect(statusLabel("NOT_APPLICABLE")).toBe("N/A");
    expect(statusLabel("SYNTHETIC_CLOCK")).toBe("SYNTHETIC CLOCK");
    expect(statusLabel("UNKNOWN")).toBe("UNKNOWN");
  });

  it("flags an unfamiliar status instead of assuming it is healthy", () => {
    expect(isRecognisedStatus("UNKNOWN")).toBe(true);
    expect(isRecognisedStatus("SOMETHING_NEW")).toBe(false);
  });

  it("finds every qualified value in a nested payload", () => {
    const payload = {
      execution: { independent_broker_state: { status: "UNKNOWN", value: null } },
      feed: { message_rate: { status: "OBSERVED", value: 21 } },
    };
    expect(walkQualified(payload).sort()).toEqual(
      [
        ["execution.independent_broker_state", "UNKNOWN"],
        ["feed.message_rate", "OBSERVED"],
      ].sort(),
    );
  });
});

describe("freshness", () => {
  it("reads the source's assertion without computing anything", () => {
    const read = readFreshness({
      source: "STALE",
      derived_at: "2026-09-11T09:01:34.627414+00:00",
      reason: "fixture_preserves_stale_without_live_upgrade",
    });
    expect(read.source).toBe("STALE");
    expect(read.derivedAt).toBe("2026-09-11T09:01:34.627414+00:00");
    expect(read.recognised).toBe(true);
  });

  it("reports a missing assertion rather than inventing one", () => {
    const read = readFreshness({});
    expect(read.source).toBeNull();
    expect(read.recognised).toBe(false);
  });

  it("preserves an unrecognised state rather than downgrading it", () => {
    const read = readFreshness({ source: "SOMETHING_NEW" });
    expect(read.source).toBe("SOMETHING_NEW");
    expect(read.recognised).toBe(false);
  });

  it("exports no horizon evaluator", async () => {
    // monitoring.v1 has no stale_after. A reintroduced evaluator fails here.
    const module = await import("./monitoring");
    expect("evaluateFreshness" in module).toBe(false);
  });
});

describe("environment and trust", () => {
  it("treats only live_trading as live market reality", () => {
    expect(isLiveMarket("live_trading")).toBe(true);
    expect(isLiveMarket("offline_fixture")).toBe(false);
    expect(isLiveMarket("replay")).toBe(false);
    expect(isLiveMarket("live_market_paper")).toBe(false);
  });

  it("explains an unfamiliar environment without calling it live", () => {
    expect(environmentMeaning("some_new_mode")).toMatch(/does not recognise/);
  });

  it("reads a status without upgrading it", () => {
    expect(readStatus({ status: "UNTRUSTED" })).toBe("UNTRUSTED");
    expect(readStatus({})).toBeNull();
    expect(readStatus(null)).toBeNull();
  });
});

describe("instant formatting", () => {
  it("says NOT REPORTED rather than showing a dash", () => {
    expect(formatInstant(null)).toBe("NOT REPORTED");
    expect(formatInstant(undefined)).toBe("NOT REPORTED");
    expect(formatInstant("")).toBe("NOT REPORTED");
    expect(formatInstant("garbage")).toBe("NOT REPORTED");
  });

  it("formats a real instant in UTC", () => {
    expect(formatInstant("2026-09-11T09:01:34Z")).toBe("2026-09-11 09:01:34Z");
  });
});
