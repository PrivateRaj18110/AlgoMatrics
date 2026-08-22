import type { MarketRegion } from "@/lib/marketRegion";
import { regionZone } from "@/lib/marketRegion";

export interface MarketSession {
  id: string;
  region: MarketRegion;
  venue: string;
  timezone: "Asia/Kolkata" | "America/New_York";
  /** Civil clock in the venue timezone (not UTC arithmetic). */
  openHour: number;
  openMinute: number;
  closeHour: number;
  closeMinute: number;
  weekdays: number[];
}

export const MARKET_SESSIONS: MarketSession[] = [
  {
    id: "nse-bse",
    region: "india",
    venue: "NSE / BSE",
    timezone: "Asia/Kolkata",
    openHour: 9,
    openMinute: 15,
    closeHour: 15,
    closeMinute: 30,
    weekdays: [1, 2, 3, 4, 5],
  },
  {
    id: "us-cash",
    region: "international",
    venue: "NYSE / NASDAQ",
    timezone: "America/New_York",
    openHour: 9,
    openMinute: 30,
    closeHour: 16,
    closeMinute: 0,
    weekdays: [1, 2, 3, 4, 5],
  },
];

export function weekdayInZone(date: Date, timeZone: string): number {
  const weekday = new Intl.DateTimeFormat("en-US", { timeZone, weekday: "short" }).format(date);
  return { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 }[weekday] ?? 0;
}

export function civilDateInZone(date: Date, timeZone: string): { year: number; month: number; day: number } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const lookup = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return {
    year: Number(lookup.year),
    month: Number(lookup.month),
    day: Number(lookup.day),
  };
}

export function sessionsForDay(date: Date, region?: MarketRegion): MarketSession[] {
  return MARKET_SESSIONS.filter((session) => {
    if (region && session.region !== region) return false;
    const weekday = weekdayInZone(date, session.timezone);
    return session.weekdays.includes(weekday);
  });
}

export function formatSessionWindow(session: MarketSession): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  const zone = regionZone(session.region);
  return `${pad(session.openHour)}:${pad(session.openMinute)}–${pad(session.closeHour)}:${pad(session.closeMinute)} ${zone}`;
}

export function startOfWeek(date: Date): Date {
  const copy = new Date(date);
  const day = copy.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  copy.setDate(copy.getDate() + diff);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

export function addDays(date: Date, days: number): Date {
  const copy = new Date(date);
  copy.setDate(copy.getDate() + days);
  return copy;
}
