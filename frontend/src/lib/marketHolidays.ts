/** Indian Market (NSE/BSE) Holidays Calendar Service */

export type HolidayType = "TRADING" | "CLEARING";

export interface MarketHoliday {
  date: string; // YYYY-MM-DD
  name: string;
  description: string;
  isMuhuratTrading?: boolean;
  type?: HolidayType;
}

/**
 * Official Indian Market (NSE/BSE) Equity Trading Holidays.
 * Covers 2025, 2026, and 2027.
 */
export const INDIAN_MARKET_HOLIDAYS: MarketHoliday[] = [
  // 2025 Holidays
  { date: "2025-01-26", name: "Republic Day", description: "Republic Day (Sunday)", type: "TRADING" },
  { date: "2025-02-26", name: "Mahashivratri", description: "Mahashivratri", type: "TRADING" },
  { date: "2025-03-14", name: "Holi", description: "Holi (Festival of Colours)", type: "TRADING" },
  { date: "2025-03-31", name: "Id-Ul-Fitr", description: "Id-Ul-Fitr (Ramzan Id)", type: "TRADING" },
  { date: "2025-04-10", name: "Mahavir Jayanti", description: "Shri Mahavir Jayanti", type: "TRADING" },
  { date: "2025-04-14", name: "Dr. Baba Saheb Ambedkar Jayanti", description: "Dr. B.R. Ambedkar Jayanti", type: "TRADING" },
  { date: "2025-04-18", name: "Good Friday", description: "Good Friday", type: "TRADING" },
  { date: "2025-05-01", name: "Maharashtra Day", description: "Maharashtra Day", type: "TRADING" },
  { date: "2025-06-07", name: "Bakri Id", description: "Bakri Id (Id-Ul-Adha)", type: "TRADING" },
  { date: "2025-08-15", name: "Independence Day", description: "Independence Day", type: "TRADING" },
  { date: "2025-08-27", name: "Ganesh Chaturthi", description: "Shri Ganesh Chaturthi", type: "TRADING" },
  { date: "2025-10-02", name: "Mahatma Gandhi Jayanti", description: "Mahatma Gandhi Jayanti", type: "TRADING" },
  { date: "2025-10-21", name: "Diwali Laxmi Pujan", description: "Diwali *Laxmi Pujan (Muhurat Trading)", isMuhuratTrading: true, type: "TRADING" },
  { date: "2025-10-22", name: "Diwali Balipratipada", description: "Diwali Balipratipada", type: "TRADING" },
  { date: "2025-11-05", name: "Prakash Gurpurb", description: "Guru Nanak Jayanti", type: "TRADING" },
  { date: "2025-12-25", name: "Christmas", description: "Christmas", type: "TRADING" },

  // 2026 Official Equity Trading Holidays
  { date: "2026-01-15", name: "Municipal Corporation Election - Maharashtra", description: "Municipal Corporation Election - Maharashtra", type: "TRADING" },
  { date: "2026-01-26", name: "Republic Day", description: "Republic Day", type: "TRADING" },
  { date: "2026-02-15", name: "Mahashivratri", description: "Mahashivratri (Sunday)", type: "TRADING" },
  { date: "2026-03-03", name: "Holi", description: "Holi", type: "TRADING" },
  { date: "2026-03-21", name: "Id-Ul-Fitr", description: "Id-Ul-Fitr (Ramadan Eid - Saturday)", type: "TRADING" },
  { date: "2026-03-26", name: "Shri Ram Navami", description: "Shri Ram Navami", type: "TRADING" },
  { date: "2026-03-31", name: "Shri Mahavir Jayanti", description: "Shri Mahavir Jayanti", type: "TRADING" },
  { date: "2026-04-03", name: "Good Friday", description: "Good Friday", type: "TRADING" },
  { date: "2026-04-14", name: "Dr. Baba Saheb Ambedkar Jayanti", description: "Dr. Baba Saheb Ambedkar Jayanti", type: "TRADING" },
  { date: "2026-05-01", name: "Maharashtra Day", description: "Maharashtra Day", type: "TRADING" },
  { date: "2026-05-28", name: "Bakri Id", description: "Bakri Id", type: "TRADING" },
  { date: "2026-06-26", name: "Muharram", description: "Muharram", type: "TRADING" },
  { date: "2026-08-15", name: "Independence Day", description: "Independence Day (Saturday)", type: "TRADING" },
  { date: "2026-09-14", name: "Ganesh Chaturthi", description: "Ganesh Chaturthi", type: "TRADING" },
  { date: "2026-10-02", name: "Mahatma Gandhi Jayanti", description: "Mahatma Gandhi Jayanti", type: "TRADING" },
  { date: "2026-10-20", name: "Dussehra", description: "Dussehra", type: "TRADING" },
  { date: "2026-11-08", name: "Diwali Laxmi Pujan", description: "Diwali Laxmi Pujan (Muhurat Trading applies - timings separately notified)", isMuhuratTrading: true, type: "TRADING" },
  { date: "2026-11-10", name: "Diwali-Balipratipada", description: "Diwali-Balipratipada", type: "TRADING" },
  { date: "2026-11-24", name: "Prakash Gurpurb Sri Guru Nanak Dev", description: "Prakash Gurpurb Sri Guru Nanak Dev", type: "TRADING" },
  { date: "2026-12-25", name: "Christmas", description: "Christmas", type: "TRADING" },

  // 2027 Holidays
  { date: "2027-01-26", name: "Republic Day", description: "Republic Day", type: "TRADING" },
  { date: "2027-03-08", name: "Mahashivratri", description: "Mahashivratri", type: "TRADING" },
  { date: "2027-03-23", name: "Holi", description: "Holi", type: "TRADING" },
  { date: "2027-03-26", name: "Good Friday", description: "Good Friday", type: "TRADING" },
  { date: "2027-04-14", name: "Dr. Ambedkar Jayanti", description: "Dr. B.R. Ambedkar Jayanti", type: "TRADING" },
  { date: "2027-05-01", name: "Maharashtra Day", description: "Maharashtra Day (Saturday)", type: "TRADING" },
  { date: "2027-08-15", name: "Independence Day", description: "Independence Day (Sunday)", type: "TRADING" },
  { date: "2027-10-02", name: "Mahatma Gandhi Jayanti", description: "Mahatma Gandhi Jayanti (Saturday)", type: "TRADING" },
  { date: "2027-10-10", name: "Dussehra", description: "Dussehra", type: "TRADING" },
  { date: "2027-10-29", name: "Diwali Laxmi Pujan", description: "Diwali *Laxmi Pujan (Muhurat Trading)", isMuhuratTrading: true, type: "TRADING" },
  { date: "2027-12-25", name: "Christmas", description: "Christmas (Saturday)", type: "TRADING" },
];

/**
 * Official Indian Market (NSE/BSE) Clearing Holidays.
 * Distinct from Trading Holidays.
 */
export const INDIAN_CLEARING_HOLIDAYS: MarketHoliday[] = [
  { date: "2026-01-15", name: "Municipal Corporation Election in Maharashtra", description: "Municipal Corporation Election in Maharashtra", type: "CLEARING" },
  { date: "2026-01-26", name: "Republic Day", description: "Republic Day", type: "CLEARING" },
  { date: "2026-02-19", name: "Chhatrapati Shivaji Maharaj Jayanti", description: "Chhatrapati Shivaji Maharaj Jayanti", type: "CLEARING" },
  { date: "2026-03-03", name: "Holi (Second Day)", description: "Holi (Second Day)", type: "CLEARING" },
  { date: "2026-03-19", name: "Gudhi Padwa", description: "Gudhi Padwa", type: "CLEARING" },
  { date: "2026-03-26", name: "Ram Navami", description: "Ram Navami", type: "CLEARING" },
  { date: "2026-03-31", name: "Mahavir Jayanti", description: "Mahavir Jayanti", type: "CLEARING" },
  { date: "2026-04-01", name: "Annual Bank Closing", description: "Annual Bank Closing", type: "CLEARING" },
  { date: "2026-04-03", name: "Good Friday", description: "Good Friday", type: "CLEARING" },
  { date: "2026-04-14", name: "Dr. Babasaheb Ambedkar Jayanti", description: "Dr. Babasaheb Ambedkar Jayanti", type: "CLEARING" },
  { date: "2026-05-01", name: "Maharashtra Din / Buddha Pournima", description: "Maharashtra Din / Buddha Pournima", type: "CLEARING" },
  { date: "2026-05-28", name: "Bakri ID (Id-Uz-Zuha)", description: "Bakri ID (Id-Uz-Zuha)", type: "CLEARING" },
  { date: "2026-06-26", name: "Muharram", description: "Muharram", type: "CLEARING" },
  { date: "2026-08-26", name: "Id-E-Milad", description: "Id-E-Milad", type: "CLEARING" },
  { date: "2026-09-14", name: "Ganesh Chaturthi", description: "Ganesh Chaturthi", type: "CLEARING" },
  { date: "2026-10-02", name: "Mahatma Gandhi Jayanti", description: "Mahatma Gandhi Jayanti", type: "CLEARING" },
  { date: "2026-10-20", name: "Dussehra", description: "Dussehra", type: "CLEARING" },
  { date: "2026-11-10", name: "Diwali (Bali Pratipada)", description: "Diwali (Bali Pratipada)", type: "CLEARING" },
  { date: "2026-11-24", name: "Guru Nanak Jayanti", description: "Guru Nanak Jayanti", type: "CLEARING" },
  { date: "2026-12-25", name: "Christmas", description: "Christmas", type: "CLEARING" },
];

/** Convert a Date object to YYYY-MM-DD in Asia/Kolkata timezone. */
export function toKolkataDateString(date: Date): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const lookup = Object.fromEntries(parts.map((p) => [p.type, p.value]));
  return `${lookup.year}-${lookup.month}-${lookup.day}`;
}

/** Check if a given date is an official Indian market trading holiday. */
export function getIndianMarketHoliday(date: Date, type: HolidayType = "TRADING"): MarketHoliday | null {
  const dateStr = toKolkataDateString(date);
  const list = type === "CLEARING" ? INDIAN_CLEARING_HOLIDAYS : INDIAN_MARKET_HOLIDAYS;
  return list.find((h) => h.date === dateStr) ?? null;
}

/** Returns true if the date is an Indian market holiday. */
export function isIndianMarketHoliday(date: Date, type: HolidayType = "TRADING"): boolean {
  return getIndianMarketHoliday(date, type) !== null;
}
