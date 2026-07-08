import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/hooks", () => ({
  useAccounts: () => ({
    data: [
      {
        id: "acc-1",
        connection_id: "conn-1",
        external_account_id: "X1",
        name: "Paper INR",
        mode: "paper",
        base_currency: "INR",
        cash_balance: "80000",
        starting_balance: "100000",
        equity: "105000",
        status: "active",
      },
    ],
    isLoading: false,
  }),
  usePositions: () => ({
    data: [
      {
        id: "pos-1",
        account_id: "acc-1",
        instrument_id: "inst-1",
        symbol: "RELIANCE",
        side: "long",
        quantity: "10",
        average_price: "2900",
        last_mark: "2950",
        market_value: "29500",
        unrealized_pnl: "500",
        realized_pnl: "0",
        fees_paid: "0",
        updated_at: "2026-07-05T00:00:00Z",
      },
    ],
    isLoading: false,
  }),
  useExposure: () => ({
    data: [
      {
        instrument_id: "inst-1",
        symbol: "RELIANCE",
        asset_class: "equity",
        currency: "INR",
        quantity: "10",
        market_value: "29500",
        side: "long",
      },
    ],
  }),
}));

import { PortfolioPage } from "@/pages/PortfolioPage";

describe("PortfolioPage", () => {
  it("renders holdings, allocation, and accounts from the API hooks", () => {
    render(<PortfolioPage />);

    expect(screen.getByText("Paper INR")).toBeInTheDocument();
    expect(screen.getAllByText("RELIANCE").length).toBeGreaterThan(0);
    expect(screen.getByText("equity")).toBeInTheDocument();
    expect(screen.getByText("100.0%")).toBeInTheDocument();
  });
});
