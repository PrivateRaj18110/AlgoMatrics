import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/hooks", () => {
  const idleMutation = () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
  });
  return {
  useWatchlists: () => ({
    data: [
      {
        id: "wl-1",
        name: "Momentum",
        created_at: "2026-07-05T00:00:00Z",
        items: [
          { id: "item-1", instrument_id: "inst-1", symbol: "RELIANCE", name: "Reliance", sort_order: 1 },
        ],
      },
    ],
    isLoading: false,
  }),
  useInstruments: () => ({ data: [] }),
  useQuotes: () => ({
    data: [
      {
        instrument_id: "inst-1",
        symbol: "RELIANCE",
        bid: null,
        ask: null,
        last: "2950.50",
        change_pct: "1.25",
        timestamp: null,
      },
    ],
  }),
    useCreateWatchlist: idleMutation,
    useRenameWatchlist: idleMutation,
    useDeleteWatchlist: idleMutation,
    useAddWatchlistItem: idleMutation,
    useRemoveWatchlistItem: idleMutation,
  };
});

import { WatchlistsPage } from "@/pages/WatchlistsPage";

describe("WatchlistsPage", () => {
  it("renders watchlists with live quotes for their instruments", () => {
    render(<WatchlistsPage />);

    expect(screen.getAllByText("Momentum").length).toBeGreaterThan(0);
    expect(screen.getByText("RELIANCE")).toBeInTheDocument();
    expect(screen.getByText("2950.50")).toBeInTheDocument();
    expect(screen.getByText("1.25%")).toBeInTheDocument();
  });
});
