import { useState } from "react";
import { Link } from "react-router";

import { ThemeToggle } from "@/components/ThemeToggle";
import { Badge, Button } from "@/components/ui";
import { usePlans } from "@/lib/hooks";
import { money } from "@/lib/format";
import { useAuth } from "@/stores/auth";

const FEATURES = [
  {
    title: "Broker-neutral execution",
    body: "One canonical order model across paper, Zerodha, Angel One, Delta, and MT5. Strategies never touch a broker SDK.",
    icon: "M4 7h16M4 12h16M4 17h10",
  },
  {
    title: "Hierarchical risk engine",
    body: "Pre-trade limits, continuous risk, and kill switches at platform, account, and strategy scope. Fail-closed by default.",
    icon: "M12 3l9 4v6c0 5-4 8-9 9-5-1-9-4-9-9V7z",
  },
  {
    title: "Deterministic paper trading",
    body: "Reproducible fills with slippage, fees, and partial fills. Validate a strategy before risking a rupee.",
    icon: "M4 17l6-6 4 4 6-8",
  },
  {
    title: "Real-time P&L",
    body: "WebSocket-streamed orders, positions, and portfolio equity. Stale feeds are surfaced, never hidden.",
    icon: "M3 3v18h18M7 14l4-4 3 3 5-6",
  },
  {
    title: "Multi-tenant by construction",
    body: "Organizations, RBAC roles, invitations, and per-tenant isolation enforced in every query.",
    icon: "M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 100-8 4 4 0 000 8z",
  },
  {
    title: "First-party strategies + uploads",
    body: "Ship with SMA crossover, RSI reversion, and momentum breakout, or upload your own sandboxed Python.",
    icon: "M12 4v16m8-8H4",
  },
];

const FAQ = [
  {
    q: "Is paper trading really free?",
    a: "Yes. The Free plan includes one paper broker connection and one active strategy so you can validate ideas at no cost.",
  },
  {
    q: "How do live broker connections work?",
    a: "You add API credentials, which are envelope-encrypted at rest. We verify them against the venue before enabling live routing. Live trading requires the Pro plan or above.",
  },
  {
    q: "Which brokers are supported?",
    a: "Zerodha Kite, Angel One SmartAPI, Delta Exchange, and MetaTrader 5 via a VPS agent, plus the built-in paper simulator.",
  },
  {
    q: "Can I bring my own strategies?",
    a: "Yes. Upload Python strategies that subclass the SDK Strategy class. Uploaded code is statically screened and restricted to paper mode until reviewed.",
  },
];

export function LandingPage() {
  const { data: plans } = usePlans();
  const status = useAuth((state) => state.status);
  const [cycle, setCycle] = useState<"monthly" | "yearly">("monthly");
  const appHref = status === "authenticated" ? "/app/dashboard" : "/register";

  return (
    <div className="min-h-screen bg-surface-50 text-slate-900 dark:bg-surface-950 dark:text-slate-100">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/80 backdrop-blur dark:border-surface-800 dark:bg-surface-950/80">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
          <div className="flex items-center gap-2 font-semibold">
            <div className="flex size-8 items-center justify-center rounded-lg bg-accent-600 text-white">
              A
            </div>
            Algo Matrics
          </div>
          <nav className="hidden items-center gap-6 text-sm text-slate-600 md:flex dark:text-slate-300">
            <a href="#features" className="hover:text-accent-500">
              Features
            </a>
            <a href="#pricing" className="hover:text-accent-500">
              Pricing
            </a>
            <a href="#faq" className="hover:text-accent-500">
              FAQ
            </a>
            <a href="#docs" className="hover:text-accent-500">
              Docs
            </a>
          </nav>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            {status === "authenticated" ? (
              <Link to="/app/dashboard">
                <Button size="sm">Open app</Button>
              </Link>
            ) : (
              <>
                <Link to="/login" className="hidden sm:block">
                  <Button variant="ghost" size="sm">
                    Sign in
                  </Button>
                </Link>
                <Link to="/register">
                  <Button size="sm">Get started</Button>
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-6xl px-4 py-20 text-center">
        <Badge color="blue" className="mx-auto">
          Multi-tenant algorithmic trading platform
        </Badge>
        <h1 className="mx-auto mt-5 max-w-3xl text-4xl font-bold tracking-tight sm:text-5xl">
          Automate strategies. Manage risk. Trade with confidence.
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-slate-600 dark:text-slate-300">
          Build, backtest, and deploy trading strategies across multiple brokers with a
          production-grade risk engine, real-time P&amp;L, and deterministic paper trading.
        </p>
        <div className="mt-8 flex justify-center gap-3">
          <Link to={appHref}>
            <Button size="lg">Start free with paper trading</Button>
          </Link>
          <a href="#pricing">
            <Button size="lg" variant="secondary">
              View pricing
            </Button>
          </a>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="mx-auto max-w-6xl px-4 py-16">
        <h2 className="text-center text-2xl font-semibold">Everything you need to trade systematically</h2>
        <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((feature) => (
            <div
              key={feature.title}
              className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-surface-800 dark:bg-surface-900"
            >
              <div className="flex size-10 items-center justify-center rounded-lg bg-accent-500/10 text-accent-500">
                <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" d={feature.icon} />
                </svg>
              </div>
              <h3 className="mt-4 font-semibold">{feature.title}</h3>
              <p className="mt-1.5 text-sm text-slate-600 dark:text-slate-400">{feature.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="mx-auto max-w-6xl px-4 py-16">
        <h2 className="text-center text-2xl font-semibold">Simple, transparent pricing</h2>
        <div className="mt-4 flex justify-center">
          <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-1 dark:border-surface-800 dark:bg-surface-900">
            {(["monthly", "yearly"] as const).map((option) => (
              <button
                key={option}
                onClick={() => setCycle(option)}
                className={
                  cycle === option
                    ? "rounded-md bg-white px-4 py-1.5 text-sm font-medium shadow-sm dark:bg-surface-800"
                    : "px-4 py-1.5 text-sm text-slate-500"
                }
              >
                {option === "monthly" ? "Monthly" : "Yearly (2 months free)"}
              </button>
            ))}
          </div>
        </div>
        <div className="mt-10 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {(plans ?? []).map((plan) => (
            <div
              key={plan.id}
              className={
                plan.code === "pro"
                  ? "relative rounded-xl border-2 border-accent-500 bg-white p-6 shadow-md dark:bg-surface-900"
                  : "rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-surface-800 dark:bg-surface-900"
              }
            >
              {plan.code === "pro" && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-accent-600 px-3 py-0.5 text-xs font-medium text-white">
                  Most popular
                </span>
              )}
              <h3 className="font-semibold">{plan.name}</h3>
              <p className="mt-1 text-sm text-slate-500">{plan.description}</p>
              <p className="mt-4 text-3xl font-bold tabular-nums">
                {money(cycle === "monthly" ? plan.price_monthly : plan.price_yearly, plan.currency)}
                <span className="text-sm font-normal text-slate-400">
                  /{cycle === "monthly" ? "mo" : "yr"}
                </span>
              </p>
              <ul className="mt-4 space-y-2 text-sm">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-2">
                    <span className="mt-0.5 text-profit-500">✓</span>
                    <span className="text-slate-600 dark:text-slate-300">{feature}</span>
                  </li>
                ))}
              </ul>
              <Link to={appHref} className="mt-6 block">
                <Button className="w-full" variant={plan.code === "pro" ? "primary" : "secondary"}>
                  {plan.code === "free" ? "Start free" : "Choose plan"}
                </Button>
              </Link>
            </div>
          ))}
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="mx-auto max-w-3xl px-4 py-16">
        <h2 className="text-center text-2xl font-semibold">Frequently asked questions</h2>
        <div className="mt-8 space-y-3">
          {FAQ.map((item) => (
            <details
              key={item.q}
              className="group rounded-xl border border-slate-200 bg-white p-4 dark:border-surface-800 dark:bg-surface-900"
            >
              <summary className="cursor-pointer list-none font-medium">
                {item.q}
                <span className="float-right text-slate-400 group-open:rotate-45">+</span>
              </summary>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      {/* Docs / blog placeholder + Contact */}
      <section id="docs" className="mx-auto max-w-6xl px-4 py-16">
        <div className="grid gap-6 md:grid-cols-3">
          <div className="rounded-xl border border-slate-200 bg-white p-6 dark:border-surface-800 dark:bg-surface-900">
            <h3 className="font-semibold">Documentation</h3>
            <p className="mt-1.5 text-sm text-slate-500">
              Architecture, API reference, and the strategy SDK live in the repository under{" "}
              <code className="text-accent-500">docs/</code>.
            </p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-6 dark:border-surface-800 dark:bg-surface-900">
            <h3 className="font-semibold">Blog</h3>
            <p className="mt-1.5 text-sm text-slate-500">
              Product updates and engineering deep-dives are coming soon.
            </p>
            <Badge color="amber" className="mt-3">
              Coming soon
            </Badge>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-6 dark:border-surface-800 dark:bg-surface-900">
            <h3 className="font-semibold">Contact</h3>
            <p className="mt-1.5 text-sm text-slate-500">
              Questions? Reach us at{" "}
              <a href="mailto:hello@algomatrics.local" className="text-accent-500 hover:underline">
                hello@algomatrics.local
              </a>
              .
            </p>
          </div>
        </div>
      </section>

      <footer className="border-t border-slate-200 py-8 text-center text-sm text-slate-400 dark:border-surface-800">
        <p>© {new Date().getFullYear()} Algo Matrics. Trade responsibly — capital is at risk.</p>
      </footer>
    </div>
  );
}
