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

const buttonStyles: Record<ButtonVariant, string> = {
  primary:
    "bg-accent-600 text-white hover:bg-accent-500 focus-visible:outline-accent-500 disabled:bg-accent-600/50",
  secondary:
    "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 dark:border-surface-700 dark:bg-surface-850 dark:text-slate-200 dark:hover:bg-surface-800",
  ghost:
    "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-surface-800 dark:hover:text-white",
  danger:
    "bg-loss-600 text-white hover:bg-loss-500 focus-visible:outline-loss-500 disabled:bg-loss-600/50",
  success:
    "bg-profit-600 text-white hover:bg-profit-500 focus-visible:outline-profit-500 disabled:bg-profit-600/50",
};

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
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-70",
        size === "sm" && "px-2.5 py-1.5 text-xs",
        size === "md" && "px-3.5 py-2 text-sm",
        size === "lg" && "px-5 py-2.5 text-sm",
        buttonStyles[variant],
        className,
      )}
      {...rest}
    >
      {loading && <Spinner className="size-3.5" />}
      {children}
    </button>
  );
}

/* ---------------------------------- Inputs --------------------------------- */

const fieldBase =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-500/30 disabled:opacity-60 dark:border-surface-700 dark:bg-surface-900 dark:text-slate-100";

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
      <span className="text-xs font-medium tracking-wide text-slate-600 uppercase dark:text-slate-400">
        {label}
        {required && <span className="text-loss-500"> *</span>}
      </span>
      {children}
      {hint && !error && <span className="block text-xs text-slate-400">{hint}</span>}
      {error && <span className="block text-xs text-loss-500">{error}</span>}
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

export function Card({
  children,
  className,
  title,
  actions,
}: {
  children: ReactNode;
  className?: string;
  title?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section
      className={clsx(
        "rounded-xl border border-slate-200 bg-white shadow-sm dark:border-surface-800 dark:bg-surface-900",
        className,
      )}
    >
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-surface-800">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</h3>
          {actions}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function StatCard({
  label,
  value,
  sub,
  valueClass,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  valueClass?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-surface-800 dark:bg-surface-900">
      <p className="text-xs font-medium tracking-wide text-slate-500 uppercase dark:text-slate-400">
        {label}
      </p>
      <p className={clsx("mt-1.5 text-2xl font-semibold tabular-nums", valueClass)}>{value}</p>
      {sub && <p className="mt-1 text-xs text-slate-400">{sub}</p>}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-white">{title}</h1>
        {description && (
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

/* ---------------------------------- Badge ----------------------------------- */

const badgePalette: Record<string, string> = {
  slate: "bg-slate-100 text-slate-700 dark:bg-surface-800 dark:text-slate-300",
  green: "bg-profit-500/15 text-profit-600 dark:text-profit-400",
  red: "bg-loss-500/15 text-loss-600 dark:text-loss-400",
  amber: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
  blue: "bg-accent-500/15 text-accent-600 dark:text-accent-300",
  violet: "bg-violet-500/15 text-violet-600 dark:text-violet-400",
};

export function Badge({
  children,
  color = "slate",
  className,
}: {
  children: ReactNode;
  color?: keyof typeof badgePalette;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        badgePalette[color],
        className,
      )}
    >
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
          <tr className="border-b border-slate-200 text-xs tracking-wide text-slate-500 uppercase dark:border-surface-800 dark:text-slate-400">
            {headers.map((header, index) => (
              <th key={index} className={clsx("font-medium", dense ? "px-2 py-2" : "px-3 py-2.5")}>
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-surface-800/60">{children}</tbody>
      </table>
    </div>
  );
}

export function Td({
  children,
  className,
  dense,
}: {
  children: ReactNode;
  className?: string;
  dense?: boolean;
}) {
  return (
    <td className={clsx(dense ? "px-2 py-1.5" : "px-3 py-2.5", "align-middle", className)}>
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
      className={clsx("animate-pulse rounded-md bg-slate-200 dark:bg-surface-800", className)}
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
}: {
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <div className="flex size-10 items-center justify-center rounded-full bg-slate-100 text-slate-400 dark:bg-surface-800">
        <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeWidth="1.5"
            d="M20 13V7a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v6m16 0v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-4m16 0h-5l-1.5 2h-3L9 13H4"
          />
        </svg>
      </div>
      <p className="text-sm font-medium text-slate-700 dark:text-slate-200">{title}</p>
      {body && <p className="max-w-sm text-xs text-slate-500 dark:text-slate-400">{body}</p>}
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
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4 backdrop-blur-sm sm:items-center"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div
        className={clsx(
          "my-8 w-full rounded-xl border border-slate-200 bg-white shadow-2xl dark:border-surface-700 dark:bg-surface-900",
          wide ? "max-w-3xl" : "max-w-lg",
        )}
      >
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3.5 dark:border-surface-800">
          <h2 className="text-sm font-semibold">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-surface-800"
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
      className="flex flex-wrap gap-1 rounded-lg border border-slate-200 bg-slate-100 p-1 dark:border-surface-800 dark:bg-surface-900"
    >
      {tabs.map((tab) => (
        <button
          key={tab.key}
          role="tab"
          aria-selected={active === tab.key}
          onClick={() => onChange(tab.key)}
          className={clsx(
            "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
            active === tab.key
              ? "bg-white text-slate-900 shadow-sm dark:bg-surface-800 dark:text-white"
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
            "pointer-events-auto rounded-lg border p-3 shadow-lg backdrop-blur",
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
