import { useMemo } from "react";

import { DrawdownChart, EquityAreaChart, PnlBarChart } from "@/components/charts";
import {
  Badge,
  Card,
  EmptyState,
  PageHeader,
  SkeletonRows,
  StatCard,
  Table,
  Td,
} from "@/components/ui";
import {
  useDailyPnl,
  useEquityCurve,
  useExposure,
  useMonthlyPnl,
  usePerformance,
} from "@/lib/hooks";
import { money, pct, pnlClass, signed, toNumber } from "@/lib/format";
import type { EquityPoint } from "@/types/api";

function buildDrawdownData(equity: EquityPoint[]) {
  let peak = 0;
  return equity.map((point) => {
    const value = toNumber(point.equity);
    peak = Math.max(peak, value);
    const drawdown = peak > 0 ? ((peak - value) / peak) * 100 : 0;
    return {
      label: new Date(point.as_of).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
      }),
      drawdown: Number(drawdown.toFixed(2)),
    };
  });
}

export function AnalyticsPage() {
  const { data: performance, isLoading } = usePerformance(90);
  const { data: equity } = useEquityCurve(90);
  const { data: daily } = useDailyPnl(60);
  const { data: monthly } = useMonthlyPnl(12);
  const { data: exposure } = useExposure();

  const equityData = (equity ?? []).map((point) => ({
    label: new Date(point.as_of).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
    equity: toNumber(point.equity),
  }));

  const dailyData = (daily ?? []).map((point) => ({
    label: point.day.slice(5),
    pnl: toNumber(point.realized_pnl),
  }));

  const monthlyData = (monthly ?? []).map((point) => ({
    label: point.month,
    pnl: toNumber(point.realized_pnl),
  }));

  const drawdownData = useMemo(() => buildDrawdownData(equity ?? []), [equity]);

  return (
    <div>
      <PageHeader title="Analytics" description="Performance metrics over the last 90 days" />

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-24 animate-pulse rounded-xl bg-slate-200 dark:bg-surface-800" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Win rate"
            value={pct(performance?.win_rate_pct)}
            sub={`${performance?.closing_trades ?? 0} closing trades`}
          />
          <StatCard
            label="Realized P&L"
            value={signed(performance?.total_realized_pnl)}
            valueClass={pnlClass(performance?.total_realized_pnl)}
          />
          <StatCard
            label="Profit factor"
            value={performance?.profit_factor ?? "—"}
            sub={`Avg win ${money(performance?.average_win)}`}
          />
          <StatCard
            label="Max drawdown"
            value={pct(performance?.max_drawdown_pct)}
            valueClass="text-loss-500"
            sub={`Vol ${pct(performance?.daily_return_volatility_pct)}`}
          />
        </div>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title="Equity curve (90 days)">
          {equityData.length === 0 ? (
            <EmptyState title="No equity data" />
          ) : (
            <EquityAreaChart data={equityData} />
          )}
        </Card>
        <Card title="Drawdown">
          {drawdownData.length === 0 ? (
            <EmptyState title="No drawdown data" />
          ) : (
            <DrawdownChart data={drawdownData} />
          )}
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title="Daily realized P&L">
          {dailyData.length === 0 ? (
            <EmptyState title="No daily P&L yet" body="Realized P&L appears after closing trades." />
          ) : (
            <PnlBarChart data={dailyData} />
          )}
        </Card>
        <Card title="Monthly realized P&L">
          {monthlyData.length === 0 ? (
            <EmptyState title="No monthly P&L yet" />
          ) : (
            <PnlBarChart data={monthlyData} />
          )}
        </Card>
      </div>

      <Card className="mt-6" title="Performance breakdown">
        {!performance ? (
          <SkeletonRows rows={4} cols={2} />
        ) : (
          <dl className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm sm:grid-cols-3">
            <Metric label="Total trades" value={String(performance.total_trades)} />
            <Metric label="Closing trades" value={String(performance.closing_trades)} />
            <Metric label="Total fees" value={money(performance.total_fees)} />
            <Metric label="Average win" value={money(performance.average_win)} />
            <Metric label="Average loss" value={money(performance.average_loss)} />
            <Metric label="Gross exposure" value={money(performance.gross_exposure)} />
            <Metric label="Sharpe ratio" value={performance.sharpe_ratio} />
            <Metric label="Sortino ratio" value={performance.sortino_ratio} />
            <Metric label="Calmar ratio" value={performance.calmar_ratio} />
            <Metric label="Annualized return" value={pct(performance.annualized_return_pct)} />
            <Metric
              label="Unrealized P&L"
              value={signed(performance.total_unrealized_pnl)}
              className={pnlClass(performance.total_unrealized_pnl)}
            />
          </dl>
        )}
      </Card>

      <Card className="mt-6" title="Current exposure">
        {!exposure ? (
          <SkeletonRows rows={4} cols={5} />
        ) : exposure.length === 0 ? (
          <EmptyState title="No open exposure" body="Open positions appear here by instrument." />
        ) : (
          <Table headers={["Instrument", "Asset class", "Side", "Quantity", "Market value"]}>
            {exposure.map((row) => (
              <tr key={row.instrument_id}>
                <Td className="font-medium">{row.symbol}</Td>
                <Td>{row.asset_class}</Td>
                <Td>
                  <Badge color={row.side === "long" ? "green" : "red"}>{row.side}</Badge>
                </Td>
                <Td className="tabular-nums">{row.quantity}</Td>
                <Td className="tabular-nums">{money(row.market_value, row.currency)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

function Metric({
  label,
  value,
  className,
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className={`mt-0.5 font-medium tabular-nums ${className ?? ""}`}>{value}</dd>
    </div>
  );
}
