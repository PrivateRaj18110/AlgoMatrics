/** Display timestamps using IANA time zones. Never add/subtract 5:30 manually. */

export type DisplayZone = "Asia/Kolkata" | "UTC" | "America/New_York" | "Europe/London";

export const TRADING_ZONE: DisplayZone = "Asia/Kolkata";
export const INFRA_ZONE: DisplayZone = "UTC";

export function formatInZone(
  value: string | Date | null | undefined,
  timeZone: DisplayZone = TRADING_ZONE,
  options: Intl.DateTimeFormatOptions = {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  },
): string {
  if (value === null || value === undefined || value === "") return "—";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-IN", { ...options, timeZone }).format(date);
}

export function formatTradingTime(value: string | Date | null | undefined): string {
  return formatInZone(value, TRADING_ZONE);
}

export function formatUtcTime(value: string | Date | null | undefined): string {
  return formatInZone(value, INFRA_ZONE);
}

export function formatHealthAge(
  value: string | Date | null | undefined,
  nowMs: number = Date.now()
): string {
  if (value === null || value === undefined || value === "") return "No data";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "No data";
  const elapsedSec = Math.max(0, Math.floor((nowMs - date.getTime()) / 1000));
  if (elapsedSec < 60) {
    return `${elapsedSec} seconds ago`;
  }
  const minutes = Math.floor(elapsedSec / 60);
  if (minutes < 60) {
    const sec = elapsedSec % 60;
    return sec > 0 ? `${minutes}m ${sec}s ago` : `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  const remMin = minutes % 60;
  if (hours < 24) {
    return remMin > 0 ? `${hours}h ${remMin}m` : `${hours}h`;
  }
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
