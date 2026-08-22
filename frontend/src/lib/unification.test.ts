import { describe, expect, it } from "vitest";

import { classifyBroker, classifySymbol, inRegion, regionEmptyCopy } from "@/lib/marketRegion";
import { weekdayInZone } from "@/lib/marketSessions";
import { formatInZone } from "@/lib/time";

describe("market region classification", () => {
  it("maps real symbols without inventing demo names", () => {
    expect(classifySymbol("NIFTY")).toBe("india");
    expect(classifySymbol("USTEC")).toBe("international");
    expect(classifySymbol("RELIANCE.NS")).toBe("india");
    expect(classifySymbol(null)).toBeNull();
    expect(inRegion("india", [{ symbol: "Mean Reversion FX" }])).toEqual([]);
    expect(regionEmptyCopy("india")).toBe("No India data available.");
    expect(regionEmptyCopy("international")).toBe("No international data available.");
  });

  it("maps known broker codes only", () => {
    expect(classifyBroker("zerodha")).toBe("india");
    expect(classifyBroker("mt5")).toBe("international");
    expect(classifyBroker("paper")).toBeNull();
  });
});

describe("calendar timezones", () => {
  it("formats New York without manual offsets", () => {
    const utc = "2026-08-17T12:00:00.000Z";
    expect(formatInZone(utc, "America/New_York")).toContain("08:00");
    expect(weekdayInZone(new Date("2026-08-17T12:00:00.000Z"), "Asia/Kolkata")).toBe(1);
  });
});
