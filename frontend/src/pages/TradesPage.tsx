import { Card, EmptyState, PageHeader, SkeletonRows, Table, Td } from "@/components/ui";
import { useTrades } from "@/lib/hooks";
import { dateTime, money } from "@/lib/format";

export function TradesPage() {
  const { data, isLoading } = useTrades();

  return (
    <div>
      <PageHeader title="Trades" description="Execution history (fills) across accounts" />
      <Card>
        {isLoading ? (
          <SkeletonRows rows={6} cols={6} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState title="No trades yet" body="Fills appear here as your orders execute." />
        ) : (
          <Table headers={["Symbol", "Side", "Qty", "Price", "Fee", "Executed"]}>
            {data.items.map((trade) => (
              <tr key={trade.id}>
                <Td className="font-medium">{trade.symbol}</Td>
                <Td>
                  <span className={trade.side === "buy" ? "text-profit-500" : "text-loss-500"}>
                    {trade.side.toUpperCase()}
                  </span>
                </Td>
                <Td className="tabular-nums">{trade.quantity}</Td>
                <Td className="tabular-nums">{money(trade.price)}</Td>
                <Td className="tabular-nums text-slate-500">{money(trade.fee, trade.fee_currency)}</Td>
                <Td className="text-xs text-slate-400">{dateTime(trade.executed_at)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}
