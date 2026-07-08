import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Link } from "react-router";

import { EquityAreaChart } from "@/components/charts";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  PageHeader,
  SkeletonRows,
  StatCard,
  Table,
  Td,
  statusColor,
} from "@/components/ui";
import {
  useDashboard,
  useEquityCurve,
  useOrders,
  usePositions,
  useScanner,
  useStrategyRuns,
} from "@/lib/hooks";
import { dateTime, money, pct, pnlClass, signed, toNumber } from "@/lib/format";
import { liveChannel } from "@/lib/ws";
import { useAuth } from "@/stores/auth";

export function DashboardPage() {
  const { data: summary, isLoading } = useDashboard();
  const { data: equity } = useEquityCurve(30);
  const { data: openOrders } = useOrders({ open_only: true });
  const { data: positions } = usePositions();
  const { data: runs } = useStrategyRuns({ active_only: true });
  const { data: movers } = useScanner("active");
  const client = useQueryClient();
  const activeOrgId = useAuth((state) => state.activeOrgId);

  useEffect(() => {
    if (!activeOrgId) return;
    const channels = ["orders", "positions", "portfolio"];
    const unsubscribers = channels.map((channel) =>
      liveChannel.subscribe(channel, () => {
        client.invalidateQueries({ queryKey: ["dashboard"] });
        client.invalidateQueries({ queryKey: [channel === "portfolio" ? "positions" : channel] });
      }),
    );
    return () => unsubscribers.forEach((unsub) => unsub());
  }, [activeOrgId, client]);

  const equityData = (equity ?? []).map((point) => ({
    label: new Date(point.as_of).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
    equity: toNumber(point.equity),
  }));

  const totalPnl = summary
    ? toNumber(summary.realized_pnl_today) + toNumber(summary.unrealized_pnl)
    : 0;

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Live account overview and trading activity"
        actions={
          <Link to="/app/strategies">
            <Button size="sm">Deploy a strategy</Button>
          </Link>
        }
      />

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-24 animate-pulse rounded-xl bg-slate-200 dark:bg-surface-800" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Total Equity" value={money(summary?.total_equity)} sub={`${summary?.accounts ?? 0} accounts`} />
          <StatCard
            label="Today's P&L"
            value={signed(summary?.realized_pnl_today)}
            valueClass={pnlClass(summary?.realized_pnl_today)}
            sub={`${summary?.trades_today ?? 0} trades`}
          />
          <StatCard
            label="Unrealized P&L"
            value={signed(summary?.unrealized_pnl)}
            valueClass={pnlClass(summary?.unrealized_pnl)}
            sub={`${summary?.open_positions ?? 0} open positions`}
          />
          <StatCard
            label="Total P&L Impact"
            value={signed(totalPnl)}
            valueClass={pnlClass(totalPnl)}
            sub={`${summary?.active_strategies ?? 0} active strategies`}
          />
        </div>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Equity curve (30 days)" className="lg:col-span-2">
          {equityData.length === 0 ? (
            <EmptyState
              title="No equity history yet"
              body="Snapshots appear after the trading engine records account activity."
            />
          ) : (
            <EquityAreaChart data={equityData} />
          )}
        </Card>

        <div className="space-y-6">
          <Card
            title="Active strategies"
            actions={
              <Link to="/app/strategies" className="text-xs text-accent-500 hover:underline">
                View all
              </Link>
            }
          >
            {!runs || runs.length === 0 ? (
              <EmptyState title="No running strategies" body="Deploy a strategy to start trading." />
            ) : (
              <ul className="space-y-2">
                {runs.slice(0, 5).map((run) => (
                  <li key={run.id} className="flex items-center justify-between text-sm">
                    <Link
                      to={`/app/strategies/${run.strategy_id}`}
                      className="truncate hover:text-accent-500"
                    >
                      {run.strategy_name}
                    </Link>
                    <Badge color={statusColor(run.state)}>{run.state}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Top movers">
            {!movers || movers.length === 0 ? (
              <EmptyState title="No market data" body="Waiting for the live feed." />
            ) : (
              <ul className="space-y-1.5">
                {movers.slice(0, 6).map((mover) => (
                  <li key={mover.instrument_id} className="flex items-center justify-between text-sm">
                    <span className="font-medium">{mover.symbol}</span>
                    <span className="flex items-center gap-3 tabular-nums">
                      <span className="text-slate-500">{money(mover.last)}</span>
                      <span className={pnlClass(mover.change_pct)}>{pct(mover.change_pct)}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card
          title="Open orders"
          actions={
            <Link to="/app/orders" className="text-xs text-accent-500 hover:underline">
              View all
            </Link>
          }
        >
          {!openOrders ? (
            <SkeletonRows />
          ) : openOrders.items.length === 0 ? (
            <EmptyState title="No open orders" />
          ) : (
            <Table headers={["Symbol", "Side", "Qty", "Status"]} dense>
              {openOrders.items.slice(0, 6).map((order) => (
                <tr key={order.id}>
                  <Td dense className="font-medium">
                    {order.symbol}
                  </Td>
                  <Td dense>
                    <span className={order.side === "buy" ? "text-profit-500" : "text-loss-500"}>
                      {order.side.toUpperCase()}
                    </span>
                  </Td>
                  <Td dense className="tabular-nums">
                    {order.quantity}
                  </Td>
                  <Td dense>
                    <Badge color={statusColor(order.status)}>{order.status}</Badge>
                  </Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>

        <Card
          title="Open positions"
          actions={
            <Link to="/app/positions" className="text-xs text-accent-500 hover:underline">
              View all
            </Link>
          }
        >
          {!positions ? (
            <SkeletonRows />
          ) : positions.length === 0 ? (
            <EmptyState title="No open positions" />
          ) : (
            <Table headers={["Symbol", "Qty", "Avg", "Unreal. P&L"]} dense>
              {positions.slice(0, 6).map((position) => (
                <tr key={position.id}>
                  <Td dense className="font-medium">
                    {position.symbol}
                  </Td>
                  <Td dense className="tabular-nums">
                    <span className={position.side === "long" ? "text-profit-500" : "text-loss-500"}>
                      {position.quantity}
                    </span>
                  </Td>
                  <Td dense className="tabular-nums">
                    {money(position.average_price)}
                  </Td>
                  <Td dense className={`tabular-nums ${pnlClass(position.unrealized_pnl)}`}>
                    {signed(position.unrealized_pnl)}
                  </Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </div>

      {summary && summary.accounts === 0 && (
        <Card className="mt-6" title="Get started">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-slate-500">
              Connect a broker (start with the Paper Trading simulator) to begin.
            </p>
            <Link to="/app/brokers">
              <Button size="sm">Connect a broker</Button>
            </Link>
          </div>
        </Card>
      )}

      <p className="mt-4 text-center text-xs text-slate-400">
        Last updated {dateTime(new Date().toISOString())} · live updates stream over WebSocket
      </p>
    </div>
  );
}
