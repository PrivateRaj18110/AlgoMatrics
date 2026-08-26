import { describe, expect, it } from "vitest";

import { formatHealthAge, formatInZone, formatTradingTime, formatUtcTime, INFRA_ZONE, TRADING_ZONE } from "@/lib/time";

describe("time display", () => {
  it("converts noon UTC to 17:30 IST without manual offset math", () => {
    const utc = "2026-08-17T12:00:00.000Z";
    expect(formatUtcTime(utc)).toContain("12:00");
    expect(formatTradingTime(utc)).toContain("17:30");
    expect(formatInZone(utc, "Asia/Kolkata")).toContain("17:30");
  });

  it("renders missing timestamps as unknown", () => {
    expect(formatTradingTime(null)).toBe("—");
    expect(formatUtcTime(undefined)).toBe("—");
  });

  it("keeps UTC midnight as 05:30 IST the same calendar day", () => {
    const utc = "2026-08-17T00:00:00.000Z";
    expect(formatUtcTime(utc)).toContain("00:00");
    expect(formatTradingTime(utc)).toContain("05:30");
    expect(formatInZone(utc, "UTC")).toContain("17");
    expect(formatInZone(utc, "Asia/Kolkata")).toContain("17");
  });

  it("crosses the IST date boundary at 18:30 UTC", () => {
    const before = "2026-08-17T18:29:00.000Z";
    const after = "2026-08-17T18:30:00.000Z";
    expect(formatInZone(before, "Asia/Kolkata")).toContain("17");
    expect(formatInZone(after, "Asia/Kolkata")).toContain("18");
  });

  it("uses IANA conversion rather than a hardcoded 5:30 string", () => {
    expect(TRADING_ZONE).toBe("Asia/Kolkata");
    expect(INFRA_ZONE).toBe("UTC");
    const src = formatInZone.toString();
    expect(src).not.toContain("5:30");
  });

  it("formats relative health age correctly", () => {
    const base = new Date("2026-08-24T12:00:00.000Z").getTime();
    expect(formatHealthAge(new Date(base - 12000), base)).toBe("12 seconds ago");
    expect(formatHealthAge(new Date(base - 135000), base)).toBe("2m 15s ago");
    expect(formatHealthAge(new Date(base - 300000), base)).toBe("5m ago");
    expect(formatHealthAge(new Date(base - 8100000), base)).toBe("2h 15m");
    expect(formatHealthAge(null, base)).toBe("No data");
    expect(formatHealthAge(undefined, base)).toBe("No data");
  });
});
