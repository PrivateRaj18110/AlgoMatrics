import type { ReactNode } from "react";
import { Link } from "react-router";

import { BrandMark } from "@/components/BrandMark";
import { Glyph, type GlyphName } from "@/components/icons";

const PILLARS: Array<{ icon: GlyphName; title: string; body: string }> = [
  { icon: "flask", title: "Research", body: "Backtests and walk-forward validation" },
  { icon: "shield", title: "Risk", body: "Limits and kill switches enforced server-side" },
  { icon: "bolt", title: "Execution", body: "Broker routing with a full audit trail" },
  { icon: "radar", title: "Monitoring", body: "Strategy, execution and system telemetry" },
];

// The auth screens are always dark, like the marketing site they are reached
// from. The `dark` class on the root makes every shared form primitive inside
// render its dark variant too — otherwise light-theme users got white inputs
// on a near-black page.
export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="dark relative min-h-screen bg-surface-950 text-slate-100">
      {/* Decoration lives in its own clipped layer. Clipping the page root instead
          made it a scroll container, and focusing an input scrolled the whole
          layout sideways to reveal the off-screen glow. */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
        <div className="am-grid am-radial absolute inset-0" />
        <div className="absolute -top-40 right-[-10%] size-[36rem] rounded-full bg-accent-500/10 blur-3xl" />
        <div className="absolute bottom-[-20%] left-[-10%] size-[30rem] rounded-full bg-indigo-500/[0.07] blur-3xl" />
      </div>

      <div className="relative mx-auto grid min-h-screen max-w-7xl lg:grid-cols-[1.1fr_0.9fr]">
        <aside className="hidden flex-col justify-between p-12 lg:flex xl:p-16">
          <BrandMark className="text-slate-100" />

          <div className="am-reveal max-w-lg">
            <p className="font-mono text-[11px] tracking-[0.28em] text-accent-400">
              QUANTITATIVE INFRASTRUCTURE
            </p>
            <h2 className="mt-5 text-4xl leading-[1.1] font-semibold tracking-tight text-white xl:text-5xl">
              Algorithmic Intelligence.
              <br />
              <span className="bg-gradient-to-r from-accent-300 via-accent-400 to-indigo-300 bg-clip-text text-transparent">
                Built for Speed.
              </span>
            </h2>
            <p className="mt-5 text-[15px] leading-relaxed text-slate-400">
              Research, risk, execution and monitoring on one institutional control plane. Paper
              remains simulated. Live trading requires an approved broker connection and
              server-side authorization.
            </p>

            <ul className="mt-10 grid grid-cols-2 gap-3">
              {PILLARS.map((pillar) => (
                <li
                  key={pillar.title}
                  className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4 backdrop-blur-sm"
                >
                  <span className="flex size-8 items-center justify-center rounded-lg bg-accent-500/10 text-accent-300 ring-1 ring-accent-500/20 ring-inset">
                    <Glyph name={pillar.icon} />
                  </span>
                  <p className="mt-3 text-sm font-medium text-slate-100">{pillar.title}</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-slate-500">{pillar.body}</p>
                </li>
              ))}
            </ul>
          </div>

          <p className="flex items-center gap-2 text-xs text-slate-500">
            <Glyph name="lock" className="size-3.5" />
            Sessions use short-lived access tokens. Refresh credentials stay on the server.
          </p>
        </aside>

        <main className="flex items-center justify-center px-4 py-10 sm:px-6 lg:py-12">
          <div className="am-reveal w-full max-w-[26rem]">
            <div className="mb-8 flex justify-center lg:hidden">
              <BrandMark className="text-slate-100" />
            </div>
            <div className="relative rounded-2xl border border-white/10 bg-surface-900/70 p-7 shadow-[0_30px_80px_-30px_rgba(0,0,0,0.8),inset_0_1px_0_rgba(255,255,255,0.05)] backdrop-blur-xl sm:p-8">
              <div className="am-hairline absolute inset-x-8 -top-px h-px" aria-hidden />
              <h1 className="text-2xl font-semibold tracking-tight text-white">{title}</h1>
              {subtitle && <p className="mt-1.5 text-sm text-slate-400">{subtitle}</p>}
              <div className="mt-7">{children}</div>
            </div>
            {footer && <div className="mt-6 text-center text-sm text-slate-500">{footer}</div>}
            <p className="mt-8 flex items-center justify-center gap-5 text-xs">
              <Link
                to="/"
                className="inline-flex items-center gap-1.5 text-slate-500 transition-colors hover:text-slate-300"
              >
                <Glyph name="arrowLeft" className="size-3.5" />
                Back to algomatrics.in
              </Link>
              <Link
                to="/contact"
                className="inline-flex items-center gap-1.5 text-slate-500 transition-colors hover:text-slate-300"
              >
                <Glyph name="mail" className="size-3.5" />
                Contact
              </Link>
            </p>
          </div>
        </main>
      </div>
    </div>
  );
}
