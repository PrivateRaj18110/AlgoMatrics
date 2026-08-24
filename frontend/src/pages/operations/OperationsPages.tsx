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
import { formatInZone, formatTradingTime, formatUtcTime } from "@/lib/time";
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
  const [range, setRange] = useState<"1H" | "6H" | "24H" | "7D">("1H");

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

  const startTime = useMemo(() => {
    const now = Date.now();
    const rangeMap = {
      "1H": 60 * 60 * 1000,
      "6H": 6 * 60 * 60 * 1000,
      "24H": 24 * 60 * 60 * 1000,
      "7D": 7 * 24 * 60 * 60 * 1000,
    };
    return new Date(now - rangeMap[range]).toISOString();
  }, [range]);

  const { data: healthData, isLoading: healthLoading, isError } = useOpsSystemHealth({
    machine_id: activeMid || undefined,
    start: startTime,
    limit: 500,
  });

  const chartData = useMemo(() => {
    if (!healthData?.points) return [];
    return healthData.points.map((pt) => ({
      time: pt.timestamp,
      label: formatInZone(pt.timestamp, "Asia/Kolkata", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
        ...(range === "7D" ? { month: "short", day: "numeric" } : {}),
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
  }, [healthData?.points, range]);

  const isLive = healthData?.is_live ?? false;
  const execStatus = healthData?.current_execution_status ?? "offline";
  const healthStatus = healthData?.current_health_status ?? "—";
  const lastUpdated = healthData?.last_health_timestamp;

  return (
    <div className="space-y-6">
      <PageHeader
        title="System Health"
        description="Execution VM performance, latency percentiles, and system stability telemetry."
      />
      <TimezoneCaption />

      {/* Control Strip */}
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
          {(["1H", "6H", "24H", "7D"] as const).map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setRange(r)}
              className={clsx(
                "rounded px-2.5 py-1 text-xs font-medium transition-colors",
                range === r
                  ? "bg-white text-slate-900 shadow-sm dark:bg-surface-800 dark:text-white"
                  : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
              )}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      {/* Machine & Health Status Header Card */}
      <Card>
        <div className="grid gap-4 sm:grid-cols-4">
          <div>
            <p className="text-xs text-slate-500">Execution Machine</p>
            <p className="mt-1 font-semibold text-slate-900 dark:text-white">
              {healthData?.machine_name || activeMid || "—"}
            </p>
            <div className="mt-1 flex items-center gap-1.5">
              <span
                className={clsx(
                  "inline-block h-2 w-2 rounded-full",
                  isLive ? "bg-emerald-500 animate-pulse" : "bg-slate-400"
                )}
              />
              <span className="text-xs text-slate-500">
                {isLive ? "LIVE TELEMETRY" : "Historical telemetry"}
              </span>
            </div>
          </div>

          <div>
            <p className="text-xs text-slate-500">Execution Status</p>
            <div className="mt-1">
              <Badge color={execStatus === "online" ? "green" : "slate"}>
                {execStatus.toUpperCase()}
              </Badge>
            </div>
            <p className="mt-1 text-xs text-slate-400">Heartbeat liveness</p>
          </div>

          <div>
            <p className="text-xs text-slate-500">Health State</p>
            <div className="mt-1">
              <Badge
                color={
                  healthStatus === "STABLE"
                    ? "green"
                    : healthStatus === "DEGRADED"
                    ? "amber"
                    : healthStatus === "CRITICAL"
                    ? "red"
                    : "slate"
                }
              >
                {healthStatus}
              </Badge>
            </div>
            <p className="mt-1 text-xs text-slate-400">Performance snapshot</p>
          </div>

          <div>
            <p className="text-xs text-slate-500">Last Snapshot (IST)</p>
            <p className="mt-1 text-sm font-medium text-slate-700 dark:text-slate-300">
              {lastUpdated ? formatTradingTime(lastUpdated) : "—"}
            </p>
            <p className="mt-1 text-xs text-slate-400">Asia/Kolkata timezone</p>
          </div>
        </div>
      </Card>

      {/* Charts Section */}
      {healthLoading ? (
        <Card>
          <SkeletonRows rows={8} cols={4} />
        </Card>
      ) : isError ? (
        <TelemetryError />
      ) : !chartData.length ? (
        <Card>
          <EmptyState
            title="No system health telemetry available."
            body="No performance snapshots have been recorded for this machine within the selected time window. Production never renders mock data."
          />
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Chart 1: CPU Usage & Memory */}
          <Card>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-medium text-slate-900 dark:text-white">CPU Usage & Memory</h3>
              <span className="text-xs text-slate-400">CPU (0–100%) · Memory (MB)</span>
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
                  name="CPU Usage (%)"
                  stroke="#3b82f6"
                  strokeWidth={1.5}
                  dot={false}
                />
                <Line
                  yAxisId="mem"
                  type="monotone"
                  dataKey="memory"
                  name="Memory (MB)"
                  stroke="#8b5cf6"
                  strokeWidth={1.5}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </Card>

          {/* Chart 2: Latency Profile */}
          <Card>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-medium text-slate-900 dark:text-white">Latency Profile</h3>
              <span className="text-xs text-slate-400">Avg · P95 · P99 (ms)</span>
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
                  name="Avg Latency (ms)"
                  stroke="#0ea5e9"
                  strokeWidth={1.5}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="p95_latency"
                  name="P95 Latency (ms)"
                  stroke="#f59e0b"
                  strokeWidth={1.5}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="p99_latency"
                  name="P99 Latency (ms)"
                  stroke="#ef4444"
                  strokeWidth={1.5}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </Card>

          {/* Chart 3: Tick Rate & Delay */}
          <Card>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-medium text-slate-900 dark:text-white">Tick Rate & Tick Delay</h3>
              <span className="text-xs text-slate-400">Ticks/sec · Delay (ms)</span>
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
                  name="Tick Rate (ticks/s)"
                  stroke="#10b981"
                  strokeWidth={1.5}
                  dot={false}
                />
                <Line
                  yAxisId="delay"
                  type="monotone"
                  dataKey="tick_delay"
                  name="Tick Delay (ms)"
                  stroke="#f97316"
                  strokeWidth={1.5}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </Card>

          {/* Chart 4: Queue Health */}
          <Card>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-medium text-slate-900 dark:text-white">Queue Health</h3>
              <span className="text-xs text-slate-400">Queue Size (count) · Wait (ms)</span>
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
                  name="Queue Wait (ms)"
                  stroke="#ec4899"
                  strokeWidth={1.5}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </Card>

          {/* Chart 5: Reliability & Signal Fill */}
          <Card className="lg:col-span-2">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-medium text-slate-900 dark:text-white">
                API Reliability & Signal Fill Rate
              </h3>
              <span className="text-xs text-slate-400">API Success (%) · Signal Fill (%)</span>
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="rgba(100,116,139,0.15)" vertical={false} />
                <XAxis dataKey="label" stroke="#64748b" fontSize={11} tickLine={false} minTickGap={30} />
                <YAxis stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} width={40} unit="%" domain={[0, 100]} />
                <Tooltip content={<ChartTooltip />} />
                <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }} />
                <Line
                  type="monotone"
                  dataKey="api_success"
                  name="API Success Rate (%)"
                  stroke="#10b981"
                  strokeWidth={1.5}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="signal_fill"
                  name="Signal Fill Rate (%)"
                  stroke="#3b82f6"
                  strokeWidth={1.5}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        </div>
      )}
    </div>
  );
}
