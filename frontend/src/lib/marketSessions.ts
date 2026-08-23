import type { MarketRegion } from "@/lib/marketRegion";
import { regionZone } from "@/lib/marketRegion";
import { getIndianMarketHoliday } from "@/lib/marketHolidays";

export type SessionPhase = "pre" | "main" | "post";

export interface MarketSessionWindow {
  id: string;
  name: string;
  description: string;
  phase: SessionPhase;
  timezone: "Asia/Kolkata";
  startHour: number;
  startMinute: number;
  endHour: number;
  endMinute: number;
  startTime: string; // "09:00"
  endTime: string;   // "09:15"
}

export interface MarketSession {
  id: string;
  region: MarketRegion;
  venue: string;
  timezone: "Asia/Kolkata" | "America/New_York";
  openHour: number;
  openMinute: number;
  closeHour: number;
  closeMinute: number;
  weekdays: number[];
}

/** Standard Indian Market session windows */
export const INDIAN_MARKET_WINDOWS: MarketSessionWindow[] = [
  {
    id: "india-pre-market",
    name: "Pre-Market",
    description: "Indian market pre-open session",
    phase: "pre",
    timezone: "Asia/Kolkata",
    startHour: 9,
    startMinute: 0,
    endHour: 9,
    endMinute: 15,
    startTime: "09:00",
    endTime: "09:15",
  },
  {
    id: "india-market-hours",
    name: "Market Hours",
    description: "Indian equity/derivatives market",
    phase: "main",
    timezone: "Asia/Kolkata",
    startHour: 9,
    startMinute: 15,
    endHour: 15,
    endMinute: 15,
    startTime: "09:15",
    endTime: "15:15",
  },
  {
    id: "india-cash-market",
    name: "Cash Market",
    description: "Post-market / cash market window",
    phase: "post",
    timezone: "Asia/Kolkata",
    startHour: 15,
    startMinute: 15,
    endHour: 15,
    endMinute: 45,
    startTime: "15:15",
    endTime: "15:45",
  },
];

export const MARKET_SESSIONS: MarketSession[] = [
  {
    id: "nse-bse",
    region: "india",
    venue: "NSE / BSE",
    timezone: "Asia/Kolkata",
    openHour: 9,
    openMinute: 0,
    closeHour: 15,
    closeMinute: 45,
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

export type DayMarketStatus =
  | { type: "open"; windows: MarketSessionWindow[] }
  | { type: "weekend"; reason: "Market Closed" }
  | { type: "holiday"; reason: string; holidayName: string };

/** Determine the Indian market schedule status for a given day in Asia/Kolkata. */
export function getIndianMarketDaySchedule(date: Date): DayMarketStatus {
  const weekday = weekdayInZone(date, "Asia/Kolkata");
  if (weekday === 0 || weekday === 6) {
    return { type: "weekend", reason: "Market Closed" };
  }

  const holiday = getIndianMarketHoliday(date);
  if (holiday) {
    return {
      type: "holiday",
      reason: `Market Closed — ${holiday.name}`,
      holidayName: holiday.name,
    };
  }

  return {
    type: "open",
    windows: INDIAN_MARKET_WINDOWS,
  };
}

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

export function startOfWeek(date: Date, weekStartsOn: 0 | 1 = 0): Date {
  const copy = new Date(date);
  const day = copy.getDay();
  const diff = weekStartsOn === 0 ? -day : (day === 0 ? -6 : 1 - day);
  copy.setDate(copy.getDate() + diff);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

export function addDays(date: Date, days: number): Date {
  const copy = new Date(date);
  copy.setDate(copy.getDate() + days);
  return copy;
}
