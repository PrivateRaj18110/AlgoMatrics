import { describe, expect, it } from "vitest";

import { marketRead } from "@/lib/marketRead";
import type { MarketPulse, TrendRegime } from "@/lib/markets";

function regime(label: TrendRegime["label"], rsi14: number | null = 50): TrendRegime {
  return {
    label,
    price: 100,
    sma20: 99,
    sma50: 98,
    sma200: 95,
    rsi14,
    return_5d: 1,
    return_20d: 2,
    explanation: `${label} explanation`,
  };
}

function pulse(over: Partial<MarketPulse> = {}): MarketPulse {
  return {
    session: { state: "open", as_of: "", note: "" },
    universe: { source: "nse", trade_date: "2026-09-18" },
    indices: [],
    vix: { symbol: "^INDIAVIX", name: "INDIA VIX", price: 14, previous_close: 14, change_pct: 0, day_high: null, day_low: null, as_of: null },
    global: [],
    breadth: { advances: 100, declines: 100, unchanged: 10, ratio: 1, pct_advancing: 50, near_year_high: 0, near_year_low: 0 },
    sectors: [
      { sector: "Banks", change_pct: 1.2, members: 19, advancing: 15, leader: "SBIN", laggard: "PNB" },
      { sector: "IT", change_pct: -0.8, members: 13, advancing: 3, leader: "TCS", laggard: "INFY" },
      { sector: "Auto", change_pct: 0.3, members: 17, advancing: 9, leader: "M&M", laggard: "TMPV" },
      { sector: "Realty", change_pct: -1.5, members: 6, advancing: 1, leader: "DLF", laggard: "LODHA" },
    ],
    gainers: [],
    losers: [],
    near_year_high: [],
    regime: {
      nifty: regime("Range-bound"),
      bank_nifty: regime("Range-bound"),
      volatility: { label: "Normal", vix: 15, explanation: "normal" },
    },
    institutional_flows: [],
    ...over,
  };
}

describe("marketRead", () => {
  it("is neutral when nothing stands out", () => {
    const read = marketRead(pulse());
    expect(read.stance).toBe("Neutral");
    expect(read.score).toBe(0);
  });

  it("goes risk-on on an uptrend with broad participation, and says why", () => {
    const read = marketRead(
      pulse({
        breadth: { advances: 150, declines: 50, unchanged: 10, ratio: 3, pct_advancing: 71, near_year_high: 9, near_year_low: 1 },
        regime: { nifty: regime("Uptrend"), bank_nifty: regime("Uptrend"), volatility: { label: "Normal", vix: 15, explanation: "" } },
      }),
    );
    expect(read.stance).toBe("Risk-on");
    expect(read.factors.map((f) => f.label)).toEqual(["NIFTY in an uptrend", "Broad participation"]);
  });

  it("goes risk-off on a downtrend with stressed volatility and FII selling", () => {
    const read = marketRead(
      pulse({
        regime: { nifty: regime("Downtrend"), bank_nifty: regime("Downtrend"), volatility: { label: "Stressed", vix: 28, explanation: "fear" } },
        institutional_flows: [
          { trade_date: "2026-09-18", fii_net: -2500, dii_net: 1800, fii_buy: null, fii_sell: null, dii_buy: null, dii_sell: null },
        ],
      }),
    );
    expect(read.stance).toBe("Risk-off");
    expect(read.score).toBe(-5);
    expect(read.factors.find((f) => f.label === "Foreign investors selling")?.weight).toBe(-1);
  });

  it("flags stretched RSI in both directions", () => {
    expect(marketRead(pulse({ regime: { ...pulse().regime, nifty: regime("Range-bound", 75) } })).factors[1].label).toBe(
      "NIFTY overbought",
    );
    expect(marketRead(pulse({ regime: { ...pulse().regime, nifty: regime("Range-bound", 25) } })).factors[1].label).toBe(
      "NIFTY oversold",
    );
  });

  it("ranks sector leaders and laggards", () => {
    const read = marketRead(pulse());
    expect(read.leaders).toEqual(["Banks", "Auto", "IT"]);
    expect(read.laggards).toEqual(["Realty", "IT", "Auto"]);
  });
});
