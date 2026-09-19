import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { money, toNumber } from "@/lib/format";

const AXIS = "#64748b";
const GRID = "rgba(100,116,139,0.12)";
const ACCENT = "#22b8d4";

const compactInr = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ value: number; name: string }>;
  label?: string;
  format?: (value: number) => string;
}

function ChartTooltip({ active, payload, label, format }: TooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-slate-200 bg-white/95 px-3 py-2 text-xs shadow-xl backdrop-blur dark:border-white/10 dark:bg-surface-900/95">
      <p className="mb-0.5 font-medium text-slate-500 dark:text-slate-400">{label}</p>
      {payload.map((entry) => (
        <p key={entry.name} className="font-semibold text-slate-900 tabular-nums dark:text-white">
          <span className="font-normal text-slate-500 dark:text-slate-400">{entry.name}: </span>
          {format ? format(entry.value) : entry.value.toLocaleString()}
        </p>
      ))}
    </div>
  );
}

export function EquityAreaChart({
  data,
  height = 260,
}: {
  data: Array<{ label: string; equity: number }>;
  /** Pixels, or "100%" to fill a parent that has a definite height. */
  height?: number | `${number}%`;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 10, right: 6, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={ACCENT} stopOpacity={0.32} />
            <stop offset="100%" stopColor={ACCENT} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} strokeDasharray="3 4" vertical={false} />
        <XAxis
          dataKey="label"
          stroke={AXIS}
          fontSize={11}
          tickLine={false}
          axisLine={false}
          minTickGap={40}
          dy={6}
        />
        <YAxis
          stroke={AXIS}
          fontSize={11}
          tickLine={false}
          axisLine={false}
          width={56}
          tickFormatter={(value: number) => `₹${compactInr.format(value)}`}
          domain={["auto", "auto"]}
        />
        <Tooltip
          content={<ChartTooltip format={(value) => money(value)} />}
          cursor={{ stroke: ACCENT, strokeOpacity: 0.35, strokeDasharray: "3 3" }}
        />
        <Area
          type="monotone"
          dataKey="equity"
          name="Equity"
          stroke={ACCENT}
          strokeWidth={2.25}
          fill="url(#equityGradient)"
          activeDot={{ r: 4, strokeWidth: 2, stroke: "#0b0f16", fill: ACCENT }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function PnlBarChart({
  data,
}: {
  data: Array<{ label: string; pnl: number }>;
}) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="label" stroke={AXIS} fontSize={11} tickLine={false} minTickGap={20} />
        <YAxis stroke={AXIS} fontSize={11} tickLine={false} axisLine={false} width={56} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: GRID }} />
        <Bar dataKey="pnl" name="Realized P&L" radius={[3, 3, 0, 0]}>
          {data.map((entry, index) => (
            <Cell key={index} fill={entry.pnl >= 0 ? "#10b981" : "#f43f5e"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function DrawdownChart({
  data,
}: {
  data: Array<{ label: string; drawdown: number }>;
}) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="ddGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f43f5e" stopOpacity={0.05} />
            <stop offset="100%" stopColor="#f43f5e" stopOpacity={0.35} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="label" stroke={AXIS} fontSize={11} tickLine={false} minTickGap={40} />
        <YAxis stroke={AXIS} fontSize={11} tickLine={false} axisLine={false} width={48} />
        <Tooltip content={<ChartTooltip />} />
        <Area
          type="monotone"
          dataKey="drawdown"
          name="Drawdown %"
          stroke="#f43f5e"
          strokeWidth={2}
          fill="url(#ddGradient)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function Sparkline({ points }: { points: number[] }) {
  const data = points.map((value, index) => ({ index, value }));
  const positive = points.length > 1 && points[points.length - 1] >= points[0];
  return (
    <ResponsiveContainer width="100%" height={40}>
      <LineChart data={data}>
        <Line
          type="monotone"
          dataKey="value"
          stroke={positive ? "#10b981" : "#f43f5e"}
          strokeWidth={1.5}
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function toChartNumber(value: string | number): number {
  return toNumber(value);
}
