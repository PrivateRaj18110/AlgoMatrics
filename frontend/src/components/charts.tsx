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

import { toNumber } from "@/lib/format";

const AXIS = "#64748b";
const GRID = "rgba(100,116,139,0.15)";

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ value: number; name: string }>;
  label?: string;
}

function ChartTooltip({ active, payload, label }: TooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg dark:border-surface-700 dark:bg-surface-900">
      <p className="font-medium text-slate-500">{label}</p>
      {payload.map((entry) => (
        <p key={entry.name} className="tabular-nums">
          {entry.name}: {entry.value.toLocaleString()}
        </p>
      ))}
    </div>
  );
}

export function EquityAreaChart({
  data,
}: {
  data: Array<{ label: string; equity: number }>;
}) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0ea5e9" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#0ea5e9" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="label" stroke={AXIS} fontSize={11} tickLine={false} minTickGap={40} />
        <YAxis
          stroke={AXIS}
          fontSize={11}
          tickLine={false}
          axisLine={false}
          width={64}
          tickFormatter={(value: number) => value.toLocaleString()}
          domain={["auto", "auto"]}
        />
        <Tooltip content={<ChartTooltip />} />
        <Area
          type="monotone"
          dataKey="equity"
          name="Equity"
          stroke="#0ea5e9"
          strokeWidth={2}
          fill="url(#equityGradient)"
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
