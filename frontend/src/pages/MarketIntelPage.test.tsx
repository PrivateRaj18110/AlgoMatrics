import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/hooks", () => ({
  useMarketIntelStatus: () => ({ data: { configured: true } }),
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

import { MarketIntelPage } from "@/pages/MarketIntelPage";

describe("MarketIntelPage", () => {
  it("renders regime, ranked opportunities with a breakdown, and news", () => {
    render(<MarketIntelPage />);

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
});
