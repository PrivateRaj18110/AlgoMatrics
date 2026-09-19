// AI-CIO · Track record: how the forecasts have graded — live every day and in
// the out-of-sample backtest — plus calibration and the model's actual weights.

import { clsx } from "clsx";
import { useMemo, useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Glyph } from "@/components/icons";
import { Badge, Button, Card, EmptyState, SkeletonRows, Table, Tabs, Td } from "@/components/ui";
import {
  type ForecastStage,
  type GradedDay,
  type PooledGrade,
  ratio,
  STAGE_LABEL,
  useMoversTrackRecord,
  useRunMoversJob,
} from "@/lib/movers";

import { Metric } from "./parts";

function Summary({ title, summary, note }: { title: string; summary: PooledGrade | undefined; note: string }) {
  const empty = !summary || summary.days === 0;
  return (
    <section className="rounded-2xl border border-slate-200 p-4 dark:border-white/[0.07]">
      <h3 className="text-sm font-semibold text-slate-900 dark:text-white">{title}</h3>
      <p className="mb-3 text-xs text-slate-500">{note}</p>
      {empty ? (
        <p className="text-xs text-slate-400">No graded sessions yet.</p>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Metric label="Top-10 hit rate" value={ratio(summary.precision)} hint={`${summary.hits} of ${summary.top_k_picks} picks`} />
          <Metric label="Base rate" value={ratio(summary.base_rate, 1)} hint="any stock, same day" />
          <Metric
            label="Lift"
            value={summary.lift ? `${summary.lift.toFixed(1)}×` : "—"}
            hint="vs picking at random"
            tone={summary.lift && summary.lift >= 1.5 ? "good" : summary.lift && summary.lift < 1 ? "bad" : undefined}
          />
          <Metric
            label="Direction right"
            value={ratio(summary.direction_accuracy)}
            hint={`${summary.direction_calls} calls on real movers`}
          />
        </div>
      )}
    </section>
  );
}

function DailyChart({ days }: { days: GradedDay[] }) {
  const data = days.map((day) => ({
    day: day.day.slice(5),
    hit: day.precision === null ? null : Math.round(day.precision * 100),
    base: day.base_rate === null ? null : Math.round(day.base_rate * 1000) / 10,
  }));
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid stroke="rgba(100,116,139,0.15)" vertical={false} />
          <XAxis dataKey="day" stroke="#64748b" fontSize={11} tickLine={false} minTickGap={20} />
          <YAxis stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} unit="%" domain={[0, 100]} />
          <Tooltip formatter={(value: number) => `${value}%`} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar dataKey="hit" name="Top-10 hit rate" fill="#22b8d4" radius={[3, 3, 0, 0]} isAnimationActive={false} />
          <Line dataKey="base" name="Base rate" stroke="#f59e0b" strokeWidth={2} dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TrackRecordTab({ isAdmin }: { isAdmin: boolean }) {
  const [stage, setStage] = useState<ForecastStage>("opening");
  const record = useMoversTrackRecord();
  const run = useRunMoversJob();
  const data = record.data;
  const features = useMemo(() => {
    const list = data?.model.features ?? [];
    return [...list].sort((a, b) => Math.abs(b.weight[stage]) - Math.abs(a.weight[stage]));
  }, [data, stage]);

  if (record.isLoading) return <SkeletonRows rows={6} cols={4} />;
  if (!data) {
    return (
      <Card>
        <EmptyState title="Track record unavailable" body="The grading service did not answer." />
      </Card>
    );
  }
  const backtest = data.backtest;
  const backtestStage = backtest?.stages[stage];
  const live = data.live[stage];
  const liveDays = live?.summary.days ?? 0;
  // One or two live days are too few to judge calibration; lean on the backtest until then.
  const liveCalibration = liveDays >= 10 && data.calibration.length > 0;
  const bands = liveCalibration ? data.calibration : (backtestStage?.calibration ?? data.calibration);
  const maxWeight = Math.max(0.5, ...features.map((f) => Math.max(Math.abs(f.weight[stage]), Math.abs(f.prior[stage]))));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs
          tabs={[
            { key: "opening", label: STAGE_LABEL.opening },
            { key: "overnight", label: STAGE_LABEL.overnight },
          ]}
          active={stage}
          onChange={(key) => setStage(key as ForecastStage)}
        />
        <p className="text-xs text-slate-500">
          A hit = a top-10 pick that closed at least {data.model.threshold_rule} from the previous close.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Summary
          title={liveDays ? `Live · ${liveDays} graded session${liveDays === 1 ? "" : "s"}` : "Live"}
          summary={live?.summary}
          note="Graded automatically at 16:15 IST every trading day (last 20 sessions pooled)."
        />
        <Summary
          title="Backtest · out of sample"
          summary={backtestStage?.fitted.summary}
          note={
            backtest?.test
              ? `Weights fitted on ${backtest.train?.[0]} → ${backtest.train?.[1]}, graded on ${backtest.test[0]} → ${backtest.test[1]} (unseen).`
              : "Runs automatically once after deploy (about 10 minutes)."
          }
        />
      </div>

      {backtestStage ? (
        <Card
          title="Backtest, day by day"
          subtitle={`Out-of-sample sessions · ${backtest?.filings.toLocaleString("en-IN")} real NSE filings replayed · starting weights scored ${ratio(backtestStage.prior.summary.precision)} on the same days`}
          icon={<Glyph name="chart" className="size-3.5" />}
          actions={
            isAdmin ? (
              <Button size="sm" variant="secondary" onClick={() => run.mutate("backtest")} loading={run.isPending}>
                Re-run backtest
              </Button>
            ) : undefined
          }
        >
          <DailyChart days={backtestStage.fitted.daily} />
          <ul className="mt-3 space-y-1 text-[11px] text-slate-500">
            {backtest?.limits.map((limit) => (
              <li key={limit}>· {limit}</li>
            ))}
          </ul>
        </Card>
      ) : null}

      {live && live.daily.length ? (
        <Card title="Live, day by day" icon={<Glyph name="pulse" className="size-3.5" />}>
          <DailyChart days={live.daily} />
        </Card>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Is a 30% really 30%?" subtitle="Calibration: forecast chance vs how often it happened" icon={<Glyph name="eye" className="size-3.5" />}>
          {bands.length === 0 ? (
            <p className="text-xs text-slate-400">Appears after the first graded sessions.</p>
          ) : (
            <Table headers={["Forecast band", "Stocks", "Forecast", "Happened"]} dense>
              {bands.map((band) => (
                <tr key={band.band}>
                  <Td dense className="font-data">{band.band}</Td>
                  <Td dense className="font-data tabular-nums">{band.count.toLocaleString("en-IN")}</Td>
                  <Td dense className="font-data tabular-nums">{ratio(band.predicted, 1)}</Td>
                  <Td dense className="font-data font-semibold tabular-nums">{ratio(band.actual, 1)}</Td>
                </tr>
              ))}
            </Table>
          )}
          <p className="mt-2 text-[11px] text-slate-500">
            {liveCalibration ? "From live grading." : "From the out-of-sample backtest until 10 live sessions are graded."} Close numbers in the last two columns mean the chances can be taken at face value.
          </p>
        </Card>

        <Card
          title="What the model weighs"
          subtitle={`${STAGE_LABEL[stage]} · ${data.model.source === "fitted" ? `fitted ${data.model.fitted_on ?? ""}` : "starting weights"} · log-odds per unit`}
          icon={<Glyph name="layers" className="size-3.5" />}
          actions={<Badge color={data.model.source === "fitted" ? "green" : "amber"}>{data.model.source === "fitted" ? "Learned" : "Prior"}</Badge>}
        >
          <ul className="space-y-2">
            {features
              .filter((feature) => stage === "opening" || !feature.opening_only)
              .map((feature) => {
                const weight = feature.weight[stage];
                const prior = feature.prior[stage];
                return (
                  <li key={feature.name} className="grid grid-cols-[minmax(0,1fr)_8rem_3rem] items-center gap-3 text-xs">
                    <span className="truncate text-slate-700 dark:text-slate-200" title={feature.label}>
                      {feature.label}
                    </span>
                    <div className="relative h-2 rounded-full bg-slate-100 dark:bg-white/[0.06]">
                      <div
                        className={clsx("absolute inset-y-0 left-0 rounded-full", weight >= 0 ? "bg-accent-500" : "bg-loss-500")}
                        style={{ width: `${(Math.abs(weight) / maxWeight) * 100}%` }}
                      />
                      <span
                        className="absolute -top-0.5 h-3 w-px bg-slate-500"
                        style={{ left: `${(Math.abs(prior) / maxWeight) * 100}%` }}
                        title={`Starting weight ${prior}`}
                      />
                    </div>
                    <span className="text-right font-data tabular-nums text-slate-600 dark:text-slate-300">{weight.toFixed(2)}</span>
                  </li>
                );
              })}
          </ul>
          <p className="mt-3 text-[11px] text-slate-500">
            Bar = current weight; tick = starting weight. Features with no history (news, open interest, ban list, deals) stay at their starting weight until live grades teach them.
          </p>
        </Card>
      </div>

      <p className="text-xs text-slate-500">{data.disclaimer}</p>
    </div>
  );
}
