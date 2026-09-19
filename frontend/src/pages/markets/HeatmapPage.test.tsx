import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { FoHeatmap, FoStock } from "@/lib/markets";

const hooks = vi.hoisted(() => ({ useFoHeatmap: vi.fn() }));

vi.mock("@/lib/markets", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/markets")>()),
  useFoHeatmap: hooks.useFoHeatmap,
}));

import { HeatmapPage } from "@/pages/markets/HeatmapPage";

function stock(overrides: Partial<FoStock> & { symbol: string }): FoStock {
  return {
    name: `${overrides.symbol} Ltd`,
    sector: "Banks",
    price: 100,
    previous_close: 99,
    change_pct: 1.01,
    day_high: 101,
    day_low: 98,
    year_high: 120,
    year_low: 80,
    volume: 1_000_000,
    market_cap: 1e12,
    as_of: 1_789_724_701,
    ...overrides,
  };
}

function result(stocks: FoStock[] | undefined, over: Record<string, unknown> = {}) {
  const data: FoHeatmap | undefined = stocks && {
    universe: { source: "nse", trade_date: "2026-09-18" },
    session: { state: "open", as_of: "2026-09-18T11:00:00+05:30", note: "" },
    breadth: {
      advances: 2,
      declines: 1,
      unchanged: 0,
      ratio: 2,
      pct_advancing: 66.7,
      near_year_high: 0,
      near_year_low: 0,
    },
    stocks,
    quoted: stocks.length,
    total: stocks.length,
  };
  return {
    data,
    isLoading: false,
    isError: false,
    isSuccess: true,
    dataUpdatedAt: Date.parse("2026-09-18T05:30:00Z"),
    ...over,
  };
}

function tiles() {
  return screen
    .queryAllByRole("button")
    .filter((button) => /%|UNKNOWN/.test(button.getAttribute("aria-label") ?? ""));
}

describe("HeatmapPage (NSE F&O universe)", () => {
  beforeEach(() => {
    hooks.useFoHeatmap.mockReset();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("labels each tile with its symbol and signed change", () => {
    hooks.useFoHeatmap.mockReturnValue(result([stock({ symbol: "RELIANCE", change_pct: 2.4 })]));
    render(<HeatmapPage />);
    const tile = screen.getByRole("button", { name: /RELIANCE, \+2\.40%/ });
    expect(within(tile).getByText("+2.40%")).toBeInTheDocument();
  });

  it("colours gains and losses differently", () => {
    hooks.useFoHeatmap.mockReturnValue(
      result([stock({ symbol: "TCS", change_pct: -1.8 }), stock({ symbol: "INFY", change_pct: 1.8 })]),
    );
    render(<HeatmapPage />);
    const loser = screen.getByRole("button", { name: /TCS, -1\.80%/ });
    const winner = screen.getByRole("button", { name: /INFY, \+1\.80%/ });
    expect(loser.style.background).not.toBe(winner.style.background);
  });

  it("marks a missing quote UNKNOWN, never 0%", () => {
    hooks.useFoHeatmap.mockReturnValue(
      result([stock({ symbol: "WIPRO", change_pct: null, price: null }), stock({ symbol: "ITC", change_pct: 0 })]),
    );
    render(<HeatmapPage />);
    const missing = screen.getByRole("button", { name: /WIPRO, UNKNOWN/ });
    expect(within(missing).getByText("UNKNOWN")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ITC, 0\.00%/ })).toBeInTheDocument();
    expect(screen.getByText(/MARKED UNKNOWN, NOT 0%/)).toBeInTheDocument();
  });

  it("states where the universe and the tile sizes come from", () => {
    hooks.useFoHeatmap.mockReturnValue(result([stock({ symbol: "SBIN" })]));
    render(<HeatmapPage />);
    expect(screen.getByText(/LIST FROM NSE 2026-09-18/)).toBeInTheDocument();
    expect(screen.getByText(/TILE AREA = MARKET CAP \(NSE PRE-OPEN SNAPSHOT\)/)).toBeInTheDocument();
  });

  it("falls back to equal tiles — and says so — when market cap is unknown", () => {
    hooks.useFoHeatmap.mockReturnValue(result([stock({ symbol: "LT", market_cap: null })]));
    render(<HeatmapPage />);
    expect(screen.getByText(/MARKET CAP NOT YET AVAILABLE, NOT SYNTHESISED/)).toBeInTheDocument();
  });

  it("groups tiles under sector headers", () => {
    hooks.useFoHeatmap.mockReturnValue(
      result([
        stock({ symbol: "HDFCBANK", sector: "Banks" }),
        stock({ symbol: "TCS", sector: "IT" }),
      ]),
    );
    render(<HeatmapPage />);
    // Sector name appears as a filter chip and as the frame header.
    expect(screen.getAllByText("IT").length).toBeGreaterThanOrEqual(2);
  });

  it("filters to one sector", async () => {
    hooks.useFoHeatmap.mockReturnValue(
      result([
        stock({ symbol: "HDFCBANK", sector: "Banks" }),
        stock({ symbol: "TCS", sector: "IT" }),
      ]),
    );
    render(<HeatmapPage />);
    await userEvent.click(screen.getByRole("button", { name: "IT" }));
    expect(screen.queryByRole("button", { name: /HDFCBANK/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /TCS/ })).toBeInTheDocument();
  });

  it("shows every detail in the footer when a tile is selected", async () => {
    hooks.useFoHeatmap.mockReturnValue(
      result([stock({ symbol: "AXISBANK", price: 1120.5, previous_close: 1100, market_cap: 3.4e12 })]),
    );
    const { container } = render(<HeatmapPage />);
    await userEvent.click(screen.getByRole("button", { name: /AXISBANK/ }));
    const footer = container.querySelector("footer")!;
    expect(within(footer).getByText("1,120.50")).toBeInTheDocument();
    expect(within(footer).getByText("1,100.00")).toBeInTheDocument();
    expect(within(footer).getByText("₹3,40,000 cr")).toBeInTheDocument();
  });

  it("offers a sortable table of all stocks", async () => {
    hooks.useFoHeatmap.mockReturnValue(
      result([stock({ symbol: "AAA", change_pct: -3 }), stock({ symbol: "BBB", change_pct: 5 })]),
    );
    render(<HeatmapPage />);
    await userEvent.click(screen.getByRole("button", { name: "table" }));
    const rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[0]).getByText("BBB")).toBeInTheDocument(); // biggest gainer first
    expect(within(rows[1]).getByText("AAA")).toBeInTheDocument();
  });

  it("shows an explicit empty state rather than placeholder instruments", () => {
    hooks.useFoHeatmap.mockReturnValue(result([]));
    render(<HeatmapPage />);
    expect(screen.getByText("NO SECURITIES IN UNIVERSE")).toBeInTheDocument();
    expect(tiles()).toHaveLength(0);
  });

  it("says the data is unavailable on API failure and shows no values", () => {
    hooks.useFoHeatmap.mockReturnValue(result(undefined, { isError: true, isSuccess: false }));
    render(<HeatmapPage />);
    expect(screen.getByText("MARKET DATA UNAVAILABLE")).toBeInTheDocument();
    expect(screen.getByText(/FAILED — SHOWING LAST KNOWN/)).toBeInTheDocument();
    expect(tiles()).toHaveLength(0);
  });

  it("lays tiles out in percentages so the grid rescales with the viewport", () => {
    hooks.useFoHeatmap.mockReturnValue(
      result([stock({ symbol: "A" }), stock({ symbol: "B" }), stock({ symbol: "C" })]),
    );
    render(<HeatmapPage />);
    for (const tile of tiles()) {
      expect(tile.style.width).toMatch(/%$/);
      expect(tile.style.left).toMatch(/%$/);
    }
  });

  it("offers no trading control of any kind", () => {
    hooks.useFoHeatmap.mockReturnValue(result([stock({ symbol: "RELIANCE" }), stock({ symbol: "TCS" })]));
    const { container } = render(<HeatmapPage />);
    for (const word of [/\bbuy\b/i, /\bsell\b/i, /\border\b/i, /\bexecute\b/i, /square off/i]) {
      expect(container.textContent).not.toMatch(word);
    }
    expect(container.querySelector("form")).toBeNull();
  });
});
