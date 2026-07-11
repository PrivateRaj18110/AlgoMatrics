import { useNavigate, useParams } from "react-router";

import { Tabs } from "@/components/ui";
import { OrdersPage } from "@/pages/OrdersPage";
import { PortfolioPage } from "@/pages/PortfolioPage";
import { PositionsPage } from "@/pages/PositionsPage";
import { RiskPage } from "@/pages/RiskPage";
import { TradesPage } from "@/pages/TradesPage";

const TABS: Array<{ key: string; label: string }> = [
  { key: "orders", label: "Orders" },
  { key: "positions", label: "Positions" },
  { key: "trades", label: "Trades" },
  { key: "portfolio", label: "Portfolio" },
  { key: "risk", label: "Risk" },
];

/**
 * Single intraday trading workspace: orders, positions, trades, portfolio and
 * risk in one place. The active tab lives in the URL (/app/trading/:tab) so
 * deep links and the old per-page bookmarks keep working via redirects.
 */
export function TradingPage() {
  const navigate = useNavigate();
  const { tab } = useParams();
  const active = TABS.some((candidate) => candidate.key === tab) ? (tab as string) : "orders";

  return (
    <div className="space-y-4">
      <Tabs
        tabs={TABS}
        active={active}
        onChange={(key) => navigate(`/app/trading/${key}`, { replace: true })}
      />
      {active === "orders" && <OrdersPage />}
      {active === "positions" && <PositionsPage />}
      {active === "trades" && <TradesPage />}
      {active === "portfolio" && <PortfolioPage />}
      {active === "risk" && <RiskPage />}
    </div>
  );
}
