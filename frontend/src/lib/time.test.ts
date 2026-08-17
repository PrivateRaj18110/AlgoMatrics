import { describe, expect, it } from "vitest";

import { formatInZone, formatTradingTime, formatUtcTime } from "@/lib/time";

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
});
