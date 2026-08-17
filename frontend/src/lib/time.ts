/** Display timestamps using IANA time zones. Never add/subtract 5:30 manually. */

export type DisplayZone = "Asia/Kolkata" | "UTC";

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
