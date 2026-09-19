import { clsx } from "clsx";
import { useState } from "react";

export function Sparkline({
  points,
  className,
  stroke = "#3dd0ea",
}: {
  points: number[];
  className?: string;
  stroke?: string;
}) {
  const max = Math.max(...points);
  const min = Math.min(...points);
  const range = max - min || 1;
  const d = points
    .map((value, index) => {
      const x = (index / (points.length - 1)) * 120;
      const y = 28 - ((value - min) / range) * 24;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg viewBox="0 0 120 32" className={clsx("h-8 w-full overflow-visible", className)} aria-hidden>
      <path d={d} fill="none" stroke={stroke} strokeWidth="1.4" className="am-draw" />
    </svg>
  );
}

export function DepthBars() {
  const heights = [18, 28, 22, 36, 30, 42, 26, 34, 20, 16];
  return (
    <svg viewBox="0 0 120 48" className="h-10 w-full" aria-hidden>
      {heights.map((height, index) => (
        <rect
          key={index}
          x={index * 12}
          y={48 - height}
          width="8"
          height={height}
          rx="1"
          fill={index < 5 ? "rgba(61,208,234,0.35)" : "rgba(244,63,94,0.28)"}
        />
      ))}
    </svg>
  );
}

export function SignalWave() {
  return (
    <div className="overflow-hidden" aria-hidden>
      <svg
        viewBox="0 0 240 36"
        className="am-wave-track h-8 w-[200%] motion-safe:animate-[am-wave_12s_linear_infinite]"
      >
        <path
          d="M0 18 C 20 18, 20 6, 40 6 S 60 30, 80 30 S 100 10, 120 10 S 140 26, 160 26 S 180 8, 200 8 S 220 18, 240 18"
          fill="none"
          stroke="rgba(61,208,234,0.7)"
          strokeWidth="1.3"
        />
      </svg>
    </div>
  );
}

export function HeroPipeline() {
  const nodes = [
    { id: "market", label: "MARKET DATA", x: 200, y: 28 },
    { id: "signal", label: "SIGNAL ENGINE", x: 200, y: 88 },
    { id: "strategy", label: "STRATEGY ENGINE", x: 200, y: 148 },
    { id: "risk", label: "RISK ENGINE", x: 200, y: 208 },
    { id: "exec", label: "EXECUTION", x: 200, y: 268 },
    { id: "mon", label: "MONITORING", x: 200, y: 328 },
  ];

  return (
    <div className="relative mx-auto w-full max-w-[420px]">
      <div className="pointer-events-none absolute inset-0 rounded-[28px] bg-[radial-gradient(circle_at_50%_20%,rgba(34,184,212,0.12),transparent_58%)]" />
      <svg
        viewBox="0 0 400 360"
        className="relative w-full"
        role="img"
        aria-label="Trading pipeline from market data through signal, strategy, risk, execution and monitoring"
      >
        <defs>
          <linearGradient id="pipe" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3dd0ea" stopOpacity="0.15" />
            <stop offset="100%" stopColor="#3dd0ea" stopOpacity="0.7" />
          </linearGradient>
        </defs>
        <path id="stack-path" d="M200 36 V 328" stroke="url(#pipe)" strokeWidth="1.2" fill="none" />
        {[0, 1, 2].map((index) => (
          <circle key={index} r="2.4" fill="#7ee4f5" className="am-particle motion-reduce:hidden">
            <animateMotion dur={`${4.2 + index}s`} repeatCount="indefinite" begin={`${index * 1.2}s`}>
              <mpath href="#stack-path" />
            </animateMotion>
          </circle>
        ))}
        {nodes.map((node) => (
          <g key={node.id}>
            <rect
              x={node.x - 92}
              y={node.y - 16}
              width="184"
              height="32"
              rx="8"
              fill="rgba(11,15,22,0.86)"
              stroke="rgba(125,211,240,0.28)"
            />
            <circle cx={node.x - 76} cy={node.y} r="3" fill="#34d399">
              <animate attributeName="opacity" values="0.4;1;0.4" dur="2.4s" repeatCount="indefinite" />
            </circle>
            <text
              x={node.x}
              y={node.y + 4}
              textAnchor="middle"
              fill="#e2e8f0"
              fontSize="11"
              letterSpacing="1.8"
              fontFamily="IBM Plex Mono, ui-monospace, monospace"
            >
              {node.label}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

export function SystemStatusPanel({
  title,
  rows,
  caption,
}: {
  title: string;
  rows: Array<{ label: string; state: string }>;
  caption: string;
}) {
  return (
    <aside className="am-card rounded-2xl p-4 font-mono text-[11px] tracking-wide">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-[10px] tracking-[0.22em] text-slate-500">{title}</p>
        <span className="am-heartbeat size-1.5 rounded-full bg-profit-400" aria-hidden />
      </div>
      <ul className="space-y-2">
        {rows.map((row) => (
          <li key={row.label} className="flex items-center justify-between gap-6">
            <span className="text-slate-500">{row.label}</span>
            <span className="text-profit-400">{row.state}</span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[10px] tracking-[0.16em] text-slate-600">{caption}</p>
    </aside>
  );
}

const INFRA_NODES = [
  {
    id: "markets",
    label: "MARKETS",
    x: 260,
    y: 8,
    body: "Venues and market data sources. Public diagrams stay abstract — no hosts, ports or credentials.",
  },
  {
    id: "data",
    label: "MARKET DATA",
    x: 260,
    y: 64,
    body: "Normalized market and derivatives data used by research and live decisioning.",
  },
  {
    id: "features",
    label: "FEATURE ENGINE",
    x: 260,
    y: 120,
    body: "Derived features computed from incoming data before a strategy sees them.",
  },
  {
    id: "strategy",
    label: "STRATEGY ENGINE",
    x: 260,
    y: 176,
    body: "Systematic signal generation and strategy state, separate from order submission.",
  },
  {
    id: "risk",
    label: "RISK ENGINE",
    x: 260,
    y: 232,
    body: "Server-side limits, kill switches and pre-trade checks. Fail closed when state is uncertain.",
  },
  {
    id: "execution",
    label: "EXECUTION",
    x: 260,
    y: 288,
    body: "Order construction and broker routing after risk approval.",
  },
  {
    id: "brokers",
    label: "BROKERS",
    x: 260,
    y: 344,
    body: "Verified broker connections. Paper and live accounts are distinct modes.",
  },
  {
    id: "monitoring",
    label: "MONITORING",
    x: 260,
    y: 400,
    body: "Observability of strategy state, execution and system health for authorized operators.",
  },
] as const;

export function InfrastructureDiagram() {
  const [active, setActive] = useState<string | null>(null);
  const current = INFRA_NODES.find((node) => node.id === active) ?? INFRA_NODES[0];

  return (
    <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
      <svg
        viewBox="0 0 520 448"
        className="h-auto w-full"
        role="img"
        aria-label="Infrastructure path from markets through monitoring. Hover or focus a node for a description."
      >
        <path
          d="M260 32 V 416"
          stroke="rgba(61,208,234,0.28)"
          strokeWidth="1.2"
          fill="none"
        />
        <path id="infra-path" d="M260 32 V 416" fill="none" />
        <circle r="2.5" fill="#7ee4f5" className="am-particle motion-reduce:hidden">
          <animateMotion dur="7s" repeatCount="indefinite">
            <mpath href="#infra-path" />
          </animateMotion>
        </circle>
        {INFRA_NODES.map((node) => {
          const lit = active === node.id;
          return (
            <g
              key={node.id}
              tabIndex={0}
              role="button"
              aria-label={`${node.label}. ${node.body}`}
              onMouseEnter={() => setActive(node.id)}
              onFocus={() => setActive(node.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setActive(node.id);
                }
              }}
              className="cursor-pointer outline-none"
            >
              <rect
                x={node.x - 78}
                y={node.y}
                width="156"
                height="34"
                rx="8"
                fill={lit ? "rgba(20, 40, 52, 0.96)" : "rgba(16,21,30,0.92)"}
                stroke={lit ? "rgba(61,208,234,0.7)" : "rgba(148,163,184,0.2)"}
              />
              <circle cx={node.x - 62} cy={node.y + 17} r="2.6" fill={lit ? "#7ee4f5" : "#3dd0ea"} />
              <text
                x={node.x}
                y={node.y + 22}
                textAnchor="middle"
                fill={lit ? "#f8fafc" : "#cbd5e1"}
                fontSize="11"
                letterSpacing="1.5"
                fontFamily="IBM Plex Mono, ui-monospace, monospace"
              >
                {node.label}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="am-card h-fit rounded-2xl p-5">
        <p className="font-mono text-[10px] tracking-[0.22em] text-slate-500">LAYER</p>
        <h3 className="mt-2 font-mono text-sm tracking-[0.14em] text-white">{current.label}</h3>
        <p className="mt-3 text-sm leading-relaxed text-slate-400">{current.body}</p>
      </div>
    </div>
  );
}

export function ExecutionTimeline() {
  const stages = [
    "Market Event",
    "Data Received",
    "Feature Processing",
    "Signal",
    "Risk Check",
    "Order Submission",
    "Broker ACK",
    "Execution",
  ];
  return (
    <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
      {stages.map((stage, index) => (
        <li key={stage} className="relative rounded-2xl border border-white/10 bg-white/4 px-3 py-3">
          <p className="font-mono text-[10px] tracking-[0.18em] text-accent-400">
            {String(index + 1).padStart(2, "0")}
          </p>
          <p className="mt-2 text-sm leading-snug text-slate-200">{stage}</p>
          {index < stages.length - 1 && (
            <span className="mt-2 hidden font-mono text-[10px] text-slate-600 xl:block">↓</span>
          )}
        </li>
      ))}
    </ol>
  );
}

export function MonitoringVisual() {
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1.1fr]">
      <SystemStatusPanel
        title="ALGOMATRIC SYSTEM"
        caption="ILLUSTRATIVE · NO INTERNAL HOSTS"
        rows={[
          { label: "DATA", state: "CONNECTED" },
          { label: "STRATEGIES", state: "ACTIVE" },
          { label: "RISK ENGINE", state: "HEALTHY" },
          { label: "EXECUTION", state: "READY" },
          { label: "MONITORING", state: "ACTIVE" },
        ]}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="am-card rounded-2xl p-4">
          <p className="font-mono text-[10px] tracking-[0.2em] text-slate-500">SIGNAL ACTIVITY</p>
          <Sparkline points={[8, 10, 9, 14, 12, 16, 13, 18, 15, 17]} className="mt-3" />
        </div>
        <div className="am-card rounded-2xl p-4">
          <p className="font-mono text-[10px] tracking-[0.2em] text-slate-500">EXECUTION TIMELINE</p>
          <Sparkline points={[4, 5, 4, 7, 6, 5, 8, 6, 5, 7]} stroke="#fbbf24" className="mt-3" />
        </div>
        <div className="am-card rounded-2xl p-4 sm:col-span-2">
          <p className="font-mono text-[10px] tracking-[0.2em] text-slate-500">SYSTEM HEARTBEAT</p>
          <div className="mt-4 flex items-end gap-1" aria-hidden>
            {Array.from({ length: 28 }, (_, index) => (
              <span
                key={index}
                className="am-heartbeat inline-block w-full rounded-sm bg-accent-500/40"
                style={{
                  height: `${10 + ((index * 7) % 18)}px`,
                  animationDelay: `${index * 80}ms`,
                }}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function ResearchPipeline() {
  const steps = ["DATA", "FEATURES", "EXPERIMENT", "VALIDATION", "WALK-FORWARD", "DEPLOYMENT"];
  return (
    <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-6">
      {steps.map((step, index) => (
        <li key={step} className="rounded-2xl border border-white/10 bg-white/3 px-3 py-4">
          <p className="font-mono text-[10px] tracking-[0.2em] text-accent-400">
            {String(index + 1).padStart(2, "0")}
          </p>
          <p className="mt-2 font-mono text-xs tracking-[0.14em] text-slate-200">{step}</p>
        </li>
      ))}
    </ol>
  );
}

export function SecurityStack() {
  const layers = [
    "AUTHENTICATION",
    "AUTHORIZATION",
    "RATE LIMITING",
    "API SECURITY",
    "APPLICATION SECURITY",
    "RISK CONTROLS",
    "EXECUTION CONTROLS",
    "MONITORING",
    "AUDIT TRAIL",
  ];
  return (
    <ol className="space-y-1.5 font-mono text-[11px] tracking-[0.16em]">
      {layers.map((layer, index) => (
        <li key={layer} className="flex items-center gap-3 rounded-lg border border-white/8 bg-white/3 px-3 py-2">
          <span className="text-accent-400">{String(index + 1).padStart(2, "0")}</span>
          <span className="text-slate-200">{layer}</span>
        </li>
      ))}
    </ol>
  );
}
