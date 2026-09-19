import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/hooks", () => ({
  useMarketIntelStatus: () => ({ data: { configured: true } }),
  useMarketIntelIndices: () => ({ data: [{ value: "nifty50", label: "Nifty 50" }] }),
  useRegime: () => ({
    data: {
      label: "ranging_low",
      hmm_confidence: 0.82,
      hmm_vol_state: "low",
      gmm_vol_state: "low",
      adx_14: 18.3,
      avg_pairwise_corr: 0.21,
      breadth_pct_above_ma20: 0.44,
      days_since_changepoint: 12,
      as_of: "2026-07-16",
    },
    isLoading: false,
  }),
  useRankings: () => ({
    data: [
      {
        run_date: "2026-07-16",
        ticker: "SHREECEM",
        name: "Shree Cement",
        rank: 1,
        composite_score: 1.499,
        regime: "ranging_low",
        dimensions: [
          { name: "rs_60d", value: 0.15 },
          { name: "oi_score", value: -0.65 },
          { name: "if_score", value: null },
        ],
      },
    ],
    isLoading: false,
  }),
  useMarketIntelNews: () => ({
    data: [
      {
        ticker: "SHREECEM",
        title: "Cement demand climbs",
        source: "demo-wire",
        link: "http://example.invalid",
        published_raw: "2026-07-16",
        is_duplicate: false,
        sentiment_label: "positive",
        sentiment_score: 0.4,
      },
    ],
    isLoading: false,
  }),
  useOptionsSnapshot: () => ({ data: null }),
  useInstitutionalFlow: () => ({ data: null }),
}));

vi.mock("@/lib/markets", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/markets")>();
  const trend = (label: "Uptrend" | "Downtrend") => ({
    label,
    price: 23270,
    sma20: 23500,
    sma50: 24091,
    sma200: 24508,
    rsi14: 30,
    return_5d: -1.2,
    return_20d: -3.35,
    explanation: `${label} explanation`,
  });
  return {
    ...actual,
    useMarketPulse: () => ({
      isLoading: false,
      data: {
        session: { state: "closed", as_of: "", note: "" },
        universe: { source: "nse", trade_date: "2026-09-18" },
        indices: [],
        vix: { symbol: "^INDIAVIX", name: "INDIA VIX", price: 11.4, previous_close: 11, change_pct: 3.6, day_high: null, day_low: null, as_of: null },
        global: [],
        breadth: { advances: 145, declines: 60, unchanged: 5, ratio: 2.42, pct_advancing: 69, near_year_high: 7, near_year_low: 9 },
        sectors: [{ sector: "Logistics", change_pct: 3.27, members: 6, advancing: 5, leader: "INDIGO", laggard: "CONCOR" }],
        gainers: [],
        losers: [],
        near_year_high: [],
        regime: {
          nifty: trend("Downtrend"),
          bank_nifty: trend("Downtrend"),
          volatility: { label: "Calm", vix: 11.4, explanation: "Option premiums are cheap." },
        },
        institutional_flows: [
          { trade_date: "2026-09-18", fii_net: 599.54, dii_net: 1019.69, fii_buy: null, fii_sell: null, dii_buy: null, dii_sell: null },
        ],
      },
    }),
  };
});

import { MarketIntelPage } from "@/pages/MarketIntelPage";

describe("MarketIntelPage", () => {
  it("renders regime, ranked opportunities with a breakdown, and news", () => {
    render(<MarketIntelPage />, { wrapper: MemoryRouter });

    // Regime label and the advisory banner.
    expect(screen.getByText("ranging_low")).toBeInTheDocument();
    expect(screen.getByText(/Advisory/)).toBeInTheDocument();

    // Ranked opportunity + its dimension breakdown (selected by default).
    // The ticker appears in both the ranking row and the news badge.
    expect(screen.getAllByText("SHREECEM").length).toBeGreaterThan(0);
    expect(screen.getByText("Shree Cement")).toBeInTheDocument();
    expect(screen.getByText(/dimension breakdown/i)).toBeInTheDocument();
    expect(screen.getByText("Rel. strength (60d)")).toBeInTheDocument();

    // News feed.
    expect(screen.getByText("Cement demand climbs")).toBeInTheDocument();
  });

  it("leads with a live, explained market read from real data", () => {
    render(<MarketIntelPage />, { wrapper: MemoryRouter });

    // Downtrend (-2) + oversold (+0.5) + broad breadth (+1) + calm VIX (+0.5) + FII buying (+0.5)
    expect(screen.getByText("Neutral")).toBeInTheDocument();
    expect(screen.getByText("NIFTY in a downtrend")).toBeInTheDocument();
    expect(screen.getByText("Foreign investors buying")).toBeInTheDocument();
    expect(screen.getByText("NIFTY 50 trend")).toBeInTheDocument();
    // The synthetic-by-default model is labelled as such.
    expect(screen.getByText("Experimental")).toBeInTheDocument();
  });
});
