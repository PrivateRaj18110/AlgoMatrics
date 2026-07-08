import { useMemo } from "react";

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
import { useAccounts, useExposure, usePositions } from "@/lib/hooks";
import { money, pnlClass, signed, toNumber } from "@/lib/format";

interface Allocation {
  assetClass: string;
  value: number;
  pct: number;
}

export function PortfolioPage() {
  const { data: accounts, isLoading: accountsLoading } = useAccounts();
  const { data: positions, isLoading: positionsLoading } = usePositions();
  const { data: exposure } = useExposure();

  const totals = useMemo(() => {
    const accountList = accounts ?? [];
    const positionList = positions ?? [];
    return {
      equity: accountList.reduce((sum, account) => sum + toNumber(account.equity), 0),
      cash: accountList.reduce((sum, account) => sum + toNumber(account.cash_balance), 0),
      exposure: positionList.reduce((sum, position) => sum + toNumber(position.market_value), 0),
      unrealized: positionList.reduce(
        (sum, position) => sum + toNumber(position.unrealized_pnl),
        0,
      ),
    };
  }, [accounts, positions]);

  const allocations = useMemo<Allocation[]>(() => {
    const rows = exposure ?? [];
    const byClass = new Map<string, number>();
    for (const row of rows) {
      byClass.set(
        row.asset_class,
        (byClass.get(row.asset_class) ?? 0) + Math.abs(toNumber(row.market_value)),
      );
    }
    const total = [...byClass.values()].reduce((sum, value) => sum + value, 0);
    return [...byClass.entries()]
      .map(([assetClass, value]) => ({
        assetClass,
        value,
        pct: total > 0 ? (value / total) * 100 : 0,
      }))
      .sort((a, b) => b.value - a.value);
  }, [exposure]);

  return (
    <div>
      <PageHeader title="Portfolio" description="Holdings, cash, and allocation across accounts" />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total equity" value={money(totals.equity)} />
        <StatCard label="Cash" value={money(totals.cash)} />
        <StatCard label="Gross exposure" value={money(totals.exposure)} />
        <StatCard
          label="Unrealized P&L"
          value={signed(totals.unrealized)}
          valueClass={pnlClass(totals.unrealized)}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <Card title="Holdings">
          {positionsLoading ? (
            <SkeletonRows rows={5} cols={6} />
          ) : !positions || positions.length === 0 ? (
            <EmptyState
              title="No holdings"
              body="Positions appear here once orders fill on your accounts."
            />
          ) : (
            <Table
              headers={["Symbol", "Side", "Qty", "Avg price", "Mark", "Market value", "Unreal. P&L"]}
            >
              {positions.map((position) => (
                <tr key={position.id}>
                  <Td className="font-medium">{position.symbol}</Td>
                  <Td>
                    <span
                      className={position.side === "long" ? "text-profit-500" : "text-loss-500"}
                    >
                      {position.side}
                    </span>
                  </Td>
                  <Td className="tabular-nums">{position.quantity}</Td>
                  <Td className="tabular-nums">{money(position.average_price)}</Td>
                  <Td className="tabular-nums">{money(position.last_mark)}</Td>
                  <Td className="tabular-nums">{money(position.market_value)}</Td>
                  <Td className={`tabular-nums ${pnlClass(position.unrealized_pnl)}`}>
                    {signed(position.unrealized_pnl)}
                  </Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>

        <Card title="Allocation by asset class" className="h-fit">
          {allocations.length === 0 ? (
            <EmptyState title="No allocation" body="Open positions drive allocation." />
          ) : (
            <ul className="space-y-3">
              {allocations.map((allocation) => (
                <li key={allocation.assetClass}>
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium">{allocation.assetClass}</span>
                    <span className="tabular-nums text-slate-500">
                      {allocation.pct.toFixed(1)}%
                    </span>
                  </div>
                  <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-surface-800">
                    <div
                      className="h-full rounded-full bg-accent-500"
                      style={{ width: `${allocation.pct}%` }}
                    />
                  </div>
                  <p className="mt-0.5 text-xs text-slate-400">{money(allocation.value)}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card className="mt-6" title="Accounts">
        {accountsLoading ? (
          <SkeletonRows rows={3} cols={5} />
        ) : !accounts || accounts.length === 0 ? (
          <EmptyState title="No accounts" body="Connect a broker to create trading accounts." />
        ) : (
          <Table headers={["Account", "Mode", "Currency", "Cash", "Equity", "Status"]}>
            {accounts.map((account) => (
              <tr key={account.id}>
                <Td className="font-medium">{account.name}</Td>
                <Td>
                  <Badge color={account.mode === "live" ? "red" : "blue"}>{account.mode}</Badge>
                </Td>
                <Td>{account.base_currency}</Td>
                <Td className="tabular-nums">{money(account.cash_balance, account.base_currency)}</Td>
                <Td className="tabular-nums">{money(account.equity, account.base_currency)}</Td>
                <Td>{account.status}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}
