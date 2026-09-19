import { Link } from "react-router";

import { Seo } from "@/components/Seo";
import { useAuth } from "@/stores/auth";

import { MarketingFooter } from "@/pages/marketing/MarketingFooter";
import { MarketingNav } from "@/pages/marketing/MarketingNav";
import {
  DepthBars,
  ExecutionTimeline,
  HeroPipeline,
  InfrastructureDiagram,
  MonitoringVisual,
  ResearchPipeline,
  SecurityStack,
  SignalWave,
  Sparkline,
  SystemStatusPanel,
} from "@/pages/marketing/visuals";

const LAYERS = [
  {
    title: "Market Data",
    body: "Real-time market and derivatives data.",
    visual: <Sparkline points={[12, 14, 13, 18, 16, 21, 19, 24, 22, 26]} />,
  },
  {
    title: "Strategy Engine",
    body: "Systematic signal generation and strategy execution.",
    visual: <SignalWave />,
  },
  {
    title: "Risk Engine",
    body: "Position, exposure and execution safeguards.",
    visual: <Sparkline points={[8, 9, 8, 11, 10, 9, 12, 10, 9, 8]} stroke="#34d399" />,
  },
  {
    title: "Execution",
    body: "Broker connectivity and order execution infrastructure.",
    visual: <DepthBars />,
  },
  {
    title: "Monitoring",
    body: "Real-time strategy, execution and system observability.",
    visual: <Sparkline points={[4, 5, 4, 6, 8, 5, 4, 7, 5, 4]} stroke="#fbbf24" />,
  },
  {
    title: "Research",
    body: "Historical analysis, experimentation and quantitative validation.",
    visual: <Sparkline points={[20, 18, 19, 17, 21, 23, 22, 25, 24, 26]} />,
  },
];

const STRATEGIES = [
  {
    name: "H30-X2",
    market: "OPTION REPRICING",
    timeframe: "30 SEC",
    signal: "ACTIVE",
    environment: "PAPER" as const,
  },
];

const PRINCIPLES = [
  "Defense in Depth",
  "Least Privilege",
  "Fail Closed",
  "Continuous Monitoring",
  "Secure Authentication",
  "Auditability",
];

export function MarketingPage() {
  const authenticated = useAuth((state) => state.status) === "authenticated";
  const launchTo = authenticated ? "/app/dashboard" : "/login";

  return (
    <div className="am-page min-h-screen overflow-x-hidden bg-surface-950 text-slate-100">
      <Seo
        title="ALGOMATRIC — Quantitative Trading Infrastructure"
        description="Research, automate, execute and monitor systematic trading strategies through a unified quantitative infrastructure."
        canonicalPath="/"
      />
      <a
        href="#platform"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[60] focus:rounded-md focus:bg-surface-900 focus:px-3 focus:py-2 focus:text-sm"
      >
        Skip to content
      </a>
      <MarketingNav />
      <main>
        <section className="relative overflow-hidden pt-24 pb-20 sm:pt-28 sm:pb-28">
          <div className="am-grid am-radial am-scanlines absolute inset-0 opacity-90" />
          <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-4 sm:px-6 lg:grid-cols-[1.05fr_0.95fr]">
            <div className="am-reveal">
              <p className="font-mono text-[10px] tracking-[0.14em] text-accent-400 sm:text-[11px] sm:tracking-[0.28em]">
                ALGOMATRIC
                <br />
                QUANTITATIVE TRADING INFRASTRUCTURE
              </p>
              <h1 className="mt-5 max-w-xl text-[1.85rem] font-semibold leading-[1.12] tracking-tight text-white sm:text-5xl sm:leading-[1.05] lg:text-6xl">
                Quantitative Intelligence.
                <br />
                Built for Precision.
              </h1>
              <p className="mt-5 max-w-lg text-sm leading-relaxed text-slate-400 sm:text-lg">
                Research, automate, execute and monitor systematic trading strategies through a
                unified quantitative infrastructure.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <a
                  href="#platform"
                  className="rounded-lg bg-accent-500 px-5 py-2.5 text-sm font-medium text-surface-950 transition hover:bg-accent-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400"
                >
                  Explore Platform
                </a>
                <Link
                  to={launchTo}
                  className="rounded-lg border border-white/12 px-5 py-2.5 text-sm text-slate-200 transition hover:border-white/25 hover:bg-white/4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400"
                >
                  Launch Platform
                </Link>
              </div>
              <div className="mt-8 max-w-sm">
                <SystemStatusPanel
                  title="SYSTEM STATUS"
                  caption="ILLUSTRATIVE VISUALIZATION"
                  rows={[
                    { label: "MARKET DATA", state: "CONNECTED" },
                    { label: "STRATEGIES", state: "ACTIVE" },
                    { label: "RISK ENGINE", state: "READY" },
                    { label: "EXECUTION", state: "READY" },
                    { label: "MONITORING", state: "ACTIVE" },
                  ]}
                />
              </div>
            </div>
            <HeroPipeline />
          </div>
        </section>

        <section id="platform" className="border-y border-white/6 py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <p className="font-mono text-[11px] tracking-[0.24em] text-accent-400">PLATFORM</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
              One Infrastructure. Every Layer of the Trade.
            </h2>
            <div className="mt-10 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {LAYERS.map((layer) => (
                <article
                  key={layer.title}
                  className="am-card rounded-[22px] p-5 transition-transform duration-200 hover:-translate-y-0.5"
                >
                  <div className="mb-5 h-10">{layer.visual}</div>
                  <h3 className="text-lg text-white">{layer.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-400">{layer.body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="strategies" className="py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <p className="font-mono text-[11px] tracking-[0.24em] text-accent-400">STRATEGIES</p>
            <h2 className="mt-3 text-3xl font-semibold text-white">
              Strategies Built for Systematic Markets
            </h2>
            <p className="mt-4 max-w-2xl text-sm text-slate-500">
              Illustrative strategy card. Names, status and environment in the console come from
              your organisation. No performance, win-rate or return figures are shown here.
            </p>
            <div className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {STRATEGIES.map((strategy) => (
                <article key={strategy.name} className="am-card rounded-[22px] p-5">
                  <div className="flex items-start justify-between gap-3">
                    <h3 className="font-mono text-xl text-white">{strategy.name}</h3>
                    <span className="rounded-full border border-accent-400/30 bg-accent-500/10 px-2 py-0.5 font-mono text-[10px] tracking-wide text-accent-200">
                      {strategy.environment}
                    </span>
                  </div>
                  <p className="mt-3 font-mono text-[11px] tracking-[0.16em] text-slate-500">
                    {strategy.market}
                  </p>
                  <dl className="mt-5 grid grid-cols-2 gap-3 font-mono text-[11px] text-slate-400">
                    <div>
                      <dt className="text-slate-600">STATUS</dt>
                      <dd className="mt-1 text-slate-200">{strategy.environment}</dd>
                    </div>
                    <div>
                      <dt className="text-slate-600">TIMEFRAME</dt>
                      <dd className="mt-1 text-slate-200">{strategy.timeframe}</dd>
                    </div>
                    <div>
                      <dt className="text-slate-600">SIGNAL</dt>
                      <dd className="mt-1 text-slate-200">{strategy.signal}</dd>
                    </div>
                  </dl>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="environments" className="border-y border-white/6 py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <p className="font-mono text-[11px] tracking-[0.24em] text-accent-400">ENVIRONMENTS</p>
            <h2 className="mt-3 text-3xl font-semibold text-white">Paper and live are not the same system.</h2>
            <p className="mt-4 max-w-2xl text-slate-400">
              Paper trading is simulated. Live trading requires an approved broker connection,
              organization enablement and server-side authorization. The two modes are labeled
              distinctly throughout the console.
            </p>
            <div className="mt-10 grid gap-4 md:grid-cols-2">
              <article className="rounded-[22px] border border-accent-400/20 bg-accent-500/5 p-6">
                <p className="font-mono text-[11px] tracking-[0.22em] text-accent-300">PAPER</p>
                <p className="mt-3 text-sm leading-relaxed text-slate-400">
                  Simulated execution for research, configuration and operator rehearsal. Paper
                  fills never reach a live venue.
                </p>
              </article>
              <article className="rounded-[22px] border border-loss-500/35 bg-loss-500/8 p-6">
                <p className="font-mono text-[11px] tracking-[0.22em] text-loss-400">LIVE</p>
                <p className="mt-2 inline-block rounded border border-amber-400/40 bg-amber-500/10 px-2 py-0.5 font-mono text-[10px] tracking-wide text-amber-300">
                  REAL ORDERS · ADDITIONAL CONTROLS
                </p>
                <p className="mt-3 text-sm leading-relaxed text-slate-400">
                  Live mode can submit real orders. It is gated by authentication, authorization,
                  account validation, risk limits and broker state. Uncertain state fails closed.
                </p>
              </article>
            </div>
          </div>
        </section>

        <section id="execution" className="py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">
              Every Millisecond Has a Purpose.
            </h2>
            <p className="mt-4 max-w-2xl text-slate-400">
              Path from market event to broker acknowledgement. Timing is schematic staging, not
              measured production latency.
            </p>
            <div className="mt-10">
              <ExecutionTimeline />
            </div>
            <p className="mt-4 font-mono text-[10px] tracking-[0.18em] text-slate-600">ILLUSTRATIVE</p>
          </div>
        </section>

        <section id="monitoring" className="border-y border-white/6 py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <p className="font-mono text-[11px] tracking-[0.24em] text-accent-400">MONITORING</p>
            <h2 className="mt-3 text-3xl font-semibold text-white">Control plane, not wallpaper.</h2>
            <p className="mt-4 max-w-2xl text-sm text-slate-500">
              Live connectivity and broker health are available inside the authenticated console.
              Public indicators describe posture, not internal topology.
            </p>
            <div className="mt-10">
              <MonitoringVisual />
            </div>
          </div>
        </section>

        <section id="infrastructure" className="py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <p className="font-mono text-[11px] tracking-[0.24em] text-accent-400">INFRASTRUCTURE</p>
            <h2 className="mt-3 text-3xl font-semibold text-white">A path, not a pile of tools.</h2>
            <p className="mt-4 max-w-2xl text-slate-400">
              Hover or focus a layer. Descriptions stay conceptual — no addresses, ports or
              credentials.
            </p>
            <div className="am-card mt-10 rounded-[28px] p-4 sm:p-8">
              <InfrastructureDiagram />
            </div>
          </div>
        </section>

        <section id="research" className="border-y border-white/6 py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <p className="font-mono text-[11px] tracking-[0.24em] text-accent-400">RESEARCH</p>
            <h2 className="mt-3 text-3xl font-semibold text-white">Systematic research before deployment.</h2>
            <p className="mt-4 max-w-2xl text-slate-400">
              Algomatric is built around validation, not arbitrary trading decisions. Arming a
              strategy is a distinct, authorized step.
            </p>
            <div className="mt-10">
              <ResearchPipeline />
            </div>
          </div>
        </section>

        <section id="security" className="py-20">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 sm:px-6 lg:grid-cols-[1.1fr_0.9fr]">
            <div>
              <p className="font-mono text-[11px] tracking-[0.24em] text-accent-400">SECURITY</p>
              <h2 className="mt-3 text-3xl font-semibold text-white">Security by Design.</h2>
              <p className="mt-4 max-w-xl text-slate-400">
                Controls are layered and fail closed. We do not claim systems are unhackable or
                immune to compromise.
              </p>
              <div className="mt-8 flex flex-wrap gap-2">
                {PRINCIPLES.map((item) => (
                  <span
                    key={item}
                    className="rounded-full border border-white/10 px-3 py-1.5 text-sm text-slate-300"
                  >
                    {item}
                  </span>
                ))}
              </div>
            </div>
            <SecurityStack />
          </div>
        </section>

        <section className="pb-24">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <div className="am-card flex flex-col items-start justify-between gap-6 rounded-[28px] px-6 py-10 sm:flex-row sm:items-center sm:px-10">
              <div>
                <h2 className="text-3xl font-semibold text-white">Enter the platform.</h2>
                <p className="mt-2 max-w-xl text-slate-400">
                  Access is invitation-based. Authenticated sessions reach dashboards, research,
                  risk and execution.
                </p>
              </div>
              <Link
                to={launchTo}
                className="rounded-lg bg-accent-500 px-5 py-2.5 text-sm font-medium text-surface-950 transition hover:bg-accent-300"
              >
                Launch Platform
              </Link>
            </div>
          </div>
        </section>
      </main>
      <MarketingFooter />
    </div>
  );
}
