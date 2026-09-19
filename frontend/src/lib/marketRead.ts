// A transparent "market read": a stance built from a handful of well-known
// signals, where every point that moved the score is listed. Deliberately
// simple and rule-based so a reader can check it — not a model, not advice.

import type { MarketPulse } from "@/lib/markets";

export type Stance = "Risk-on" | "Neutral" | "Risk-off";

export interface ReadFactor {
  label: string;
  detail: string;
  weight: number; // signed contribution to the score
}

export interface MarketRead {
  stance: Stance;
  score: number;
  factors: ReadFactor[];
  leaders: string[];
  laggards: string[];
}

const LARGE_FLOW_CRORE = 1000;

export function marketRead(pulse: MarketPulse): MarketRead {
  const factors: ReadFactor[] = [];
  const { nifty, volatility } = pulse.regime;

  if (nifty.label === "Uptrend") {
    factors.push({ label: "NIFTY in an uptrend", detail: nifty.explanation, weight: 2 });
  } else if (nifty.label === "Downtrend") {
    factors.push({ label: "NIFTY in a downtrend", detail: nifty.explanation, weight: -2 });
  } else if (nifty.label === "Range-bound") {
    factors.push({ label: "NIFTY range-bound", detail: nifty.explanation, weight: 0 });
  }

  if (nifty.rsi14 !== null) {
    if (nifty.rsi14 >= 70) {
      factors.push({
        label: "NIFTY overbought",
        detail: `RSI(14) ${nifty.rsi14}: extended, pullbacks more likely`,
        weight: -0.5,
      });
    } else if (nifty.rsi14 <= 30) {
      factors.push({
        label: "NIFTY oversold",
        detail: `RSI(14) ${nifty.rsi14}: stretched to the downside, bounces more likely`,
        weight: 0.5,
      });
    }
  }

  const participation = pulse.breadth.pct_advancing;
  if (participation !== null) {
    if (participation >= 60) {
      factors.push({
        label: "Broad participation",
        detail: `${participation}% of F&O stocks are up today`,
        weight: 1,
      });
    } else if (participation <= 40) {
      factors.push({
        label: "Weak breadth",
        detail: `Only ${participation}% of F&O stocks are up today`,
        weight: -1,
      });
    }
  }

  if (volatility.label === "Elevated") {
    factors.push({ label: "Volatility elevated", detail: volatility.explanation, weight: -1 });
  } else if (volatility.label === "Stressed") {
    factors.push({ label: "Volatility stressed", detail: volatility.explanation, weight: -2 });
  } else if (volatility.label === "Calm") {
    factors.push({ label: "Volatility calm", detail: volatility.explanation, weight: 0.5 });
  }

  const flow = pulse.institutional_flows[0];
  if (flow && flow.fii_net !== null) {
    const size = Math.abs(flow.fii_net) >= LARGE_FLOW_CRORE ? 1 : 0.5;
    factors.push({
      label: flow.fii_net >= 0 ? "Foreign investors buying" : "Foreign investors selling",
      detail: `FII net ₹${Math.round(flow.fii_net).toLocaleString("en-IN")} cr on ${flow.trade_date}`,
      weight: flow.fii_net >= 0 ? size : -size,
    });
  }

  const score = factors.reduce((sum, factor) => sum + factor.weight, 0);
  const stance: Stance = score >= 2 ? "Risk-on" : score <= -2 ? "Risk-off" : "Neutral";
  const ranked = [...pulse.sectors].sort((a, b) => b.change_pct - a.change_pct);
  return {
    stance,
    score,
    factors,
    leaders: ranked.slice(0, 3).map((sector) => sector.sector),
    laggards: ranked.slice(-3).reverse().map((sector) => sector.sector),
  };
}
