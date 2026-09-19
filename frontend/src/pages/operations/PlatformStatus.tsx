// One-glance status of every data source the platform depends on, shown at the
// top of System Health. Each tile states what it knows and says "Unknown" when
// a source has not answered — never a green tick by default.

import { clsx } from "clsx";
import { Link } from "react-router";

import { Glyph, type GlyphName } from "@/components/icons";
import { surface } from "@/components/ui";
import { useDevices } from "@/lib/devices";
import { useMonitoringSources } from "@/lib/hooks";
import { useMarketPulse } from "@/lib/markets";

type Tone = "good" | "warn" | "bad" | "unknown";

const TONE: Record<Tone, { dot: string; text: string; label: string }> = {
  good: { dot: "bg-profit-500", text: "text-profit-600 dark:text-profit-400", label: "Operational" },
  warn: { dot: "bg-amber-500", text: "text-amber-600 dark:text-amber-300", label: "Attention" },
  bad: { dot: "bg-loss-500", text: "text-loss-600 dark:text-loss-400", label: "Down" },
  unknown: { dot: "bg-slate-400", text: "text-slate-500", label: "Unknown" },
};

function Tile({
  icon,
  title,
  tone,
  value,
  detail,
  to,
}: {
  icon: GlyphName;
  title: string;
  tone: Tone;
  value: string;
  detail: string;
  to: string;
}) {
  const style = TONE[tone];
  return (
    <Link
      to={to}
      className={clsx(surface, "group flex flex-col gap-2 p-4 transition-colors hover:border-accent-500/40")}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-xs font-medium text-slate-500 dark:text-slate-400">
          <Glyph name={icon} className="size-4" />
          {title}
        </span>
        <span className={clsx("flex items-center gap-1.5 text-[11px] font-semibold", style.text)}>
          <span className={clsx("size-1.5 rounded-full", style.dot, tone === "good" && "am-live-dot")} />
          {style.label}
        </span>
      </div>
      <p className="text-lg font-semibold tracking-tight text-slate-900 dark:text-white">{value}</p>
      <p className="text-xs text-slate-500 dark:text-slate-400">{detail}</p>
    </Link>
  );
}

export function PlatformStatus() {
  const devices = useDevices();
  const pulse = useMarketPulse();
  const sources = useMonitoringSources();

  const fleet = (devices.data ?? []).filter((device) => device.status !== "revoked");
  const online = fleet.filter((device) => device.status === "online").length;
  const offline = fleet.filter((device) => device.status === "offline").length;
  const deviceTone: Tone = !devices.isSuccess || fleet.length === 0 ? "unknown" : offline > 0 ? "warn" : "good";

  const quoted = pulse.data ? pulse.data.breadth.advances + pulse.data.breadth.declines + pulse.data.breadth.unchanged : 0;
  const marketTone: Tone = pulse.isError && !pulse.data ? "bad" : !pulse.data ? "unknown" : quoted > 0 ? "good" : "warn";
  const universe = pulse.data?.universe;

  const sourceRows = sources.data ?? [];
  const refused = sourceRows.reduce((sum, row) => sum + row.refused_gap_count + row.refused_old_count, 0);
  const llsTone: Tone = !sources.data ? "unknown" : sourceRows.length === 0 ? "unknown" : refused > 0 ? "warn" : "good";

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Tile
        icon="server"
        title="Trading devices"
        tone={deviceTone}
        to="/app/devices"
        value={devices.isSuccess ? `${online} of ${fleet.length} online` : "Unknown"}
        detail={
          !devices.isSuccess
            ? "Device list did not load"
            : fleet.length === 0
              ? "No devices registered yet"
              : offline > 0
                ? `${offline} silent for over 3 minutes`
                : "All reporting normally"
        }
      />
      <Tile
        icon="chart"
        title="Market data"
        tone={marketTone}
        to="/app/market-update"
        value={pulse.data ? `${quoted} F&O stocks quoted` : "Unknown"}
        detail={pulse.data ? "NSE + Yahoo, delayed, refreshed every minute" : "Quote sources did not answer"}
      />
      <Tile
        icon="clock"
        title="NSE daily snapshots"
        tone={!universe ? "unknown" : universe.source === "nse" ? "good" : "warn"}
        to="/app/pre-market"
        value={universe?.source === "nse" ? `Pre-open ${universe.trade_date}` : universe ? "Not captured yet" : "Unknown"}
        detail={
          universe?.source === "nse"
            ? "Captured automatically at 09:08 IST each trading day"
            : "The first capture happens on the next trading morning"
        }
      />
      <Tile
        icon="signal"
        title="LLS monitoring"
        tone={llsTone}
        to="/app/lls-monitoring"
        value={sources.data ? `${sourceRows.length} source(s)` : "Unknown"}
        detail={
          !sources.data
            ? "Receiver did not answer"
            : refused > 0
              ? `${refused} message(s) refused for ordering`
              : "Ordered delivery, nothing refused"
        }
      />
    </div>
  );
}
