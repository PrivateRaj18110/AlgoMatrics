import { useState } from "react";

import { OrderTicket } from "@/components/OrderTicket";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  PageHeader,
  Select,
  SkeletonRows,
  Table,
  Td,
  statusColor,
} from "@/components/ui";
import { useCancelOrder, useOrders } from "@/lib/hooks";
import { dateTime, money } from "@/lib/format";
import { toastError, toastSuccess } from "@/stores/toast";
import { ApiError } from "@/lib/api";

const OPEN_STATES = new Set([
  "pending_risk",
  "approved",
  "submitted",
  "partially_filled",
  "cancel_pending",
]);

export function OrdersPage() {
  const [filter, setFilter] = useState<"all" | "open">("open");
  const [ticketOpen, setTicketOpen] = useState(false);
  const { data, isLoading } = useOrders(filter === "open" ? { open_only: true } : {});
  const cancelOrder = useCancelOrder();

  async function cancel(orderId: string) {
    try {
      await cancelOrder.mutateAsync(orderId);
      toastSuccess("Cancel requested");
    } catch (error) {
      toastError("Cancel failed", error instanceof ApiError ? error.detail : undefined);
    }
  }

  return (
    <div>
      <PageHeader
        title="Orders"
        description="All orders across your trading accounts"
        actions={
          <>
            <Select value={filter} onChange={(event) => setFilter(event.target.value as "all" | "open")}>
              <option value="open">Open orders</option>
              <option value="all">All orders</option>
            </Select>
            <Button onClick={() => setTicketOpen(true)}>New order</Button>
          </>
        }
      />

      <Card>
        {isLoading ? (
          <SkeletonRows rows={6} cols={7} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            title="No orders"
            body={filter === "open" ? "You have no open orders." : "No orders placed yet."}
            action={<Button onClick={() => setTicketOpen(true)}>Place an order</Button>}
          />
        ) : (
          <Table
            headers={["Symbol", "Side", "Type", "Qty", "Filled", "Avg price", "Status", "Placed", ""]}
          >
            {data.items.map((order) => (
              <tr key={order.id}>
                <Td className="font-medium">{order.symbol}</Td>
                <Td>
                  <span className={order.side === "buy" ? "text-profit-500" : "text-loss-500"}>
                    {order.side.toUpperCase()}
                  </span>
                </Td>
                <Td className="text-slate-500">{order.order_type}</Td>
                <Td className="tabular-nums">{order.quantity}</Td>
                <Td className="tabular-nums">{order.filled_quantity}</Td>
                <Td className="tabular-nums">{money(order.average_fill_price)}</Td>
                <Td>
                  <div className="flex flex-col gap-0.5">
                    <Badge color={statusColor(order.status)}>{order.status}</Badge>
                    {order.rejection_reason && (
                      <span className="text-[11px] text-loss-500">{order.rejection_reason}</span>
                    )}
                  </div>
                </Td>
                <Td className="text-xs text-slate-400">{dateTime(order.created_at)}</Td>
                <Td>
                  {OPEN_STATES.has(order.status) && order.status !== "cancel_pending" && (
                    <Button size="sm" variant="ghost" onClick={() => cancel(order.id)}>
                      Cancel
                    </Button>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <OrderTicket open={ticketOpen} onClose={() => setTicketOpen(false)} />
    </div>
  );
}
