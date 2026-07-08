import { useState } from "react";

import { Badge, Button, Field, Input, Modal, Select } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useAccounts, useInstruments, usePlaceOrder } from "@/lib/hooks";
import { toastError, toastSuccess } from "@/stores/toast";

export function OrderTicket({
  open,
  onClose,
  presetInstrumentId,
}: {
  open: boolean;
  onClose: () => void;
  presetInstrumentId?: string;
}) {
  const { data: accounts } = useAccounts();
  const [search, setSearch] = useState("");
  const { data: instruments } = useInstruments(search);
  const placeOrder = usePlaceOrder();

  const [accountId, setAccountId] = useState("");
  const [instrumentId, setInstrumentId] = useState(presetInstrumentId ?? "");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [orderType, setOrderType] = useState<"market" | "limit" | "stop" | "stop_limit">("market");
  const [quantity, setQuantity] = useState("1");
  const [limitPrice, setLimitPrice] = useState("");
  const [stopPrice, setStopPrice] = useState("");

  const activeAccounts = (accounts ?? []).filter((account) => account.status === "active");
  const effectiveAccount = accountId || activeAccounts[0]?.id || "";

  async function submit() {
    if (!effectiveAccount || !instrumentId) {
      toastError("Missing fields", "Select an account and instrument.");
      return;
    }
    try {
      const result = await placeOrder.mutateAsync({
        account_id: effectiveAccount,
        instrument_id: instrumentId,
        side,
        quantity,
        order_type: orderType,
        time_in_force: "day",
        limit_price: orderType === "limit" || orderType === "stop_limit" ? limitPrice : null,
        stop_price: orderType === "stop" || orderType === "stop_limit" ? stopPrice : null,
      });
      if (result.status === "rejected") {
        toastError("Order rejected", result.rejection_reason ?? undefined);
      } else {
        toastSuccess("Order placed", `Status: ${result.status}`);
        onClose();
      }
    } catch (error) {
      toastError("Order failed", error instanceof ApiError ? error.detail : undefined);
    }
  }

  const needsLimit = orderType === "limit" || orderType === "stop_limit";
  const needsStop = orderType === "stop" || orderType === "stop_limit";
  const account = activeAccounts.find((candidate) => candidate.id === effectiveAccount);

  return (
    <Modal open={open} onClose={onClose} title="Place order">
      <div className="space-y-4">
        {activeAccounts.length === 0 ? (
          <p className="text-sm text-slate-500">
            No active trading account. Connect a broker first.
          </p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => setSide("buy")}
                className={
                  side === "buy"
                    ? "rounded-lg bg-profit-600 py-2 text-sm font-medium text-white"
                    : "rounded-lg border border-slate-300 py-2 text-sm dark:border-surface-700"
                }
              >
                Buy
              </button>
              <button
                onClick={() => setSide("sell")}
                className={
                  side === "sell"
                    ? "rounded-lg bg-loss-600 py-2 text-sm font-medium text-white"
                    : "rounded-lg border border-slate-300 py-2 text-sm dark:border-surface-700"
                }
              >
                Sell
              </button>
            </div>

            <Field label="Account">
              <Select value={effectiveAccount} onChange={(event) => setAccountId(event.target.value)}>
                {activeAccounts.map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>
                    {candidate.name} ({candidate.mode})
                  </option>
                ))}
              </Select>
            </Field>

            {account?.mode === "live" && (
              <Badge color="red">Live account — this order routes to the venue</Badge>
            )}

            <Field label="Instrument">
              <Input
                placeholder="Search symbol…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
              <Select
                className="mt-2"
                value={instrumentId}
                onChange={(event) => setInstrumentId(event.target.value)}
              >
                <option value="">Select an instrument…</option>
                {(instruments ?? []).map((instrument) => (
                  <option key={instrument.id} value={instrument.id}>
                    {instrument.symbol} — {instrument.name}
                  </option>
                ))}
              </Select>
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Order type">
                <Select
                  value={orderType}
                  onChange={(event) =>
                    setOrderType(event.target.value as "market" | "limit" | "stop" | "stop_limit")
                  }
                >
                  <option value="market">Market</option>
                  <option value="limit">Limit</option>
                  <option value="stop">Stop</option>
                  <option value="stop_limit">Stop limit</option>
                </Select>
              </Field>
              <Field label="Quantity">
                <Input
                  type="number"
                  min="0"
                  step="any"
                  value={quantity}
                  onChange={(event) => setQuantity(event.target.value)}
                />
              </Field>
            </div>

            {(needsLimit || needsStop) && (
              <div className="grid grid-cols-2 gap-3">
                {needsLimit && (
                  <Field label="Limit price">
                    <Input
                      type="number"
                      step="any"
                      value={limitPrice}
                      onChange={(event) => setLimitPrice(event.target.value)}
                    />
                  </Field>
                )}
                {needsStop && (
                  <Field label="Stop price">
                    <Input
                      type="number"
                      step="any"
                      value={stopPrice}
                      onChange={(event) => setStopPrice(event.target.value)}
                    />
                  </Field>
                )}
              </div>
            )}

            <Button
              className="w-full"
              variant={side === "buy" ? "success" : "danger"}
              onClick={submit}
              loading={placeOrder.isPending}
            >
              {side === "buy" ? "Buy" : "Sell"} {quantity || "0"}
            </Button>
          </>
        )}
      </div>
    </Modal>
  );
}
