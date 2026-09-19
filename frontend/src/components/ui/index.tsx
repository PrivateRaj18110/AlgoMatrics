// Design-system primitives: hand-rolled Tailwind components, dark-mode aware.

import { clsx } from "clsx";
import {
  Component,
  type ErrorInfo,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
  forwardRef,
  useEffect,
} from "react";

import { useToasts } from "@/stores/toast";

/* ---------------------------------- Button --------------------------------- */

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "success";

// Primary is dark text on the bright accent: ~9:1 contrast, where white on the
// darker accent only managed ~3.5:1. Matches the marketing site's CTA.
const buttonStyles: Record<ButtonVariant, string> = {
  primary:
    "bg-accent-500 text-surface-950 shadow-[inset_0_1px_0_rgba(255,255,255,0.25),0_1px_2px_rgba(0,0,0,0.2)] hover:bg-accent-400 hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.3),0_8px_24px_-6px_rgba(34,184,212,0.45)] focus-visible:outline-accent-500 disabled:bg-accent-500/50",
  secondary:
    "border border-slate-200 bg-white text-slate-700 shadow-sm hover:border-slate-300 hover:bg-slate-50 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-200 dark:shadow-none dark:hover:border-white/20 dark:hover:bg-white/[0.07]",
  ghost:
    "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-white/[0.06] dark:hover:text-white",
  danger:
    "bg-loss-600 text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.15)] hover:bg-loss-500 focus-visible:outline-loss-500 disabled:bg-loss-600/50",
  success:
    "bg-profit-600 text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.15)] hover:bg-profit-500 focus-visible:outline-profit-500 disabled:bg-profit-600/50",
};

const buttonBase =
  "inline-flex items-center justify-center gap-2 rounded-lg font-medium whitespace-nowrap transition-[color,background-color,border-color,box-shadow,transform] duration-200 hover:-translate-y-px active:translate-y-0 focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-70 disabled:hover:translate-y-0";

const buttonSizes = {
  sm: "h-8 px-3 text-xs",
  md: "h-9 px-4 text-sm",
  lg: "h-11 px-5 text-sm",
} as const;

/** Button styling for a router `<Link>`, so links never have to nest a `<button>`. */
export function buttonClass({
  variant = "primary",
  size = "md",
  className,
}: {
  variant?: ButtonVariant;
  size?: keyof typeof buttonSizes;
  className?: string;
} = {}): string {
  return clsx(buttonBase, buttonSizes[size], buttonStyles[variant], className);
}

export function Button({
  children,
  variant = "primary",
  size = "md",
  loading = false,
  className,
  disabled,
  type = "button",
  ...rest
}: {
  children: ReactNode;
  variant?: ButtonVariant;
  size?: "sm" | "md" | "lg";
  loading?: boolean;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={buttonClass({ variant, size, className })}
      {...rest}
    >
      {loading && <Spinner className="size-3.5" />}
      {children}
    </button>
  );
}

/* ---------------------------------- Inputs --------------------------------- */

const fieldBase =
  "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-[inset_0_1px_1px_rgba(15,23,42,0.03)] transition-[border-color,box-shadow,background-color] duration-150 placeholder:text-slate-400 hover:border-slate-300 focus:border-accent-500 focus:outline-none focus:ring-4 focus:ring-accent-500/15 disabled:opacity-60 dark:border-white/10 dark:bg-surface-950/60 dark:text-slate-100 dark:shadow-none dark:placeholder:text-slate-500 dark:hover:border-white/20 dark:focus:border-accent-400 dark:focus:bg-surface-950";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...rest }, ref) {
    return <input ref={ref} className={clsx(fieldBase, className)} {...rest} />;
  },
);

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={clsx(fieldBase, "min-h-24", className)} {...rest} />;
});

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, children, ...rest }, ref) {
    return (
      <select ref={ref} className={clsx(fieldBase, "pr-8", className)} {...rest}>
        {children}
      </select>
    );
  },
);

export function Field({
  label,
  error,
  hint,
  children,
  required,
}: {
  label: string;
  error?: string;
  hint?: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-[13px] font-medium text-slate-700 dark:text-slate-300">
        {label}
        {required && <span className="text-loss-500"> *</span>}
      </span>
      {children}
      {hint && !error && (
        <span className="block text-xs text-slate-500 dark:text-slate-400">{hint}</span>
      )}
      {error && <span className="block text-xs font-medium text-loss-500">{error}</span>}
    </label>
  );
}

export function Switch({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={clsx(
        "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-50",
        checked ? "bg-accent-600" : "bg-slate-300 dark:bg-surface-700",
      )}
    >
      <span
        className={clsx(
          "inline-block size-4 transform rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-6" : "translate-x-1",
        )}
      />
    </button>
  );
}

/* --------------------------------- Surfaces --------------------------------- */

// One surface recipe for every panel in the console, so pages read as one system.
export const surface =
  "rounded-2xl border border-slate-200/80 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04),0_12px_32px_-18px_rgba(15,23,42,0.18)] dark:border-white/[0.07] dark:bg-surface-900/70 dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.035),0_24px_48px_-28px_rgba(0,0,0,0.7)]";

export function Card({
  children,
  className,
  title,
  subtitle,
  icon,
  actions,
  bodyClassName,
}: {
  children: ReactNode;
  className?: string;
  title?: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  bodyClassName?: string;
}) {
  return (
    <section className={clsx(surface, "transition-colors", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-3.5 dark:border-white/[0.06]">
          <div className="flex min-w-0 items-center gap-2.5">
            {icon && (
              <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-accent-500/10 text-accent-600 ring-1 ring-accent-500/20 ring-inset dark:text-accent-300">
                {icon}
              </span>
            )}
            <div className="min-w-0">
              <h3 className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
                {title}
              </h3>
              {subtitle && (
                <p className="truncate text-xs text-slate-500 dark:text-slate-400">{subtitle}</p>
              )}
            </div>
          </div>
          {actions}
        </header>
      )}
      <div className={clsx("p-5", bodyClassName)}>{children}</div>
    </section>
  );
}

type Tone = "accent" | "profit" | "loss" | "amber" | "violet" | "neutral";

const toneChip: Record<Tone, string> = {
  accent: "bg-accent-500/10 text-accent-600 ring-accent-500/20 dark:text-accent-300",
  profit: "bg-profit-500/10 text-profit-600 ring-profit-500/20 dark:text-profit-400",
  loss: "bg-loss-500/10 text-loss-600 ring-loss-500/20 dark:text-loss-400",
  amber: "bg-amber-500/10 text-amber-600 ring-amber-500/20 dark:text-amber-400",
  violet: "bg-violet-500/10 text-violet-600 ring-violet-500/20 dark:text-violet-300",
  neutral: "bg-slate-500/10 text-slate-600 ring-slate-500/20 dark:text-slate-300",
};

const toneGlow: Record<Tone, string> = {
  accent: "rgba(34, 184, 212, 0.13)",
  profit: "rgba(34, 197, 94, 0.12)",
  loss: "rgba(244, 63, 94, 0.12)",
  amber: "rgba(245, 158, 11, 0.12)",
  violet: "rgba(139, 92, 246, 0.12)",
  neutral: "rgba(148, 163, 184, 0.08)",
};

export function StatCard({
  label,
  value,
  sub,
  valueClass,
  icon,
  tone = "neutral",
  footer,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  valueClass?: string;
  icon?: ReactNode;
  tone?: Tone;
  footer?: ReactNode;
}) {
  return (
    <div
      className={clsx(surface, "am-glow relative overflow-hidden p-5")}
      style={{ "--am-glow": toneGlow[tone] } as React.CSSProperties}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-medium text-slate-500 dark:text-slate-400">{label}</p>
        {icon && (
          <span
            className={clsx(
              "flex size-8 shrink-0 items-center justify-center rounded-lg ring-1 ring-inset",
              toneChip[tone],
            )}
            aria-hidden
          >
            {icon}
          </span>
        )}
      </div>
      <p
        className={clsx(
          "mt-2 text-[1.625rem] leading-tight font-semibold tracking-tight tabular-nums",
          valueClass ?? "text-slate-900 dark:text-white",
        )}
      >
        {value}
      </p>
      {sub && <p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">{sub}</p>}
      {footer}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
}) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && (
          <p className="mb-1.5 font-mono text-[11px] font-medium tracking-[0.18em] text-accent-600 uppercase dark:text-accent-400">
            {eyebrow}
          </p>
        )}
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">
          {title}
        </h1>
        {description && (
          <p className="mt-1.5 max-w-2xl text-sm text-slate-500 dark:text-slate-400">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/* ---------------------------------- Badge ----------------------------------- */

const badgePalette: Record<string, string> = {
  slate:
    "bg-slate-100 text-slate-700 ring-slate-200 dark:bg-white/[0.06] dark:text-slate-300 dark:ring-white/10",
  green: "bg-profit-500/10 text-profit-700 ring-profit-500/25 dark:text-profit-400",
  red: "bg-loss-500/10 text-loss-700 ring-loss-500/25 dark:text-loss-400",
  amber: "bg-amber-500/10 text-amber-700 ring-amber-500/25 dark:text-amber-400",
  blue: "bg-accent-500/10 text-accent-700 ring-accent-500/25 dark:text-accent-300",
  violet: "bg-violet-500/10 text-violet-700 ring-violet-500/25 dark:text-violet-300",
};

const badgeDot: Record<string, string> = {
  slate: "bg-slate-400",
  green: "bg-profit-500",
  red: "bg-loss-500",
  amber: "bg-amber-500",
  blue: "bg-accent-500",
  violet: "bg-violet-500",
};

export function Badge({
  children,
  color = "slate",
  className,
  dot,
}: {
  children: ReactNode;
  color?: keyof typeof badgePalette;
  className?: string;
  dot?: boolean;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        badgePalette[color],
        className,
      )}
    >
      {dot && <span className={clsx("size-1.5 rounded-full", badgeDot[color])} aria-hidden />}
      {children}
    </span>
  );
}

export function statusColor(status: string): keyof typeof badgePalette {
  const green = new Set(["active", "verified", "filled", "running", "paid", "ok", "success"]);
  const red = new Set(["failed", "rejected", "suspended", "critical", "expired", "closed"]);
  const amber = new Set([
    "pending",
    "pending_risk",
    "trialing",
    "past_due",
    "paused",
    "warning",
    "cancel_pending",
    "partially_filled",
    "stopping",
    "starting",
    "open",
  ]);
  const blue = new Set(["submitted", "approved", "info", "paper"]);
  if (green.has(status)) return "green";
  if (red.has(status)) return "red";
  if (amber.has(status)) return "amber";
  if (blue.has(status)) return "blue";
  return "slate";
}

/* ---------------------------------- Table ------------------------------------ */

export function Table({
  headers,
  children,
  dense,
}: {
  headers: ReactNode[];
  children: ReactNode;
  dense?: boolean;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-max text-left text-sm">
        <thead>
          <tr className="border-b border-slate-100 text-[11px] tracking-wider text-slate-500 uppercase dark:border-white/[0.06] dark:text-slate-500">
            {headers.map((header, index) => (
              <th key={index} className={clsx("font-medium", dense ? "px-2 py-2" : "px-3 py-2.5")}>
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04] [&>tr]:transition-colors [&>tr:hover]:bg-slate-50/80 dark:[&>tr:hover]:bg-white/[0.025]">
          {children}
        </tbody>
      </table>
    </div>
  );
}

export function Td({
  children,
  className,
  dense,
  colSpan,
}: {
  children: ReactNode;
  className?: string;
  dense?: boolean;
  colSpan?: number;
}) {
  return (
    <td
      colSpan={colSpan}
      className={clsx(dense ? "px-2 py-1.5" : "px-3 py-2.5", "align-middle", className)}
    >
      {children}
    </td>
  );
}

/* --------------------------------- Feedback ----------------------------------- */

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={clsx("animate-spin text-current", className ?? "size-5")}
      viewBox="0 0 24 24"
      fill="none"
      aria-label="loading"
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="4" />
      <path
        d="M22 12a10 10 0 0 1-10 10"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={clsx("animate-pulse rounded-md bg-slate-200/80 dark:bg-white/[0.06]", className)}
    />
  );
}

export function SkeletonRows({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2 p-2">
      {Array.from({ length: rows }).map((_, row) => (
        <div key={row} className="flex gap-3">
          {Array.from({ length: cols }).map((_, col) => (
            <Skeleton key={col} className="h-5 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  body,
  action,
  icon,
}: {
  title: string;
  body?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <div className="relative mb-1 flex size-12 items-center justify-center rounded-2xl bg-gradient-to-b from-slate-50 to-slate-100 text-slate-400 ring-1 ring-slate-200 ring-inset dark:from-white/[0.06] dark:to-white/[0.02] dark:text-slate-400 dark:ring-white/10">
        {icon ?? (
          <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" aria-hidden>
            <path
              strokeLinecap="round"
              strokeWidth="1.5"
              d="M20 13V7a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v6m16 0v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-4m16 0h-5l-1.5 2h-3L9 13H4"
            />
          </svg>
        )}
      </div>
      <p className="text-sm font-medium text-slate-800 dark:text-slate-200">{title}</p>
      {body && (
        <p className="max-w-sm text-xs leading-relaxed text-slate-500 dark:text-slate-400">{body}</p>
      )}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

/* ---------------------------------- Modal ------------------------------------- */

export function Modal({
  open,
  onClose,
  title,
  children,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-950/60 p-4 backdrop-blur-sm sm:items-center"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div
        className={clsx(
          "am-fade-in my-8 w-full rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-white/10 dark:bg-surface-900",
          wide ? "max-w-3xl" : "max-w-lg",
        )}
      >
        <header className="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-white/[0.06]">
          <h2 className="text-sm font-semibold">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-white/[0.06] dark:hover:text-slate-200"
          >
            <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeWidth="2" d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </header>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  body,
  confirmLabel = "Confirm",
  danger,
  loading,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  body: string;
  confirmLabel?: string;
  danger?: boolean;
  loading?: boolean;
}) {
  return (
    <Modal open={open} onClose={onClose} title={title}>
      <p className="text-sm text-slate-600 dark:text-slate-300">{body}</p>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button variant={danger ? "danger" : "primary"} onClick={onConfirm} loading={loading}>
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}

/* ---------------------------------- Tabs -------------------------------------- */

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: Array<{ key: string; label: string }>;
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <div
      role="tablist"
      className="inline-flex flex-wrap gap-1 rounded-xl border border-slate-200 bg-slate-100/80 p-1 dark:border-white/[0.07] dark:bg-white/[0.03]"
    >
      {tabs.map((tab) => (
        <button
          key={tab.key}
          role="tab"
          aria-selected={active === tab.key}
          onClick={() => onChange(tab.key)}
          className={clsx(
            "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
            active === tab.key
              ? "bg-white text-slate-900 shadow-sm dark:bg-white/[0.09] dark:text-white dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
              : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200",
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

/* --------------------------------- Toaster ------------------------------------- */

export function Toaster() {
  const { toasts, dismiss } = useToasts();
  return (
    <div className="pointer-events-none fixed right-4 bottom-4 z-[60] flex w-80 flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          role="status"
          className={clsx(
            "am-fade-in pointer-events-auto rounded-xl border p-3 shadow-lg backdrop-blur-md",
            toast.kind === "success" &&
              "border-profit-500/40 bg-profit-500/10 text-profit-700 dark:text-profit-400",
            toast.kind === "error" &&
              "border-loss-500/40 bg-loss-500/10 text-loss-700 dark:text-loss-400",
            toast.kind === "info" &&
              "border-accent-500/40 bg-accent-500/10 text-accent-700 dark:text-accent-300",
          )}
        >
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-sm font-medium">{toast.title}</p>
              {toast.body && (
                <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-300">{toast.body}</p>
              )}
            </div>
            <button
              onClick={() => dismiss(toast.id)}
              className="text-xs opacity-60 hover:opacity-100"
              aria-label="Dismiss"
            >
              ✕
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------ Error boundary ---------------------------------- */

export class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("ui.error_boundary", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 p-8 text-center">
          <p className="text-lg font-semibold">Something went wrong</p>
          <p className="max-w-md text-sm text-slate-500">
            The view crashed unexpectedly. The error has been logged to the console.
          </p>
          <Button onClick={() => this.setState({ error: null })}>Try again</Button>
        </div>
      );
    }
    return this.props.children;
  }
}
