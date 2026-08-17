import { describe, expect, it } from "vitest";

import { formatInZone, formatTradingTime, formatUtcTime, INFRA_ZONE, TRADING_ZONE } from "@/lib/time";

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
    expect(src).not.toMatch(/\+330|330 \*/);
  });
});
