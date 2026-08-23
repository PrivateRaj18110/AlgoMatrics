import { describe, expect, it } from "vitest";

import { classifyBroker, classifySymbol, inRegion, regionEmptyCopy } from "@/lib/marketRegion";
import { weekdayInZone } from "@/lib/marketSessions";
import { formatInZone } from "@/lib/time";

describe("market region classification", () => {
  it("maps real symbols without inventing demo names", () => {
    expect(classifySymbol("NIFTY")).toBe("india");
    expect(classifySymbol("NIFTY 24500 CE")).toBe("india");
    expect(classifySymbol("BANKNIFTY24AUGFUT")).toBe("india");
    expect(classifySymbol("RELIANCE")).toBe("india");
    expect(classifySymbol("RELIANCE.NS")).toBe("india");
    expect(classifySymbol("USTEC")).toBe("international");
    expect(classifySymbol("EURUSD")).toBe("international");
    expect(classifySymbol("XAUUSD")).toBe("international");
    expect(classifySymbol("BTCUSDT")).toBe("international");
    expect(classifySymbol(null)).toBeNull();
    expect(regionEmptyCopy("india")).toBe("No India data available.");
    expect(regionEmptyCopy("international")).toBe("No international data available.");
  });

  it("maps known broker codes only", () => {
    expect(classifyBroker("zerodha")).toBe("india");
    expect(classifyBroker("angelone")).toBe("india");
    expect(classifyBroker("mt5")).toBe("international");
    expect(classifyBroker("binance")).toBe("international");
    expect(classifyBroker("paper")).toBeNull();
  });

  it("classifies telemetry rows into India vs International", () => {
    // Real India trades
    const indiaTrades = [
      { id: "t1", symbol: "NIFTY 24500 CE", broker: "zerodha", machine: "gcp-trading-1" },
      { id: "t2", symbol: "RELIANCE", broker: "angelone", machine: "mch-agent-gcp-2" },
      { id: "t3", symbol: "BANKNIFTY", machine: "google-vm" },
    ];
    expect(inRegion("india", indiaTrades)).toHaveLength(3);
    expect(inRegion("international", indiaTrades)).toHaveLength(0);

    // International trades
    const intlTrades = [
      { id: "t4", symbol: "EURUSD", broker: "mt5", machine: "london-vps" },
      { id: "t5", symbol: "XAUUSD", broker: "binance" },
    ];
    expect(inRegion("international", intlTrades)).toHaveLength(2);
    expect(inRegion("india", intlTrades)).toHaveLength(0);
  });
});

describe("calendar timezones", () => {
  it("formats New York without manual offsets", () => {
    const utc = "2026-08-17T12:00:00.000Z";
    expect(formatInZone(utc, "America/New_York")).toContain("08:00");
    expect(weekdayInZone(new Date("2026-08-17T12:00:00.000Z"), "Asia/Kolkata")).toBe(1);
  });
});
