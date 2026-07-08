import { useState } from "react";

import { OrderTicket } from "@/components/OrderTicket";
import {
  Button,
  Card,
  EmptyState,
  PageHeader,
  SkeletonRows,
  StatCard,
  Table,
  Td,
} from "@/components/ui";
import { usePositions } from "@/lib/hooks";
import { money, pnlClass, signed, toNumber } from "@/lib/format";

export function PositionsPage() {
  const { data: positions, isLoading } = usePositions();
  const [ticketOpen, setTicketOpen] = useState(false);
  const [presetInstrument, setPresetInstrument] = useState<string | undefined>();

  const totals = (positions ?? []).reduce(
    (acc, position) => {
      acc.unrealized += toNumber(position.unrealized_pnl);
      acc.realized += toNumber(position.realized_pnl);
      acc.exposure += toNumber(position.market_value);
      return acc;
    },
    { unrealized: 0, realized: 0, exposure: 0 },
  );

  return (
    <div>
      <PageHeader title="Positions" description="Open positions and running P&L" />

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Unrealized P&L"
          value={signed(totals.unrealized)}
          valueClass={pnlClass(totals.unrealized)}
        />
        <StatCard
          label="Realized P&L (all)"
          value={signed(totals.realized)}
          valueClass={pnlClass(totals.realized)}
        />
        <StatCard label="Gross exposure" value={money(totals.exposure)} />
      </div>

      <Card>
        {isLoading ? (
          <SkeletonRows rows={5} cols={8} />
        ) : !positions || positions.length === 0 ? (
          <EmptyState title="No open positions" body="Positions appear here once orders fill." />
        ) : (
          <Table
            headers={[
              "Symbol",
              "Side",
              "Qty",
              "Avg price",
              "Mark",
              "Market value",
              "Unreal. P&L",
              "Realized",
              "",
            ]}
          >
            {positions.map((position) => (
              <tr key={position.id}>
                <Td className="font-medium">{position.symbol}</Td>
                <Td>
                  <span className={position.side === "long" ? "text-profit-500" : "text-loss-500"}>
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
                <Td className={`tabular-nums ${pnlClass(position.realized_pnl)}`}>
                  {signed(position.realized_pnl)}
                </Td>
                <Td>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setPresetInstrument(position.instrument_id);
                      setTicketOpen(true);
                    }}
                  >
                    Trade
                  </Button>
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <OrderTicket
        open={ticketOpen}
        onClose={() => setTicketOpen(false)}
        presetInstrumentId={presetInstrument}
      />
    </div>
  );
}
