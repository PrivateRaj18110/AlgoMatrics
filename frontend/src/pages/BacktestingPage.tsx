import { useState } from "react";

import {
  Button,
  Card,
  Field,
  Input,
  PageHeader,
  Select,
  StatCard,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useRunBacktest, useSignalTypes, type BacktestBar } from "@/lib/hooks";
import { toastError } from "@/stores/toast";

const SAMPLE = "100,101,103,102,105,108,107,110,113,112,116,119,118,121,125,124,128,131";

function parseBars(text: string): BacktestBar[] {
  return text
    .split(/[\s,]+/)
    .map((t) => Number(t.trim()))
    .filter((n) => Number.isFinite(n) && n > 0)
    .map((price) => ({ open: price, high: price, low: price, close: price }));
}

export function BacktestingPage() {
  const { data: signalTypes } = useSignalTypes();
  const run = useRunBacktest();
  const [signalType, setSignalType] = useState("sma_crossover");
  const [fast, setFast] = useState("5");
  const [slow, setSlow] = useState("10");
  const [prices, setPrices] = useState(SAMPLE);
  const result = run.data;

  const onRun = () => {
    const bars = parseBars(prices);
    if (bars.length < 2) {
      toastError("Enter at least two prices");
      return;
    }
    run.mutate(
      { signal_type: signalType, params: { fast: Number(fast), slow: Number(slow) }, bars },
      { onError: (e) => toastError(e instanceof ApiError ? e.detail : "Backtest failed") },
    );
  };

  return (
    <div>
      <PageHeader
        title="Backtesting"
        description="Replay a price series through a strategy and score the result"
      />
      <Card>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Strategy type">
            <Select value={signalType} onChange={(e) => setSignalType(e.target.value)}>
              {(signalTypes ?? ["sma_crossover"]).map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Fast period">
            <Input type="number" value={fast} onChange={(e) => setFast(e.target.value)} />
          </Field>
          <Field label="Slow period">
            <Input type="number" value={slow} onChange={(e) => setSlow(e.target.value)} />
          </Field>
        </div>
        <div className="mt-3">
          <Field label="Price series (comma or space separated closes)">
            <textarea
              className="h-24 w-full rounded-lg border border-slate-300 bg-transparent p-2 text-sm dark:border-slate-700"
              value={prices}
              onChange={(e) => setPrices(e.target.value)}
            />
          </Field>
        </div>
        <div className="mt-4">
          <Button onClick={onRun} loading={run.isPending}>
            Run backtest
          </Button>
        </div>
      </Card>

      {result && (
        <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCard label="Total return" value={`${result.total_return_pct}%`} />
          <StatCard label="Max drawdown" value={`${result.max_drawdown_pct}%`} valueClass="text-loss-500" />
          <StatCard label="Sharpe" value={String(result.sharpe)} />
          <StatCard label="Sortino" value={String(result.sortino)} />
          <StatCard label="Calmar" value={String(result.calmar)} />
          <StatCard label="Annualized" value={`${result.annualized_return_pct}%`} />
          <StatCard label="Trades" value={String(result.trades)} />
          <StatCard label="Ending equity" value={result.ending_equity.toLocaleString()} />
        </div>
      )}
    </div>
  );
}
