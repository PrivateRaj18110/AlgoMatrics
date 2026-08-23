import { useMemo } from "react";
import { useLocation, useParams } from "react-router";

import { Card, EmptyState, PageHeader, SkeletonRows, Table, Td } from "@/components/ui";
import {
  inRegion,
  regionEmptyCopy,
  regionLabel,
  regionZone,
  type MarketRegion,
} from "@/lib/marketRegion";
import { useOpsMachines, useOpsOrders, useOpsStrategies, useOpsTrades } from "@/lib/hooks";
import { signed } from "@/lib/format";
import { formatInZone } from "@/lib/time";
import { AnalyticsPage } from "@/pages/AnalyticsPage";
import { BrokersPage } from "@/pages/BrokersPage";
import { LogsPage } from "@/pages/operations/OperationsPages";
import { MarketPage } from "@/pages/MarketPage";
import { PortfolioPage } from "@/pages/PortfolioPage";
import { PositionsPage } from "@/pages/PositionsPage";
import { RiskPage } from "@/pages/RiskPage";
import { StrategiesPage } from "@/pages/StrategiesPage";

const SECTIONS = new Set([
  "overview",
  "strategies",
  "positions",
  "closed-trades",
  "portfolio",
  "brokers",
  "analytics",
  "risk",
  "execution",
  "logs",
]);

function useActiveRegion(): { region: MarketRegion; section: string } {
  const location = useLocation();
  const params = useParams();
  const region: MarketRegion = location.pathname.startsWith("/app/international")
    ? "international"
    : "india";
  const section = params.section && SECTIONS.has(params.section) ? params.section : "overview";
  return { region, section };
}

function RegionEmpty({ region }: { region: MarketRegion }) {
  return <EmptyState title={regionEmptyCopy(region)} body="Production stays empty until real telemetry or accounts exist for this market." />;
}

export function MarketSectionPage() {
  const { region, section } = useActiveRegion();
  const zone = regionZone(region);
  const label = regionLabel(region);

  if (section === "overview") {
    return (
      <div className="space-y-6">
        <PageHeader
          title={`${label} overview`}
          description={`Times display in ${zone}. Storage and API remain UTC.`}
        />
        {region === "india" ? <MarketPage /> : null}
        <RegionMachines region={region} />
      </div>
    );
  }
  if (section === "strategies") {
    return (
      <div className="space-y-6">
        <PageHeader title={`${label} strategies`} />
        <RegionStrategies region={region} />
        {region === "india" ? <StrategiesPage /> : null}
      </div>
    );
  }
  if (section === "positions") return <PositionsPage region={region} />;
  if (section === "closed-trades") return <RegionTrades region={region} />;
  if (section === "portfolio") return <PortfolioPage />;
  if (section === "brokers") return <BrokersPage embedded region={region} />;
  if (section === "analytics") return <AnalyticsPage />;
  if (section === "risk") return <RiskPage />;
  if (section === "execution") return <RegionOrders region={region} />;
  if (section === "logs") return <LogsPage />;
  return <RegionEmpty region={region} />;
}

function RegionMachines({ region }: { region: MarketRegion }) {
  const { data, isLoading, isError } = useOpsMachines();
  const rows = useMemo(() => inRegion(region, data), [data, region]);
  return (
    <Card>
      {isLoading ? (
        <SkeletonRows rows={4} cols={5} />
      ) : isError ? (
        <EmptyState title="Telemetry unavailable" />
      ) : !rows.length ? (
        <RegionEmpty region={region} />
      ) : (
        <Table headers={["Machine", "Status", "Heartbeat"]}>
          {rows.map((row) => (
            <tr key={row.id}>
              <Td>{row.hostname || row.name || row.id}</Td>
              <Td>{row.status ?? "—"}</Td>
              <Td>{formatInZone(row.last_heartbeat, regionZone(region))}</Td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}

function RegionStrategies({ region }: { region: MarketRegion }) {
  const { data, isLoading, isError } = useOpsStrategies();
  const rows = useMemo(
    () =>
      (data ?? []).filter((row) => {
        if (row.symbols && row.symbols.length > 0) {
          return row.symbols.some(
            (symbol) => inRegion(region, [{ symbol, machine: row.machine_id }]).length > 0,
          );
        }
        return inRegion(region, [{ machine: row.machine_id, name: row.strategy_name }]).length > 0;
      }),
    [data, region],
  );
  if (isLoading) return <SkeletonRows rows={4} cols={5} />;
  if (isError) return <EmptyState title="Telemetry unavailable" />;
  if (!rows.length) return <RegionEmpty region={region} />;
  return (
    <Card>
      <Table headers={["Strategy", "Symbols", "Trades", "PnL"]}>
        {rows.map((row) => (
          <tr key={row.strategy_id}>
            <Td>{row.strategy_name}</Td>
            <Td>{row.symbols?.join(", ") || "—"}</Td>
            <Td>{row.trade_count ?? "—"}</Td>
            <Td>{row.total_pnl == null ? "—" : signed(row.total_pnl)}</Td>
          </tr>
        ))}
      </Table>
    </Card>
  );
}

function RegionTrades({ region }: { region: MarketRegion }) {
  const { data, isLoading, isError } = useOpsTrades();
  const rows = useMemo(() => inRegion(region, data), [data, region]);
  return (
    <div>
      <PageHeader title={`${regionLabel(region)} closed trades`} description="Only classified trade / trade_closed rows." />
      <Card>
        {isLoading ? (
          <SkeletonRows rows={5} cols={6} />
        ) : isError ? (
          <EmptyState title="Telemetry unavailable" />
        ) : !rows.length ? (
          <RegionEmpty region={region} />
        ) : (
          <Table headers={["Time", "Strategy", "Symbol", "Side", "PnL"]}>
            {rows.map((row) => (
              <tr key={row.id}>
                <Td>{formatInZone(row.time, regionZone(region))}</Td>
                <Td>{row.strategy ?? "—"}</Td>
                <Td>{row.symbol ?? "—"}</Td>
                <Td>{row.direction ?? "—"}</Td>
                <Td>{row.pnl == null ? "—" : signed(row.pnl)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

function RegionOrders({ region }: { region: MarketRegion }) {
  const { data, isLoading, isError } = useOpsOrders();
  const rows = useMemo(() => inRegion(region, data), [data, region]);
  return (
    <div>
      <PageHeader title={`${regionLabel(region)} execution`} />
      <Card>
        {isLoading ? (
          <SkeletonRows rows={5} cols={5} />
        ) : isError ? (
          <EmptyState title="Telemetry unavailable" />
        ) : !rows.length ? (
          <RegionEmpty region={region} />
        ) : (
          <Table headers={["Time", "Strategy", "Symbol", "Summary"]}>
            {rows.map((row) => (
              <tr key={row.id}>
                <Td>{formatInZone(row.time, regionZone(region))}</Td>
                <Td>{row.strategy ?? "—"}</Td>
                <Td>{row.symbol ?? "—"}</Td>
                <Td>{row.payload_summary || row.message || "—"}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}
