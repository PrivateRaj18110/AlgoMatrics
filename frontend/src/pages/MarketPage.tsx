import { useDeferredValue, useState } from "react";

import {
  Card,
  EmptyState,
  Input,
  PageHeader,
  SkeletonRows,
  StatCard,
  Table,
  Td,
} from "@/components/ui";
import { useMarketIndices, useMarketQuotes } from "@/lib/hooks";
import { money, pnlClass, signed, toNumber } from "@/lib/format";

/**
 * Indian market information: headline NSE/BSE indices and delayed NSE spot
 * quotes from a free public source. Indian market only — no forex.
 */
export function MarketPage() {
  const { data: indices } = useMarketIndices();
  const { data: quotes, isLoading: quotesLoading } = useMarketQuotes();
  const [filter, setFilter] = useState("");
  const deferredFilter = useDeferredValue(filter);

  const visible = (quotes ?? []).filter(
    (quote) =>
      !deferredFilter ||
      quote.symbol.toLowerCase().includes(deferredFilter.toLowerCase()) ||
      quote.name.toLowerCase().includes(deferredFilter.toLowerCase()),
  );

  return (
    <div>
      <PageHeader
        title="Market"
        description="Indian market snapshot — indices and delayed NSE quotes (refreshes every minute)"
        actions={
          <Input
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filter symbols…"
            aria-label="Filter symbols"
            className="w-48"
          />
        }
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {(indices ?? []).map((index) => {
          const changePct = index.change_pct ? toNumber(index.change_pct) : null;
          return (
            <StatCard
              key={index.yahoo_symbol}
              label={index.name}
              value={index.price ? money(index.price) : "—"}
              valueClass={changePct !== null ? pnlClass(changePct) : undefined}
              sub={
                changePct !== null
                  ? `${signed(toNumber(index.change ?? "0"))} (${changePct.toFixed(2)}%)`
                  : "unavailable"
              }
            />
          );
        })}
      </div>

      <Card>
        {quotesLoading && !quotes ? (
          <SkeletonRows rows={8} cols={5} />
        ) : visible.length === 0 ? (
          <EmptyState
            title="No quotes available"
            body="Quotes come from a free public source and may be briefly unavailable."
          />
        ) : (
          <Table headers={["Symbol", "Name", "Price", "Change", "Change %"]}>
            {visible.map((quote) => {
              const changePct = quote.change_pct ? toNumber(quote.change_pct) : null;
              return (
                <tr key={quote.yahoo_symbol}>
                  <Td className="font-medium">{quote.symbol}</Td>
                  <Td className="text-slate-500 dark:text-slate-400">{quote.name}</Td>
                  <Td className="tabular-nums">{quote.price ? money(quote.price) : "—"}</Td>
                  <Td className={`tabular-nums ${changePct !== null ? pnlClass(changePct) : ""}`}>
                    {quote.change ? signed(toNumber(quote.change)) : "—"}
                  </Td>
                  <Td className={`tabular-nums ${changePct !== null ? pnlClass(changePct) : ""}`}>
                    {changePct !== null ? `${changePct.toFixed(2)}%` : "—"}
                  </Td>
                </tr>
              );
            })}
          </Table>
        )}
      </Card>
    </div>
  );
}
