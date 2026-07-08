import type { ReactNode } from "react";
import { Link } from "react-router";

import { ThemeToggle } from "@/components/ThemeToggle";

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
    <div className="flex min-h-screen bg-surface-50 dark:bg-surface-950">
      <div className="hidden flex-1 flex-col justify-between bg-gradient-to-br from-accent-700 via-accent-600 to-surface-900 p-12 text-white lg:flex">
        <Link to="/" className="flex items-center gap-2 text-lg font-semibold">
          <div className="flex size-8 items-center justify-center rounded-lg bg-white/20">A</div>
          Algo Matrics
        </Link>
        <div className="space-y-4">
          <h2 className="text-3xl font-semibold leading-tight">
            Automate strategies. Manage risk. Trade with confidence.
          </h2>
          <p className="max-w-md text-white/80">
            A multi-tenant algorithmic trading platform with paper and live execution, real-time
            P&amp;L, and hierarchical risk controls.
          </p>
        </div>
        <p className="text-sm text-white/60">
          Paper trading is fully simulated. Live trading requires an approved broker connection.
        </p>
      </div>
      <div className="flex flex-1 items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="mb-6 flex items-center justify-between lg:hidden">
            <Link to="/" className="flex items-center gap-2 font-semibold">
              <div className="flex size-7 items-center justify-center rounded-md bg-accent-600 text-white">
                A
              </div>
              Algo Matrics
            </Link>
            <ThemeToggle />
          </div>
          <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>}
          <div className="mt-6">{children}</div>
          {footer && <div className="mt-6 text-center text-sm text-slate-500">{footer}</div>}
        </div>
      </div>
    </div>
  );
}
