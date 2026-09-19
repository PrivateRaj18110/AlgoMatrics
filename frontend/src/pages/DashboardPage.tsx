import { useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { useEffect } from "react";
import { Link } from "react-router";

import { EquityAreaChart } from "@/components/charts";
import { Glyph } from "@/components/icons";
import {
  Badge,
  Card,
  EmptyState,
  PageHeader,
  Skeleton,
  SkeletonRows,
  StatCard,
  Table,
  Td,
  buttonClass,
  statusColor,
} from "@/components/ui";
import {
  useDashboard,
  useEquityCurve,
  useOrders,
  usePositions,
  useStrategyRuns,
} from "@/lib/hooks";
import { dateOnly, dateTime, money, pnlClass, signed, toNumber } from "@/lib/format";
import { pctText, useMarketPulse } from "@/lib/markets";
import { liveChannel } from "@/lib/ws";
import { OpsOverviewStrip } from "@/pages/operations/OperationsPages";
import { activeOrg, useAuth } from "@/stores/auth";

function greeting(hour: number): string {
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function toneFor(value: number): "profit" | "loss" | "neutral" {
  if (value > 0) return "profit";
  if (value < 0) return "loss";
  return "neutral";
}

function ChangePill({ value, suffix }: { value: number; suffix?: string }) {
  const up = value >= 0;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums ring-1 ring-inset",
        up
          ? "bg-profit-500/10 text-profit-700 ring-profit-500/20 dark:text-profit-400"
          : "bg-loss-500/10 text-loss-700 ring-loss-500/20 dark:text-loss-400",
      )}
    >
      <Glyph name={up ? "trendUp" : "trendDown"} className="size-3" strokeWidth={2.2} />
      {up ? "+" : ""}
      {value.toFixed(2)}%{suffix ? <span className="font-normal opacity-80"> {suffix}</span> : null}
    </span>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-8 mb-3 text-[11px] font-semibold tracking-[0.16em] text-slate-400 uppercase dark:text-slate-500">
      {children}
    </p>
  );
}

function SideTag({ side }: { side: string }) {
  const buy = side === "buy" || side === "long";
  return (
    <span
      className={clsx(
        "inline-flex min-w-11 justify-center rounded-md px-1.5 py-0.5 text-[11px] font-semibold tracking-wide uppercase",
        buy
          ? "bg-profit-500/10 text-profit-700 dark:text-profit-400"
          : "bg-loss-500/10 text-loss-700 dark:text-loss-400",
      )}
    >
      {side}
    </span>
  );
}

const viewAll =
  "inline-flex items-center gap-1 text-xs font-medium text-accent-600 hover:text-accent-500 dark:text-accent-400 dark:hover:text-accent-300";

export function DashboardPage() {
  const { data: summary, isLoading } = useDashboard();
  const { data: equity } = useEquityCurve(30);
  const { data: openOrders } = useOrders({ open_only: true });
  const { data: positions } = usePositions();
  const { data: runs } = useStrategyRuns({ active_only: true });
  // Real F&O movers (NSE universe, delayed quotes), not the simulated feed.
  const { data: pulse } = useMarketPulse();
  const movers = pulse ? [...pulse.gainers.slice(0, 3), ...pulse.losers.slice(0, 3)] : undefined;
  const client = useQueryClient();
  const activeOrgId = useAuth((state) => state.activeOrgId);
  const user = useAuth((state) => state.user);
  const org = activeOrg();

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

  // Both ends come from the server; nothing here is estimated.
  const startingBalance = toNumber(summary?.starting_balance);
  const sinceStart =
    summary && startingBalance > 0
      ? ((toNumber(summary.total_equity) - startingBalance) / startingBalance) * 100
      : null;
  const periodChange =
    equityData.length > 1 && equityData[0].equity > 0
      ? ((equityData[equityData.length - 1].equity - equityData[0].equity) / equityData[0].equity) *
        100
      : null;

  const firstName = user?.full_name?.split(" ")[0];
  const nowIso = new Date().toISOString();

  return (
    <div className="am-fade-in">
      <PageHeader
        eyebrow={[org?.name, dateOnly(nowIso)].filter(Boolean).join(" · ")}
        title={`${greeting(new Date().getHours())}${firstName ? `, ${firstName}` : ""}`}
        description="Live account overview and trading activity"
        actions={
          <>
            <Link to="/app/trading" className={buttonClass({ variant: "secondary", size: "sm" })}>
              <Glyph name="bolt" className="size-3.5" />
              Open trading
            </Link>
            <Link to="/app/strategies" className={buttonClass({ size: "sm" })}>
              <Glyph name="rocket" className="size-3.5" />
              Deploy a strategy
            </Link>
          </>
        }
      />

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-[132px] rounded-2xl" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Total Equity"
            value={money(summary?.total_equity)}
            icon={<Glyph name="wallet" />}
            tone="accent"
            sub={`${summary?.accounts ?? 0} accounts`}
            footer={
              sinceStart !== null ? (
                <div className="mt-3">
                  <ChangePill value={sinceStart} suffix="since start" />
                </div>
              ) : null
            }
          />
          <StatCard
            label="Today's P&L"
            value={signed(summary?.realized_pnl_today)}
            valueClass={pnlClass(summary?.realized_pnl_today)}
            icon={<Glyph name="trendUp" />}
            tone={toneFor(toNumber(summary?.realized_pnl_today))}
            sub={`${summary?.trades_today ?? 0} trades`}
          />
          <StatCard
            label="Unrealized P&L"
            value={signed(summary?.unrealized_pnl)}
            valueClass={pnlClass(summary?.unrealized_pnl)}
            icon={<Glyph name="layers" />}
            tone={toneFor(toNumber(summary?.unrealized_pnl))}
            sub={`${summary?.open_positions ?? 0} open positions`}
          />
          <StatCard
            label="Total P&L Impact"
            value={signed(totalPnl)}
            valueClass={pnlClass(totalPnl)}
            icon={<Glyph name="pulse" />}
            tone={toneFor(totalPnl)}
            sub={`${summary?.active_strategies ?? 0} active strategies`}
          />
        </div>
      )}

      <OpsOverviewStrip />

      <SectionLabel>Performance</SectionLabel>
      <div className="grid gap-6 lg:grid-cols-3">
        <Card
          title="Equity curve"
          subtitle="Last 30 days"
          icon={<Glyph name="chart" className="size-3.5" />}
          className="flex flex-col lg:col-span-2"
          actions={periodChange !== null ? <ChangePill value={periodChange} suffix="30d" /> : null}
          bodyClassName="flex-1 min-h-[300px] px-3 pt-4 pb-3"
        >
          {equityData.length === 0 ? (
            <EmptyState
              title="No equity history yet"
              body="Snapshots appear after the trading engine records account activity."
            />
          ) : (
            // Fills the card, which the grid stretches to the height of the side column.
            <EquityAreaChart data={equityData} height="100%" />
          )}
        </Card>

        <div className="space-y-6">
          <Card
            title="Active strategies"
            icon={<Glyph name="rocket" className="size-3.5" />}
            actions={
              <Link to="/app/strategies" className={viewAll}>
                View all
                <Glyph name="arrowRight" className="size-3" />
              </Link>
            }
            bodyClassName="p-2"
          >
            {!runs || runs.length === 0 ? (
              <EmptyState title="No running strategies" body="Deploy a strategy to start trading." />
            ) : (
              <ul>
                {runs.slice(0, 5).map((run) => (
                  <li key={run.id}>
                    <Link
                      to={`/app/strategies/${run.strategy_id}`}
                      className="flex items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors hover:bg-slate-50 dark:hover:bg-white/[0.03]"
                    >
                      <span className="min-w-0">
                        <span className="block truncate font-medium text-slate-800 dark:text-slate-100">
                          {run.strategy_name}
                        </span>
                        <span className="text-xs text-slate-500 uppercase">
                          {run.mode} · {run.timeframe}
                        </span>
                      </span>
                      <Badge color={statusColor(run.state)} dot>
                        {run.state}
                      </Badge>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title="Top movers"
            subtitle="NSE F&O · delayed"
            icon={<Glyph name="trendUp" className="size-3.5" />}
            bodyClassName="p-2"
            actions={
              <Link to="/app/heatmap" className={viewAll}>
                Heatmap
                <Glyph name="arrowRight" className="size-3" />
              </Link>
            }
          >
            {!movers || movers.length === 0 ? (
              <EmptyState title="No market data" body="Quotes are briefly unavailable." />
            ) : (
              <ul>
                {movers.map((mover) => {
                  const change = mover.change_pct ?? 0;
                  return (
                    <li
                      key={mover.symbol}
                      className="flex items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm"
                    >
                      <span className="flex min-w-0 items-center gap-2.5">
                        <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-[10px] font-bold text-slate-500 dark:bg-white/[0.06] dark:text-slate-300">
                          {mover.symbol.slice(0, 2)}
                        </span>
                        <span className="truncate font-medium text-slate-800 dark:text-slate-100">
                          {mover.symbol}
                        </span>
                      </span>
                      <span className="flex items-center gap-3 tabular-nums">
                        <span className="text-slate-500 dark:text-slate-400">{money(mover.price)}</span>
                        <span
                          className={clsx(
                            "min-w-16 rounded-md px-1.5 py-0.5 text-right text-xs font-semibold",
                            change > 0 && "bg-profit-500/10 text-profit-700 dark:text-profit-400",
                            change < 0 && "bg-loss-500/10 text-loss-700 dark:text-loss-400",
                            change === 0 && "text-slate-500",
                          )}
                        >
                          {pctText(mover.change_pct)}
                        </span>
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </div>
      </div>

      <SectionLabel>Activity</SectionLabel>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card
          title="Open orders"
          subtitle={openOrders ? `${openOrders.items.length} working` : undefined}
          icon={<Glyph name="list" className="size-3.5" />}
          actions={
            <Link to="/app/orders" className={viewAll}>
              View all
              <Glyph name="arrowRight" className="size-3" />
            </Link>
          }
          bodyClassName="px-2 py-2"
        >
          {!openOrders ? (
            <SkeletonRows />
          ) : openOrders.items.length === 0 ? (
            <EmptyState title="No open orders" />
          ) : (
            <Table headers={["Symbol", "Side", "Qty", "Status"]} dense>
              {openOrders.items.slice(0, 6).map((order) => (
                <tr key={order.id}>
                  <Td dense className="font-medium text-slate-800 dark:text-slate-100">
                    {order.symbol}
                  </Td>
                  <Td dense>
                    <SideTag side={order.side} />
                  </Td>
                  <Td dense className="tabular-nums">
                    {order.quantity}
                  </Td>
                  <Td dense>
                    <Badge color={statusColor(order.status)}>{order.status.replace(/_/g, " ")}</Badge>
                  </Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>

        <Card
          title="Open positions"
          subtitle={positions ? `${positions.length} held` : undefined}
          icon={<Glyph name="layers" className="size-3.5" />}
          actions={
            <Link to="/app/positions" className={viewAll}>
              View all
              <Glyph name="arrowRight" className="size-3" />
            </Link>
          }
          bodyClassName="px-2 py-2"
        >
          {!positions ? (
            <SkeletonRows />
          ) : positions.length === 0 ? (
            <EmptyState title="No open positions" />
          ) : (
            <Table headers={["Symbol", "Side", "Qty", "Avg", "Unreal. P&L"]} dense>
              {positions.slice(0, 6).map((position) => (
                <tr key={position.id}>
                  <Td dense className="font-medium text-slate-800 dark:text-slate-100">
                    {position.symbol}
                  </Td>
                  <Td dense>
                    <SideTag side={position.side} />
                  </Td>
                  <Td dense className="tabular-nums">
                    {position.quantity}
                  </Td>
                  <Td dense className="tabular-nums text-slate-500 dark:text-slate-400">
                    {money(position.average_price)}
                  </Td>
                  <Td dense className={`font-medium tabular-nums ${pnlClass(position.unrealized_pnl)}`}>
                    {signed(position.unrealized_pnl)}
                  </Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </div>

      {summary && summary.accounts === 0 && (
        <Card className="mt-6" title="Get started" icon={<Glyph name="rocket" className="size-3.5" />}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Connect a broker (start with the Paper Trading simulator) to begin.
            </p>
            <Link to="/app/brokers" className={buttonClass({ size: "sm" })}>
              Connect a broker
            </Link>
          </div>
        </Card>
      )}

      <p className="mt-8 flex items-center justify-center gap-2 text-center text-xs text-slate-400 dark:text-slate-500">
        <span className="am-live-dot size-1.5 rounded-full bg-accent-500" aria-hidden />
        Last updated {dateTime(nowIso)} · live updates stream over WebSocket
      </p>
    </div>
  );
}
