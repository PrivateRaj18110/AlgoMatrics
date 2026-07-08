const currencySymbols: Record<string, string> = {
  INR: "₹",
  USD: "$",
  EUR: "€",
  GBP: "£",
};

export function money(value: string | number | null | undefined, currency = "INR"): string {
  if (value === null || value === undefined || value === "") return "—";
  const amount = typeof value === "string" ? Number.parseFloat(value) : value;
  if (Number.isNaN(amount)) return "—";
  const symbol = currencySymbols[currency] ?? `${currency} `;
  const formatted = new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(amount));
  return `${amount < 0 ? "-" : ""}${symbol}${formatted}`;
}

export function num(value: string | number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || value === "") return "—";
  const amount = typeof value === "string" ? Number.parseFloat(value) : value;
  if (Number.isNaN(amount)) return "—";
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  }).format(amount);
}

export function pct(value: string | number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || value === "") return "—";
  const amount = typeof value === "string" ? Number.parseFloat(value) : value;
  if (Number.isNaN(amount)) return "—";
  return `${amount >= 0 ? "" : ""}${amount.toFixed(digits)}%`;
}

export function signed(value: string | number | null | undefined, currency = "INR"): string {
  if (value === null || value === undefined) return "—";
  const amount = typeof value === "string" ? Number.parseFloat(value) : value;
  if (Number.isNaN(amount)) return "—";
  const base = money(Math.abs(amount), currency);
  return amount > 0 ? `+${base}` : amount < 0 ? `-${base.replace("-", "")}` : base;
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function dateOnly(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function timeAgo(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value).getTime();
  if (Number.isNaN(parsed)) return "—";
  const seconds = Math.floor((Date.now() - parsed) / 1000);
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function toNumber(value: string | number | null | undefined): number {
  if (value === null || value === undefined) return 0;
  const parsed = typeof value === "string" ? Number.parseFloat(value) : value;
  return Number.isNaN(parsed) ? 0 : parsed;
}

export function pnlClass(value: string | number | null | undefined): string {
  const amount = toNumber(value);
  if (amount > 0) return "text-profit-500";
  if (amount < 0) return "text-loss-500";
  return "text-slate-500 dark:text-slate-400";
}
