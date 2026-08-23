import { Link, useParams } from "react-router";

import {
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
  useOpsTrades,
} from "@/lib/hooks";
import { money, signed } from "@/lib/format";
import { formatTradingTime, formatUtcTime } from "@/lib/time";
import { unknownMs, unknownPercent } from "@/lib/unknown";
import { useState } from "react";

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
