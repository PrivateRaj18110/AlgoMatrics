import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Catalysts, ForecastStock, MarketNews, Movers, TrackRecord } from "@/lib/movers";

const legacy = vi.hoisted(() => ({ configured: false }));

vi.mock("@/lib/hooks", () => ({
  useMarketIntelStatus: () => ({ data: { configured: legacy.configured } }),
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
        dimensions: [{ name: "rs_60d", value: 0.15 }],
      },
    ],
    isLoading: false,
  }),
  useMarketIntelNews: () => ({ data: [], isLoading: false }),
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

const movers = vi.hoisted(() => ({
  useMovers: vi.fn(),
  useMoversTrackRecord: vi.fn(),
  useCatalysts: vi.fn(),
  useMarketNews: vi.fn(),
  useRunMoversJob: vi.fn(),
  useBriefingArchive: vi.fn(),
  useBriefingAction: vi.fn(),
}));
vi.mock("@/lib/movers", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/movers")>()),
  ...movers,
}));

import { MarketIntelPage } from "@/pages/MarketIntelPage";
import { useAuth } from "@/stores/auth";

function stock(symbol: string, over: Partial<ForecastStock> = {}): ForecastStock {
  return {
    symbol,
    sector: "Banks",
    rank: 1,
    probability: 0.34,
    direction: "down",
    direction_basis: "pre-open gap backed by the order book",
    direction_confidence: "high",
    gap_pct: -1.6,
    imbalance: -0.52,
    typical_move_pct: 0.8,
    threshold_pct: 3,
    prev_change_pct: 4.5,
    last_close: 100,
    news_count: 3,
    oi_change_pct: null,
    reasons: [{ feature: "gap_z", text: "Pre-open gap -1.6% — 1.9x its usual day", weight: 1.2 }],
    catalysts: [
      {
        id: "nse:1",
        symbol,
        source: "nse_filing",
        category: "results",
        label: "Financial results",
        impact: 0.9,
        direction: 0,
        title: "Unaudited results",
        at: "2026-09-17T18:30:00+05:30",
        url: "https://nsearchives.nseindia.com/corporate/x.pdf",
        company: `${symbol} Ltd`,
      },
    ],
    flags: { results: true, ban: false, ex_adjustment: false },
    ...over,
  };
}

function forecast(overrides: Partial<Extract<Movers, { available: true }>> = {}): Movers {
  return {
    available: true,
    trade_date: "2026-09-18",
    stage: "opening",
    stale: false,
    overnight_available: true,
    intraday: [],
    model: { source: "fitted", version: "v", fitted_at: null, days: 60 },
    dates: ["2026-09-18", "2026-09-17"],
    disclaimer: "Not investment advice.",
    outcome: null,
    forecast: {
      stage: "opening",
      trade_date: "2026-09-18",
      generated_at: "2026-09-18T09:09:30+05:30",
      model: { source: "fitted", version: "v", fitted_at: null, days: 60 },
      universe: 2,
      expected_majors: 0.6,
      threshold_rule: "max(3%, 2x the stock's typical daily move)",
      stocks: [stock("TMPV"), stock("PAYTM", { rank: 2, probability: 0.3, direction: "up", gap_pct: 1.8, catalysts: [], flags: { results: false, ban: false, ex_adjustment: false } })],
    },
    ...overrides,
  };
}

function grade(over: Record<string, unknown> = {}) {
  return {
    top_k: 10,
    hits: 2,
    majors: 44,
    universe: 210,
    precision: 0.2,
    base_rate: 0.2095,
    recall: 0.045,
    lift: 0.95,
    direction_calls: 2,
    direction_right: 2,
    brier: 0.17,
    hit_symbols: ["TMPV"],
    missed_symbols: ["RVNL"],
    ...over,
  };
}

const view = (path = "/app/market-intelligence") =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <MarketIntelPage />
    </MemoryRouter>,
  );

beforeEach(() => {
  legacy.configured = false;
  movers.useMovers.mockReturnValue({ data: forecast(), isLoading: false, isError: false });
  movers.useRunMoversJob.mockReturnValue({ mutate: vi.fn(), isPending: false });
  movers.useCatalysts.mockReturnValue({ data: undefined, isLoading: true });
  movers.useMarketNews.mockReturnValue({ data: undefined, isLoading: true });
  movers.useMoversTrackRecord.mockReturnValue({ data: undefined, isLoading: true });
  movers.useBriefingAction.mockReturnValue({ mutate: vi.fn(), isPending: false, isSuccess: false });
  useAuth.setState({ user: null });
});

describe("MarketIntelPage · AI-CIO", () => {
  it("opens on today's movers with reasons, direction and the filing behind each pick", () => {
    view();
    expect(screen.getByRole("tab", { name: "Today's movers" })).toHaveAttribute("aria-selected", "true");
    const card = screen.getByRole("article", { name: "TMPV forecast" });
    expect(within(card).getByText("Likely down")).toBeInTheDocument();
    expect(within(card).getByText(/Pre-open gap -1.6%/)).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: /Financial results/ })).toHaveAttribute(
      "href",
      "https://nsearchives.nseindia.com/corporate/x.pdf",
    );
    expect(screen.getByText(/Advisory/)).toBeInTheDocument();
    expect(screen.getByText("Not investment advice.")).toBeInTheDocument();
  });

  it("says plainly when the day graded worse than chance, and why", () => {
    movers.useMovers.mockReturnValue({
      data: forecast({ outcome: { evaluated_at: "", stocks: { TMPV: [-3.4, true], PAYTM: [1.1, false] }, grades: { opening: grade() } } }),
      isLoading: false,
    });
    view();
    const banner = screen.getByRole("status");
    expect(banner).toHaveTextContent("worse than picking at random today");
    expect(banner).not.toHaveTextContent("better than picking");
    expect(banner).toHaveTextContent(/market-wide move day/);
    expect(within(screen.getByRole("article", { name: "TMPV forecast" })).getByText(/HIT/)).toBeInTheDocument();
  });

  it("credits a good day with its lift", () => {
    movers.useMovers.mockReturnValue({
      data: forecast({ outcome: { evaluated_at: "", stocks: {}, grades: { opening: grade({ hits: 4, precision: 0.4, base_rate: 0.08, lift: 5 }) } } }),
      isLoading: false,
    });
    view();
    expect(screen.getByRole("status")).toHaveTextContent("5.0× better than picking at random");
    expect(screen.getByRole("status")).not.toHaveTextContent(/market-wide/);
  });

  it("explains when the first forecast will appear", () => {
    movers.useMovers.mockReturnValue({
      data: { available: false, model: { source: "prior", version: "prior", fitted_at: null }, dates: [], disclaimer: "" },
      isLoading: false,
    });
    view();
    expect(screen.getByText("No forecast yet")).toBeInTheDocument();
    expect(screen.getByText(/09:08 pre-open auction/)).toBeInTheDocument();
  });

  it("hides the old research pipeline unless it is connected", () => {
    view();
    expect(screen.queryByRole("tab", { name: "Research pipeline" })).not.toBeInTheDocument();
  });

  it("keeps the old research pipeline in its own tab when connected", async () => {
    legacy.configured = true;
    view("/app/market-intelligence?tab=research");
    expect(screen.getByText("ranging_low")).toBeInTheDocument();
    expect(screen.getByText("Shree Cement")).toBeInTheDocument();
  });

  it("keeps the live, explained market read in its own tab", async () => {
    view();
    await userEvent.click(screen.getByRole("tab", { name: "Market read" }));
    expect(screen.getByText("Neutral")).toBeInTheDocument();
    expect(screen.getByText("NIFTY in a downtrend")).toBeInTheDocument();
    expect(screen.getByText("Foreign investors buying")).toBeInTheDocument();
  });

  it("lists filings by impact and labels those that came after the close", async () => {
    const catalysts: Catalysts = {
      trade_date: "2026-09-18",
      updated_at: "2026-09-18T20:00:00+05:30",
      events_updated_at: null,
      ai_reader: false,
      oi_spurts: { TCS: 30 },
      events: [
        { id: "ban:SAIL", symbol: "SAIL", source: "ban", category: "fo_ban", label: "In F&O ban period", impact: 0.3, direction: 0, title: "OI above limit", at: null, url: null, company: null },
      ],
      filings: [
        { id: "a", symbol: "BHARTIARTL", source: "nse_filing", category: "regulatory", label: "Regulatory action / penalty", impact: 0.55, direction: -1, title: "Order passed", at: "2026-09-18T18:29:00+05:30", url: null, company: null, session: "after_close" },
        { id: "b", symbol: "IOC", source: "nse_filing", category: "management", label: "Management change", impact: 0.25, direction: 0, title: "Director resigns", at: "2026-09-18T17:38:00+05:30", url: null, company: null, session: "after_close" },
      ],
    };
    movers.useCatalysts.mockReturnValue({ data: catalysts, isLoading: false });
    view("/app/market-intelligence?tab=catalysts");
    expect(screen.getByText("BHARTIARTL")).toBeInTheDocument();
    expect(screen.getByText("After the close · next session")).toBeInTheDocument();
    // "Material" (≥ 0.4) is the default: the 0.25 management change is hidden.
    expect(screen.queryByText("IOC")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Everything" }));
    expect(screen.getByText("IOC")).toBeInTheDocument();
    expect(screen.getByText("SAIL")).toBeInTheDocument();
    expect(screen.getByText("+30%")).toBeInTheDocument();
  });

  it("shows headlines with the stocks they name and their tone", () => {
    const news: MarketNews = {
      trade_date: "2026-09-18",
      feeds: 6,
      updated_at: null,
      items: [
        { id: "n1", title: "Power Grid to raise ₹5,000 crore through bonds", source: "Mint", url: "https://example.com/a", at: "2026-09-18T17:03:00+05:30", symbols: ["POWERGRID"], sentiment: 1 },
      ],
    };
    movers.useMarketNews.mockReturnValue({ data: news, isLoading: false });
    view("/app/market-intelligence?tab=news");
    expect(screen.getByRole("link", { name: /Power Grid to raise/ })).toHaveAttribute("href", "https://example.com/a");
    expect(screen.getByText("POWERGRID")).toBeInTheDocument();
    expect(screen.getByText(/positive tone/)).toBeInTheDocument();
  });

  it("shows the out-of-sample backtest and uses its calibration until live days accumulate", () => {
    const summary = { days: 18, top_k_picks: 180, hits: 50, precision: 0.2778, base_rate: 0.0816, lift: 3.4, recall: 0.17, direction_accuracy: 0.9149, direction_calls: 47, brier: 0.07 };
    const record: TrackRecord = {
      live: {
        opening: { summary: { ...summary, days: 1, hits: 2, top_k_picks: 10, precision: 0.2, base_rate: 0.21, lift: 0.95 }, daily: [] },
        overnight: { summary: { ...summary, days: 0 }, daily: [] },
      },
      calibration: [{ band: "5-10%", count: 144, predicted: 0.07, actual: 0.215 }],
      backtest: {
        ran_on: "2026-09-19",
        ran_at: "",
        sessions: 60,
        train: ["2026-06-29", "2026-08-25"],
        test: ["2026-08-26", "2026-09-18"],
        universe: 210,
        filings: 7104,
        base_rate: 0.0786,
        limits: ["Uses today's F&O list for past sessions (survivorship)."],
        stages: {
          opening: {
            weights_on_train: { bias: -3.7, weights: {} },
            fitted: { summary, daily: [] },
            prior: { summary: { ...summary, precision: 0.2167 }, daily: [] },
            calibration: [{ band: "50-100%", count: 10, predicted: 0.77, actual: 0.8 }],
          },
          overnight: {
            weights_on_train: { bias: -3.5, weights: {} },
            fitted: { summary, daily: [] },
            prior: { summary, daily: [] },
          },
        },
      },
      model: {
        source: "fitted",
        version: "v",
        fitted_at: null,
        fitted_on: "2026-09-19",
        features: [
          { name: "gap_abs", label: "Size of the pre-open gap", opening_only: true, prior: { opening: 0.25, overnight: 0.25 }, weight: { opening: 0.81, overnight: 0.25 } },
        ],
        bias: { opening: -3.7, overnight: -3.5 },
        prior_bias: { opening: -3.4, overnight: -3.1 },
        top_k: 10,
        threshold_rule: "max(3%, 2x the stock's typical daily move)",
      },
      disclaimer: "Graded daily.",
    };
    movers.useMoversTrackRecord.mockReturnValue({ data: record, isLoading: false });
    view("/app/market-intelligence?tab=record");
    expect(screen.getByText("Backtest · out of sample")).toBeInTheDocument();
    expect(screen.getByText("28%")).toBeInTheDocument();
    expect(screen.getByText("3.4×")).toBeInTheDocument();
    expect(screen.getByText("Live · 1 graded session")).toBeInTheDocument();
    // One live day is too few to judge calibration: the backtest's bands are used.
    expect(screen.getByText("50-100%")).toBeInTheDocument();
    expect(screen.queryByText("5-10%")).not.toBeInTheDocument();
    expect(screen.getByText("Size of the pre-open gap")).toBeInTheDocument();
  });

  it("keeps the daily briefing for the owner, and says when e-mail is not set up", () => {
    useAuth.setState({ user: { is_platform_admin: true } as never });
    movers.useBriefingArchive.mockReturnValue({
      isLoading: false,
      data: {
        dates: ["2026-09-18"],
        delivery: "console",
        enabled: true,
        briefing: {
          day: "2026-09-18",
          sent_at: "2026-09-18T09:10:12+05:30",
          subject: "AI-CIO briefing · Fri 18 Sep · watch TMPV",
          stage: "opening",
          recipients: ["owner@example.com"],
          delivery: "console",
          text: "",
          html: "<p>Morning briefing</p>",
        },
      },
    });
    view("/app/market-intelligence?tab=briefing");
    expect(screen.getByText(/E-mail is not set up on the server yet/)).toBeInTheDocument();
    expect(screen.getByText("AI-CIO briefing · Fri 18 Sep · watch TMPV")).toBeInTheDocument();
    expect(screen.getByTitle("Briefing")).toHaveAttribute("srcdoc", "<p>Morning briefing</p>");
    // Sandboxed: nothing in the stored HTML can run or navigate the console.
    expect(screen.getByTitle("Briefing")).toHaveAttribute("sandbox", "");
  });

  it("does not offer the briefing to other users", () => {
    view("/app/market-intelligence?tab=briefing");
    expect(screen.queryByRole("tab", { name: "Daily briefing" })).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Today's movers" })).toHaveAttribute("aria-selected", "true");
  });
});
