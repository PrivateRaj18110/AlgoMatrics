import { clsx } from "clsx";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  Badge,
  Card,
  EmptyState,
  Field,
  PageHeader,
  Select,
  SkeletonRows,
  Table,
  Td,
} from "@/components/ui";
import {
  useOpsAlerts,
  useOpsAnalytics,
  useOpsEvents,
  useOpsLogs,
  useOpsMachines,
  useOpsOrders,
  useOpsOverview,
  useOpsStrategies,
  useOpsSystemHealth,
  useOpsTrades,
} from "@/lib/hooks";
import { money, signed } from "@/lib/format";
import { formatHealthAge, formatInZone, formatTradingTime, formatUtcTime } from "@/lib/time";
import { unknownMs, unknownPercent } from "@/lib/unknown";

function Dash(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function TelemetryError() {
  return (
    <EmptyState
      title="Telemetry unavailable"
      body="The operations database is not configured or could not be reached. No demo data is shown."
    />
  );
}

function TimezoneCaption() {
  return (
    <p className="mb-3 text-xs text-slate-500">
      Event and trade clocks are stored as UTC. Display uses IANA zones: Asia/Kolkata (IST) and UTC. Offsets are never added by hand.
    </p>
  );
}

export function MachinesPage() {
  const { data, isLoading, isError } = useOpsMachines();
  return (
    <div>
      <PageHeader title="Machines" description="Hosts reported by Google telemetry" />
      <TimezoneCaption />
      <Card>
        {isLoading ? (
          <SkeletonRows rows={4} cols={6} />
        ) : isError ? (
          <TelemetryError />
        ) : !data?.length ? (
          <EmptyState title="Awaiting telemetry" body="No machines have reported a heartbeat yet." />
        ) : (
          <Table
            headers={["Machine", "Agent", "Status", "Heartbeat (IST)", "CPU", "RAM", "Queue", "Upload"]}
          >
            {data.map((row) => (
              <tr key={row.id}>
                <Td>{row.hostname || row.name || row.id}</Td>
                <Td>{Dash(row.agent_id)}</Td>
                <Td>{Dash(row.status)}</Td>
                <Td>{formatTradingTime(row.last_heartbeat)}</Td>
                <Td>{unknownPercent(row.cpu)}</Td>
                <Td>{unknownPercent(row.ram)}</Td>
                <Td>{Dash(row.queue_depth)}</Td>
                <Td>{formatTradingTime(row.last_successful_upload)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

export function EventsPage() {
  const [eventType, setEventType] = useState("");
  const { data, isLoading, isError } = useOpsEvents({ event_type: eventType || undefined });
  return (
    <div>
      <PageHeader title="Events" description="Categorized telemetry. Heartbeats are not trades." />
      <TimezoneCaption />
      <div className="mb-3 max-w-xs">
        <Field label="Event type">
          <Select value={eventType} onChange={(event) => setEventType(event.target.value)}>
            <option value="">All</option>
            <option value="heartbeat">heartbeat</option>
            <option value="system_status">system_status</option>
            <option value="strategy_status">strategy_status</option>
            <option value="order">order</option>
            <option value="trade">trade</option>
            <option value="trade_closed">trade_closed</option>
            <option value="alert">alert</option>
            <option value="error">error</option>
          </Select>
        </Field>
      </div>
      <Card>
        {isLoading ? (
          <SkeletonRows rows={6} cols={5} />
        ) : isError ? (
          <TelemetryError />
        ) : !data?.length ? (
          <EmptyState title="No data available" body="No events match these filters." />
        ) : (
          <Table headers={["Event time (IST)", "Received (UTC)", "Type", "Machine", "Strategy", "Symbol", "Message"]}>
            {data.map((row) => (
              <tr key={row.id}>
                <Td>{formatTradingTime(row.time)}</Td>
                <Td>{formatUtcTime(row.received_at)}</Td>
                <Td>{Dash(row.event_type)}</Td>
                <Td>{Dash(row.machine_id)}</Td>
                <Td>{Dash(row.strategy)}</Td>
                <Td>{Dash(row.symbol)}</Td>
                <Td>{Dash(row.message)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

export function ClosedTradesPage() {
  const { data, isLoading, isError } = useOpsTrades();
  return (
    <div>
      <PageHeader
        title="Closed Trades"
        description="Only explicit trade / trade_closed telemetry. Misclassified historical rows are excluded from this view, not deleted."
      />
      <TimezoneCaption />
      <Card>
        {isLoading ? (
          <SkeletonRows rows={6} cols={8} />
        ) : isError ? (
          <TelemetryError />
        ) : !data?.length ? (
          <EmptyState title="No data available" body="No explicit closed trades have been ingested." />
        ) : (
          <Table
            headers={[
              "Time (IST)",
              "Strategy",
              "Machine",
              "Symbol",
              "Side",
              "Entry",
              "Exit",
              "Qty",
              "PnL",
              "Latency",
            ]}
          >
            {data.map((row) => (
              <tr key={row.id}>
                <Td>{formatTradingTime(row.time)}</Td>
                <Td>{Dash(row.strategy)}</Td>
                <Td>{Dash(row.machine)}</Td>
                <Td>{Dash(row.symbol)}</Td>
                <Td>{Dash(row.direction)}</Td>
                <Td>{Dash(row.entry)}</Td>
                <Td>{Dash(row.exit)}</Td>
                <Td>{Dash(row.quantity)}</Td>
                <Td>{row.pnl === null || row.pnl === undefined ? "—" : signed(row.pnl)}</Td>
                <Td>{unknownMs(row.latency_ms)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

export function EngineOrdersPage() {
  const { data, isLoading, isError } = useOpsOrders();
  return (
    <div>
      <PageHeader title="Execution" description="Order events from Google telemetry. Missing fields stay unknown." />
      <TimezoneCaption />
      <Card>
        {isLoading ? (
          <SkeletonRows rows={5} cols={5} />
        ) : isError ? (
          <TelemetryError />
        ) : !data?.length ? (
          <EmptyState title="Awaiting telemetry" body="No order events have been reported." />
        ) : (
          <Table headers={["Time (IST)", "Type", "Strategy", "Symbol", "Machine", "Summary"]}>
            {data.map((row) => (
              <tr key={row.id}>
                <Td>{formatTradingTime(row.time)}</Td>
                <Td>{Dash(row.event_type)}</Td>
                <Td>{Dash(row.strategy)}</Td>
                <Td>{Dash(row.symbol)}</Td>
                <Td>{Dash(row.machine_id)}</Td>
                <Td>{Dash(row.payload_summary || row.message)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

export function LogsPage() {
  const { data, isLoading, isError } = useOpsLogs();
  return (
    <div>
      <PageHeader title="Logs" description="Agent and system logs from telemetry" />
      <TimezoneCaption />
      <Card>
        {isLoading ? (
          <SkeletonRows rows={5} cols={4} />
        ) : isError ? (
          <TelemetryError />
        ) : !data?.length ? (
          <EmptyState title="No data available" />
        ) : (
          <Table headers={["Time (IST)", "Level", "Source", "Message"]}>
            {data.map((row) => (
              <tr key={row.id}>
                <Td>{formatTradingTime(row.time)}</Td>
                <Td>{Dash(row.level)}</Td>
                <Td>{Dash(row.source)}</Td>
                <Td>{Dash(row.message)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

export function TelemetryAlertsPage() {
  const { data, isLoading, isError } = useOpsAlerts();
  return (
    <div>
      <PageHeader title="Alerts" description="Critical telemetry and error events" />
      <TimezoneCaption />
      <Card>
        {isLoading ? (
          <SkeletonRows rows={4} cols={4} />
        ) : isError ? (
          <TelemetryError />
        ) : !data?.length ? (
          <EmptyState title="No data available" body="No alerts have been reported." />
        ) : (
          <Table headers={["Time (IST)", "Severity", "Type", "Message"]}>
            {data.map((row) => (
              <tr key={row.id}>
                <Td>{formatTradingTime(row.time)}</Td>
                <Td>{Dash(row.severity)}</Td>
                <Td>{Dash(row.event_type)}</Td>
                <Td>{Dash(row.message)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

export function EngineStrategiesPage() {
  const { data, isLoading, isError } = useOpsStrategies();
  return (
    <div>
      <PageHeader
        title="Engine strategies"
        description="Identities reported by Google telemetry. Names are never invented."
      />
      <TimezoneCaption />
      <Card>
        {isLoading ? (
          <SkeletonRows rows={4} cols={6} />
        ) : isError ? (
          <TelemetryError />
        ) : !data?.length ? (
          <EmptyState title="No strategy data available" body="No strategy_status or trade strategy names have arrived." />
        ) : (
          <Table
            headers={["Strategy", "Machine", "Status", "Trades", "PnL", "Win rate", "Latency", "Symbols"]}
          >
            {data.map((row) => (
              <tr key={row.strategy_id}>
                <Td>
                  <Link className="text-brand-600" to={`/app/engine-strategies/${encodeURIComponent(row.strategy_name)}`}>
                    {row.strategy_name}
                  </Link>
                </Td>
                <Td>{Dash(row.machine_id)}</Td>
                <Td>{Dash(row.status)}</Td>
                <Td>{Dash(row.trade_count)}</Td>
                <Td>{row.total_pnl === null || row.total_pnl === undefined ? "—" : signed(row.total_pnl)}</Td>
                <Td>{row.win_rate === null || row.win_rate === undefined ? "—" : unknownPercent(row.win_rate * 100)}</Td>
                <Td>{unknownMs(row.avg_latency_ms)}</Td>
                <Td>{row.symbols?.length ? row.symbols.join(", ") : "—"}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

export function EngineStrategySymbolsRoute() {
  const { strategyName } = useParams();
  const name = strategyName ? decodeURIComponent(strategyName) : "";
  if (!name) {
    return <EmptyState title="Unknown" body="Strategy identity is missing from the URL." />;
  }
  return <EngineStrategySymbolsPage strategyName={name} />;
}

function EngineStrategySymbolsPage({ strategyName }: { strategyName: string }) {
  const { data, isLoading, isError } = useOpsAnalytics(strategyName);
  const symbols = data?.symbols ?? [];
  return (
    <div>
      <PageHeader
        title={strategyName}
        description="Symbols and option metadata only when present in the telemetry symbol string."
      />
      <TimezoneCaption />
      <Card>
        {isLoading ? (
          <SkeletonRows rows={4} cols={6} />
        ) : isError ? (
          <TelemetryError />
        ) : !symbols.length ? (
          <EmptyState title="No data available" body="This strategy has no symbol-attributed trades yet." />
        ) : (
          <Table
            headers={[
              "Symbol",
              "Underlying",
              "Expiry",
              "Strike",
              "CE/PE",
              "Trades",
              "PnL",
              "Win rate",
            ]}
          >
            {symbols.map((row) => (
              <tr key={`${row.strategy_name}-${row.symbol}`}>
                <Td>{row.symbol}</Td>
                <Td>{Dash(row.underlying)}</Td>
                <Td>{Dash(row.expiry)}</Td>
                <Td>{Dash(row.strike)}</Td>
                <Td>{Dash(row.option_type)}</Td>
                <Td>{Dash(row.trade_count)}</Td>
                <Td>{row.pnl === null || row.pnl === undefined ? "—" : signed(row.pnl)}</Td>
                <Td>
                  {row.win_rate === null || row.win_rate === undefined
                    ? "—"
                    : unknownPercent(row.win_rate * 100)}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

export function EngineAnalyticsPage() {
  const { data, isLoading, isError } = useOpsAnalytics();
  return (
    <div>
      <PageHeader title="Engine analytics" description="Aggregated only from real Google trades and strategy_status." />
      <TimezoneCaption />
      <EngineStrategiesPage />
      <div className="mt-4">
        <Card>
          {isLoading ? (
            <SkeletonRows rows={4} cols={5} />
          ) : isError ? (
            <TelemetryError />
          ) : !data?.symbols?.length ? (
            <EmptyState title="No data available" body="Symbol drill-down appears when trades include a symbol." />
          ) : (
            <Table headers={["Strategy", "Symbol", "Instrument", "PnL", "Trades"]}>
              {data.symbols.map((row) => (
                <tr key={`${row.strategy_name}-${row.symbol}`}>
                  <Td>{row.strategy_name}</Td>
                  <Td>{row.symbol}</Td>
                  <Td>
                    {row.metadata_available
                      ? [row.instrument, row.option_type, row.strike].filter(Boolean).join(" ")
                      : "Not reported"}
                  </Td>
                  <Td>{row.pnl === null || row.pnl === undefined ? "—" : money(row.pnl)}</Td>
                  <Td>{Dash(row.trade_count)}</Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </div>
      <div className="mt-4">
        <Card>
          {!data?.by_symbol?.length ? (
            <EmptyState title="No data available" body="Symbol → strategy breakdown appears when the same symbol trades under more than one strategy name." />
          ) : (
            <Table headers={["Symbol", "Strategy", "Trades", "PnL", "Win rate"]}>
              {data.by_symbol.map((row) => (
                <tr key={`by-symbol-${row.symbol}-${row.strategy_name}`}>
                  <Td>{row.symbol}</Td>
                  <Td>{row.strategy_name}</Td>
                  <Td>{Dash(row.trade_count)}</Td>
                  <Td>{row.pnl === null || row.pnl === undefined ? "—" : money(row.pnl)}</Td>
                  <Td>
                    {row.win_rate === null || row.win_rate === undefined
                      ? "—"
                      : unknownPercent(row.win_rate * 100)}
                  </Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </div>
    </div>
  );
}

export function OpsOverviewStrip() {
  const { data } = useOpsOverview();
  if (!data) return null;
  if (data.awaiting_telemetry) {
    return (
      <Card className="mt-4">
        <EmptyState
          title="Awaiting telemetry"
          body="Google machines and closed trades will appear here when ingest is live."
        />
      </Card>
    );
  }
  const onlineCount = data.online_machines ?? 0;
  return (
    <div className="mt-4 grid gap-4 sm:grid-cols-3">
      <Card>
        <p className="text-xs text-slate-500">Registered machines</p>
        <p className="text-xl font-semibold">{Dash(data.machine_count)}</p>
        <p className="mt-1 text-xs text-slate-400">
          {onlineCount > 0 ? `${onlineCount} online` : "Execution offline"}
        </p>
      </Card>
      <Card>
        <p className="text-xs text-slate-500">Recorded closed trades</p>
        <p className="text-xl font-semibold">{Dash(data.closed_trade_count)}</p>
        <p className="mt-1 text-xs text-slate-400">Classified telemetry</p>
      </Card>
      <Card>
        <p className="text-xs text-slate-500">Historical Engine PnL</p>
        <p className="text-xl font-semibold">
          {data.total_pnl === null || data.total_pnl === undefined ? "—" : signed(data.total_pnl)}
        </p>
        <p className="mt-1 text-xs text-slate-400">Cumulative closed trades</p>
      </Card>
    </div>
  );
}

interface ChartTooltipProps {
  active?: boolean;
  payload?: Array<{ value: number; name: string; color?: string }>;
  label?: string;
}

function ChartTooltip({ active, payload, label }: ChartTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg dark:border-surface-700 dark:bg-surface-900">
      <p className="font-medium text-slate-500">{label}</p>
      {payload.map((entry) => (
        <p key={entry.name} className="tabular-nums" style={{ color: entry.color }}>
          {entry.name}: {typeof entry.value === "number" ? entry.value.toLocaleString() : entry.value}
        </p>
      ))}
    </div>
  );
}

type HealthTimeRange = "15m" | "30m" | "1h" | "3h" | "6h" | "24h";

const HEALTH_TIME_RANGES: { label: string; value: HealthTimeRange; ms: number }[] = [
  { label: "15 minutes", value: "15m", ms: 15 * 60 * 1000 },
  { label: "30 minutes", value: "30m", ms: 30 * 60 * 1000 },
  { label: "1 hour", value: "1h", ms: 60 * 60 * 1000 },
  { label: "3 hours", value: "3h", ms: 3 * 60 * 60 * 1000 },
  { label: "6 hours", value: "6h", ms: 6 * 60 * 60 * 1000 },
  { label: "24 hours", value: "24h", ms: 24 * 60 * 60 * 1000 },
];

function HealthMetricCard({
  title,
  value,
  unit = "",
  trend,
  timestamp,
  status,
  statusColor = "slate",
}: {
  title: string;
  value: string | number | null | undefined;
  unit?: string;
  trend?: string | null;
  timestamp?: string | null;
  status?: string;
  statusColor?: "green" | "amber" | "red" | "slate" | "blue" | "violet";
}) {
  const displayVal =
    value !== null && value !== undefined && value !== ""
      ? `${value}${unit ? " " + unit : ""}`
      : "—";

  return (
    <Card className="flex flex-col justify-between">
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-medium text-slate-500">{title}</span>
        {status && <Badge color={statusColor}>{status}</Badge>}
      </div>
      <div className="my-2">
        <p className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white tabular-nums">
          {displayVal}
        </p>
        {trend && <p className="mt-0.5 text-xs text-slate-400">{trend}</p>}
      </div>
      <div className="border-t border-slate-100 pt-2 dark:border-surface-800 text-[11px] text-slate-400 flex items-center justify-between">
        <span>{timestamp ? `${timestamp}` : "No timestamp"}</span>
      </div>
    </Card>
  );
}

function getRangeStartTime(rangeMs: number): string {
  return new Date(Date.now() - rangeMs).toISOString();
}

export function SystemHealthPage({ region: _region }: { region?: string } = {}) {
  const { data: machines } = useOpsMachines();
  const validMachines = useMemo(() => {
    if (!machines) return [];
    return machines.filter(
      (m) =>
        m.id &&
        !["mch-london", "mch-gcloud", "mch-pc"].includes(m.id) &&
        !["London VPS", "Personal Computer"].includes(m.name)
    );
  }, [machines]);

  const [selectedMid, setSelectedMid] = useState<string>("");
  const [range, setRange] = useState<HealthTimeRange>("30m");
  const [startTime, setStartTime] = useState<string>(() => getRangeStartTime(30 * 60 * 1000));

  const handleRangeChange = (newRange: HealthTimeRange) => {
    setRange(newRange);
    const cfg = HEALTH_TIME_RANGES.find((r) => r.value === newRange) || HEALTH_TIME_RANGES[1];
    setStartTime(getRangeStartTime(cfg.ms));
  };

  const selectedRangeConfig =
    HEALTH_TIME_RANGES.find((r) => r.value === range) || HEALTH_TIME_RANGES[1];

  const activeMid = useMemo(() => {
    if (selectedMid && validMachines.some((m) => m.id === selectedMid)) {
      return selectedMid;
    }
    const google = validMachines.find(
      (m) =>
        m.id === "mch-agent-google-vm-raj-quant-server" ||
        m.name === "google-vm-raj-quant-server"
    );
    if (google) return google.id;
    return validMachines[0]?.id || "";
  }, [selectedMid, validMachines]);

  const selectedMachineObj = useMemo(() => {
    return validMachines.find((m) => m.id === activeMid);
  }, [validMachines, activeMid]);

  const { data: healthData, isLoading: healthLoading, isError } = useOpsSystemHealth({
    machine_id: activeMid || undefined,
    start: startTime,
    limit: 500,
  });

  const healthPoints = healthData?.points;

  const chartData = useMemo(() => {
    if (!healthPoints) return [];
    return healthPoints.map((pt) => ({
      time: pt.timestamp,
      label: formatInZone(pt.timestamp, "Asia/Kolkata", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
        ...(range === "24h" ? { month: "short", day: "numeric" } : {}),
      }),
      cpu: pt.cpu_usage_pct,
      memory: pt.memory_mb,
      tick_rate: pt.tick_rate,
      tick_delay: pt.tick_delay_ms,
      avg_latency: pt.avg_latency_ms,
      p95_latency: pt.p95_latency_ms,
      p99_latency: pt.p99_latency_ms,
      queue_size: pt.queue_size,
      queue_wait: pt.queue_wait_ms,
      api_success: pt.api_success_pct,
      signal_fill: pt.signal_fill_rate_pct,
      status: pt.status,
    }));
  }, [healthPoints, range]);

  const points = healthData?.points || [];
  const latest = points.length > 0 ? points[points.length - 1] : null;
  const prior = points.length > 1 ? points[points.length - 2] : null;

  const isLive = healthData?.is_live ?? false;
  const execStatus = healthData?.current_execution_status ?? "offline";
  const rawHealthStatus = healthData?.current_health_status;
  const lastHealthTimestamp = healthData?.last_health_timestamp;
  const lastHeartbeat = selectedMachineObj?.last_heartbeat;

  const authoritativeStatus = useMemo(() => {
    if (!healthData?.points || healthData.points.length === 0) {
      return execStatus === "offline" ? "OFFLINE" : "NO DATA";
    }
    if (rawHealthStatus) return rawHealthStatus.toUpperCase();
    if (execStatus === "offline") return "OFFLINE";
    return "STABLE";
  }, [healthData?.points, rawHealthStatus, execStatus]);

  const healthAgeText = useMemo(() => {
    return formatHealthAge(lastHealthTimestamp);
  }, [lastHealthTimestamp]);

  const latestTimeStr = useMemo(() => {
    if (!latest?.timestamp) return null;
    return (
      formatInZone(latest.timestamp, "Asia/Kolkata", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      }) + " IST"
    );
  }, [latest]);

  const hasAnyTelemetry = Boolean(latest || healthData?.last_health_timestamp);

  return (
    <div className="space-y-6">
      <PageHeader
        title="System Health"
        description="Live execution infrastructure and strategy health"
      />
      <TimezoneCaption />

      {/* Machine Selector & Time Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <label htmlFor="health-machine-select" className="text-xs font-medium text-slate-500">
            Machine:
          </label>
          <select
            id="health-machine-select"
            value={activeMid}
            onChange={(e) => setSelectedMid(e.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition-colors focus:border-accent-500 focus:outline-none dark:border-surface-700 dark:bg-surface-850 dark:text-slate-200"
          >
            {validMachines.map((m) => (
              <option key={m.id} value={m.id}>
                {m.hostname || m.name || m.id} ({m.status})
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-100 p-1 dark:border-surface-700 dark:bg-surface-900">
          {HEALTH_TIME_RANGES.map((r) => (
            <button
              key={r.value}
              type="button"
              onClick={() => handleRangeChange(r.value)}
              className={clsx(
                "rounded px-2.5 py-1 text-xs font-medium transition-colors",
                range === r.value
                  ? "bg-white text-slate-900 shadow-sm dark:bg-surface-800 dark:text-white"
                  : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
              )}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* Prominent Machine & Health Status Header Card */}
      <Card>
        <div className="grid gap-4 sm:grid-cols-4">
          <div>
            <p className="text-xs text-slate-500">Execution Machine</p>
            <p className="mt-1 font-semibold text-slate-900 dark:text-white">
              {healthData?.machine_name || selectedMachineObj?.name || activeMid || "—"}
            </p>
            <div className="mt-1 flex items-center gap-1.5">
              <span
                className={clsx(
                  "inline-block h-2 w-2 rounded-full",
                  isLive
                    ? "bg-emerald-500 animate-pulse"
                    : execStatus === "online"
                    ? "bg-emerald-500"
                    : "bg-slate-400"
                )}
              />
              <span className="text-xs font-medium text-slate-500">
                {isLive
                  ? "LIVE"
                  : execStatus === "offline" && hasAnyTelemetry
                  ? "HISTORICAL"
                  : execStatus === "offline"
                  ? "OFFLINE"
                  : "NO DATA"}
              </span>
            </div>
          </div>

          <div>
            <p className="text-xs text-slate-500">Status</p>
            <div className="mt-1 flex items-center gap-1.5">
              <span
                className={clsx(
                  "inline-block h-2 w-2 rounded-full",
                  execStatus === "online" ? "bg-emerald-500" : "bg-slate-400"
                )}
              />
              <span className="text-sm font-semibold uppercase text-slate-900 dark:text-white">
                {execStatus.toUpperCase()}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-400">
              {lastHeartbeat
                ? `Last heartbeat: ${formatTradingTime(lastHeartbeat)}`
                : "No heartbeat received"}
            </p>
          </div>

          <div>
            <p className="text-xs text-slate-500">Health State</p>
            <div className="mt-1">
              <Badge
                color={
                  authoritativeStatus === "STABLE"
                    ? "green"
                    : authoritativeStatus === "DEGRADED"
                    ? "amber"
                    : authoritativeStatus === "UNSTABLE" || authoritativeStatus === "CRITICAL"
                    ? "red"
                    : "slate"
                }
              >
                {authoritativeStatus}
              </Badge>
            </div>
            <p className="mt-1 text-xs text-slate-400">Authoritative status</p>
          </div>

          <div>
            <p className="text-xs text-slate-500">
              {execStatus === "offline" ? "Last health" : "Last update"}
            </p>
            <p className="mt-1 text-sm font-medium text-slate-700 dark:text-slate-300">
              {lastHealthTimestamp ? formatTradingTime(lastHealthTimestamp) : "—"}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              {lastHealthTimestamp ? `Health age: ${healthAgeText}` : "Asia/Kolkata timezone"}
            </p>
          </div>
        </div>

        {/* Offline Notice Banner */}
        {execStatus === "offline" && hasAnyTelemetry && (
          <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600 dark:border-surface-700 dark:bg-surface-900 dark:text-slate-300">
            <span className="font-semibold text-slate-700 dark:text-slate-200">
              Execution VM offline.
            </span>{" "}
            Displaying historical health data through{" "}
            <span className="font-medium text-slate-900 dark:text-white">
              {lastHealthTimestamp ? formatTradingTime(lastHealthTimestamp) : "last recorded snapshot"}
            </span>
            . No continuous telemetry is streaming.
          </div>
        )}
      </Card>

      {/* Health Loading / Error / Empty State Check */}
      {healthLoading ? (
        <Card>
          <SkeletonRows rows={8} cols={4} />
        </Card>
      ) : isError ? (
        <TelemetryError />
      ) : !hasAnyTelemetry ? (
        <Card>
          <EmptyState
            title="No system health telemetry yet."
            body="The execution VM has not submitted a system_health snapshot. Production never renders mock data."
          />
        </Card>
      ) : (
        <>
          {/* Section: 11 Health Summary Cards */}
          <div>
            <h3 className="mb-3 text-sm font-semibold text-slate-900 dark:text-white">
              Health Metrics Summary
            </h3>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
              {/* 1. CPU Usage */}
              <HealthMetricCard
                title="CPU Usage"
                value={latest ? latest.cpu_usage_pct.toFixed(1) : null}
                unit="%"
                status={
                  !latest
                    ? "No data"
                    : latest.cpu_usage_pct < 70
                    ? "Healthy"
                    : latest.cpu_usage_pct < 90
                    ? "Warning"
                    : "Critical"
                }
                statusColor={
                  !latest
                    ? "slate"
                    : latest.cpu_usage_pct < 70
                    ? "green"
                    : latest.cpu_usage_pct < 90
                    ? "amber"
                    : "red"
                }
                trend={
                  latest && prior
                    ? `${latest.cpu_usage_pct >= prior.cpu_usage_pct ? "+" : ""}${(
                        latest.cpu_usage_pct - prior.cpu_usage_pct
                      ).toFixed(1)}% vs prev`
                    : "Current snapshot"
                }
                timestamp={latestTimeStr}
              />

              {/* 2. Memory */}
              <HealthMetricCard
                title="Memory"
                value={latest ? Math.round(latest.memory_mb) : null}
                unit="MB"
                status={!latest ? "No data" : "Nominal"}
                statusColor="slate"
                trend={
                  latest && prior
                    ? `${latest.memory_mb >= prior.memory_mb ? "+" : ""}${Math.round(
                        latest.memory_mb - prior.memory_mb
                      )} MB vs prev`
                    : "RAM allocation"
                }
                timestamp={latestTimeStr}
              />

              {/* 3. Tick Rate */}
              <HealthMetricCard
                title="Tick Rate"
                value={latest ? latest.tick_rate.toFixed(1) : null}
                unit="/s"
                status={!latest ? "No data" : latest.tick_rate > 0 ? "Feed active" : "Idle"}
                statusColor={!latest ? "slate" : latest.tick_rate > 0 ? "green" : "amber"}
                trend={
                  latest && prior
                    ? `${latest.tick_rate >= prior.tick_rate ? "+" : ""}${(
                        latest.tick_rate - prior.tick_rate
                      ).toFixed(1)} /s vs prev`
                    : "Market ticks"
                }
                timestamp={latestTimeStr}
              />

              {/* 4. Tick Delay */}
              <HealthMetricCard
                title="Tick Delay"
                value={latest ? latest.tick_delay_ms.toFixed(2) : null}
                unit="ms"
                status={!latest ? "No data" : latest.tick_delay_ms < 5 ? "Low delay" : "Elevated"}
                statusColor={!latest ? "slate" : latest.tick_delay_ms < 5 ? "green" : "amber"}
                trend={
                  latest && prior
                    ? `${latest.tick_delay_ms >= prior.tick_delay_ms ? "+" : ""}${(
                        latest.tick_delay_ms - prior.tick_delay_ms
                      ).toFixed(2)} ms vs prev`
                    : "Feed latency"
                }
                timestamp={latestTimeStr}
              />

              {/* 5. Queue Size */}
              <HealthMetricCard
                title="Queue Size"
                value={latest ? latest.queue_size : null}
                status={!latest ? "No data" : latest.queue_size === 0 ? "Optimal" : "Buffering"}
                statusColor={!latest ? "slate" : latest.queue_size === 0 ? "green" : "amber"}
                trend="Internal queue depth"
                timestamp={latestTimeStr}
              />

              {/* 6. Queue Wait */}
              <HealthMetricCard
                title="Queue Wait"
                value={latest ? latest.queue_wait_ms.toFixed(2) : null}
                unit="ms"
                status={!latest ? "No data" : latest.queue_wait_ms < 5 ? "Nominal" : "Elevated"}
                statusColor={!latest ? "slate" : latest.queue_wait_ms < 5 ? "green" : "amber"}
                trend={
                  latest && prior
                    ? `${latest.queue_wait_ms >= prior.queue_wait_ms ? "+" : ""}${(
                        latest.queue_wait_ms - prior.queue_wait_ms
                      ).toFixed(2)} ms vs prev`
                    : "Dispatch latency"
                }
                timestamp={latestTimeStr}
              />

              {/* 7. Avg Latency */}
              <HealthMetricCard
                title="Avg Latency"
                value={latest ? latest.avg_latency_ms.toFixed(2) : null}
                unit="ms"
                status={!latest ? "No data" : latest.avg_latency_ms < 10 ? "Fast" : "Elevated"}
                statusColor={!latest ? "slate" : latest.avg_latency_ms < 10 ? "green" : "amber"}
                trend={
                  latest && prior
                    ? `${latest.avg_latency_ms >= prior.avg_latency_ms ? "+" : ""}${(
                        latest.avg_latency_ms - prior.avg_latency_ms
                      ).toFixed(2)} ms vs prev`
                    : "Route average"
                }
                timestamp={latestTimeStr}
              />

              {/* 8. P95 Latency */}
              <HealthMetricCard
                title="P95 Latency"
                value={latest ? latest.p95_latency_ms.toFixed(2) : null}
                unit="ms"
                status={!latest ? "No data" : latest.p95_latency_ms < 20 ? "Nominal" : "High"}
                statusColor={!latest ? "slate" : latest.p95_latency_ms < 20 ? "green" : "amber"}
                trend="95th percentile"
                timestamp={latestTimeStr}
              />

              {/* 9. P99 Latency */}
              <HealthMetricCard
                title="P99 Latency"
                value={latest ? latest.p99_latency_ms.toFixed(2) : null}
                unit="ms"
                status={!latest ? "No data" : latest.p99_latency_ms < 50 ? "Nominal" : "Tail delay"}
                statusColor={!latest ? "slate" : latest.p99_latency_ms < 50 ? "green" : "red"}
                trend="99th percentile tail"
                timestamp={latestTimeStr}
              />

              {/* 10. API Success */}
              <HealthMetricCard
                title="API Success"
                value={latest ? latest.api_success_pct.toFixed(1) : null}
                unit="%"
                status={!latest ? "No data" : latest.api_success_pct >= 99 ? "Healthy" : "Degraded"}
                statusColor={!latest ? "slate" : latest.api_success_pct >= 99 ? "green" : "red"}
                trend="HTTP/WS reliability"
                timestamp={latestTimeStr}
              />

              {/* 11. Signal Fill Rate */}
              <HealthMetricCard
                title="Signal Fill Rate"
                value={latest ? latest.signal_fill_rate_pct.toFixed(1) : null}
                unit="%"
                status={!latest ? "No data" : latest.signal_fill_rate_pct >= 95 ? "Nominal" : "Partial"}
                statusColor={!latest ? "slate" : latest.signal_fill_rate_pct >= 95 ? "green" : "amber"}
                trend="Signal conversion"
                timestamp={latestTimeStr}
              />
            </div>
          </div>

          {/* Section: Time-Series Graphs */}
          {!chartData.length ? (
            <Card>
              <EmptyState
                title="No health telemetry available for this period."
                body={`No snapshots found within the selected ${selectedRangeConfig.label} window. Try choosing a longer time window above.`}
              />
            </Card>
          ) : (
            <div className="grid gap-6 lg:grid-cols-2">
              {/* Chart A: Tick / Feed Health */}
              <Card>
                <div className="mb-2 flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-medium text-slate-900 dark:text-white">
                      Tick / Feed Health
                    </h3>
                    <p className="text-xs text-slate-400">Market quote feed tick rate and arrival delay</p>
                  </div>
                  <span className="text-xs font-mono text-slate-400">Ticks/sec · ms</span>
                </div>
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="rgba(100,116,139,0.15)" vertical={false} />
                    <XAxis dataKey="label" stroke="#64748b" fontSize={11} tickLine={false} minTickGap={30} />
                    <YAxis yAxisId="rate" stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} width={45} unit="/s" />
                    <YAxis
                      yAxisId="delay"
                      orientation="right"
                      stroke="#64748b"
                      fontSize={11}
                      tickLine={false}
                      axisLine={false}
                      width={45}
                      unit="ms"
                    />
                    <Tooltip content={<ChartTooltip />} />
                    <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }} />
                    <Line
                      yAxisId="rate"
                      type="monotone"
                      dataKey="tick_rate"
                      name="Tick Rate"
                      stroke="#10b981"
                      strokeWidth={1.5}
                      dot={false}
                    />
                    <Line
                      yAxisId="delay"
                      type="monotone"
                      dataKey="tick_delay"
                      name="Tick Delay"
                      stroke="#f59e0b"
                      strokeWidth={1.5}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </Card>

              {/* Chart B: Execution Latency */}
              <Card>
                <div className="mb-2 flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-medium text-slate-900 dark:text-white">
                      Execution Latency
                    </h3>
                    <p className="text-xs text-slate-400">Average, 95th, and 99th percentile order round-trip</p>
                  </div>
                  <span className="text-xs font-mono text-slate-400">Avg · P95 · P99 (ms)</span>
                </div>
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="rgba(100,116,139,0.15)" vertical={false} />
                    <XAxis dataKey="label" stroke="#64748b" fontSize={11} tickLine={false} minTickGap={30} />
                    <YAxis stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} width={45} unit="ms" />
                    <Tooltip content={<ChartTooltip />} />
                    <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }} />
                    <Line
                      type="monotone"
                      dataKey="avg_latency"
                      name="Avg Latency"
                      stroke="#0ea5e9"
                      strokeWidth={1.5}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="p95_latency"
                      name="P95 Latency"
                      stroke="#f59e0b"
                      strokeWidth={1.5}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="p99_latency"
                      name="P99 Latency"
                      stroke="#ef4444"
                      strokeWidth={1.5}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </Card>

              {/* Chart C: Queue Health */}
              <Card>
                <div className="mb-2 flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-medium text-slate-900 dark:text-white">Queue Health</h3>
                    <p className="text-xs text-slate-400">Pending telemetry queue depth and dispatch wait time</p>
                  </div>
                  <span className="text-xs font-mono text-slate-400">Count · ms</span>
                </div>
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="rgba(100,116,139,0.15)" vertical={false} />
                    <XAxis dataKey="label" stroke="#64748b" fontSize={11} tickLine={false} minTickGap={30} />
                    <YAxis yAxisId="size" stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} width={40} />
                    <YAxis
                      yAxisId="wait"
                      orientation="right"
                      stroke="#64748b"
                      fontSize={11}
                      tickLine={false}
                      axisLine={false}
                      width={45}
                      unit="ms"
                    />
                    <Tooltip content={<ChartTooltip />} />
                    <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }} />
                    <Line
                      yAxisId="size"
                      type="monotone"
                      dataKey="queue_size"
                      name="Queue Size"
                      stroke="#6366f1"
                      strokeWidth={1.5}
                      dot={false}
                    />
                    <Line
                      yAxisId="wait"
                      type="monotone"
                      dataKey="queue_wait"
                      name="Queue Wait"
                      stroke="#ec4899"
                      strokeWidth={1.5}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </Card>

              {/* Chart D: API / Execution Quality */}
              <Card>
                <div className="mb-2 flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-medium text-slate-900 dark:text-white">
                      API / Execution Quality
                    </h3>
                    <p className="text-xs text-slate-400">Broker API connectivity and signal fill rate</p>
                  </div>
                  <span className="text-xs font-mono text-slate-400">Percentage %</span>
                </div>
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="rgba(100,116,139,0.15)" vertical={false} />
                    <XAxis dataKey="label" stroke="#64748b" fontSize={11} tickLine={false} minTickGap={30} />
                    <YAxis stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} width={40} unit="%" domain={[0, 100]} />
                    <Tooltip content={<ChartTooltip />} />
                    <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }} />
                    <Line
                      type="monotone"
                      dataKey="api_success"
                      name="API Success %"
                      stroke="#10b981"
                      strokeWidth={1.5}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="signal_fill"
                      name="Signal Fill Rate %"
                      stroke="#3b82f6"
                      strokeWidth={1.5}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </Card>

              {/* Chart E: Resource Usage */}
              <Card className="lg:col-span-2">
                <div className="mb-2 flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-medium text-slate-900 dark:text-white">
                      Resource Usage
                    </h3>
                    <p className="text-xs text-slate-400">CPU utilization and allocated heap memory</p>
                  </div>
                  <span className="text-xs font-mono text-slate-400">CPU % · Memory MB</span>
                </div>
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="rgba(100,116,139,0.15)" vertical={false} />
                    <XAxis dataKey="label" stroke="#64748b" fontSize={11} tickLine={false} minTickGap={30} />
                    <YAxis
                      yAxisId="cpu"
                      stroke="#64748b"
                      fontSize={11}
                      tickLine={false}
                      axisLine={false}
                      width={40}
                      unit="%"
                      domain={[0, 100]}
                    />
                    <YAxis
                      yAxisId="mem"
                      orientation="right"
                      stroke="#64748b"
                      fontSize={11}
                      tickLine={false}
                      axisLine={false}
                      width={50}
                      unit="MB"
                    />
                    <Tooltip content={<ChartTooltip />} />
                    <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }} />
                    <Line
                      yAxisId="cpu"
                      type="monotone"
                      dataKey="cpu"
                      name="CPU %"
                      stroke="#3b82f6"
                      strokeWidth={1.5}
                      dot={false}
                    />
                    <Line
                      yAxisId="mem"
                      type="monotone"
                      dataKey="memory"
                      name="Memory MB"
                      stroke="#8b5cf6"
                      strokeWidth={1.5}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </Card>
            </div>
          )}
        </>
      )}
    </div>
  );
}
