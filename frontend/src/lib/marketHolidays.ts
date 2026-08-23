/** Indian Market (NSE/BSE) Holidays Calendar Service */

export interface MarketHoliday {
  date: string; // YYYY-MM-DD
  name: string;
  description: string;
  isMuhuratTrading?: boolean;
}

/**
 * Official Indian Market (NSE/BSE) Trading Holidays.
 * Covers 2025, 2026, and 2027.
 */
export const INDIAN_MARKET_HOLIDAYS: MarketHoliday[] = [
  // 2025 Holidays
  { date: "2025-01-26", name: "Republic Day", description: "Republic Day (Sunday)" },
  { date: "2025-02-26", name: "Mahashivratri", description: "Mahashivratri" },
  { date: "2025-03-14", name: "Holi", description: "Holi (Festival of Colours)" },
  { date: "2025-03-31", name: "Id-Ul-Fitr", description: "Id-Ul-Fitr (Ramzan Id)" },
  { date: "2025-04-10", name: "Mahavir Jayanti", description: "Shri Mahavir Jayanti" },
  { date: "2025-04-14", name: "Dr. Baba Saheb Ambedkar Jayanti", description: "Dr. B.R. Ambedkar Jayanti" },
  { date: "2025-04-18", name: "Good Friday", description: "Good Friday" },
  { date: "2025-05-01", name: "Maharashtra Day", description: "Maharashtra Day" },
  { date: "2025-06-07", name: "Bakri Id", description: "Bakri Id (Id-Ul-Adha)" },
  { date: "2025-08-15", name: "Independence Day", description: "Independence Day" },
  { date: "2025-08-27", name: "Ganesh Chaturthi", description: "Shri Ganesh Chaturthi" },
  { date: "2025-10-02", name: "Mahatma Gandhi Jayanti", description: "Mahatma Gandhi Jayanti" },
  { date: "2025-10-21", name: "Diwali Laxmi Pujan", description: "Diwali *Laxmi Pujan (Muhurat Trading)", isMuhuratTrading: true },
  { date: "2025-10-22", name: "Diwali Balipratipada", description: "Diwali Balipratipada" },
  { date: "2025-11-05", name: "Prakash Gurpurb", description: "Guru Nanak Jayanti" },
  { date: "2025-12-25", name: "Christmas", description: "Christmas" },

  // 2026 Holidays
  { date: "2026-01-26", name: "Republic Day", description: "Republic Day" },
  { date: "2026-02-16", name: "Mahashivratri", description: "Mahashivratri" },
  { date: "2026-03-03", name: "Holi", description: "Holi (Festival of Colours)" },
  { date: "2026-03-20", name: "Id-Ul-Fitr", description: "Id-Ul-Fitr (Ramzan Id)" },
  { date: "2026-03-30", name: "Shri Ram Navami", description: "Shri Ram Navami" },
  { date: "2026-04-03", name: "Good Friday", description: "Good Friday" },
  { date: "2026-04-14", name: "Dr. Ambedkar Jayanti", description: "Dr. B.R. Ambedkar Jayanti" },
  { date: "2026-05-01", name: "Maharashtra Day", description: "Maharashtra Day" },
  { date: "2026-05-27", name: "Bakri Id", description: "Bakri Id (Id-Ul-Adha)" },
  { date: "2026-06-25", name: "Muharram", description: "Muharram" },
  { date: "2026-08-15", name: "Independence Day", description: "Independence Day (Saturday)" },
  { date: "2026-09-14", name: "Ganesh Chaturthi", description: "Shri Ganesh Chaturthi" },
  { date: "2026-10-02", name: "Mahatma Gandhi Jayanti", description: "Mahatma Gandhi Jayanti" },
  { date: "2026-10-20", name: "Dussehra", description: "Dussehra (Vijay Dashami)" },
  { date: "2026-11-08", name: "Diwali Laxmi Pujan", description: "Diwali *Laxmi Pujan (Muhurat Trading)", isMuhuratTrading: true },
  { date: "2026-11-10", name: "Diwali Balipratipada", description: "Diwali Balipratipada" },
  { date: "2026-11-24", name: "Guru Nanak Jayanti", description: "Guru Nanak Jayanti" },
  { date: "2026-12-25", name: "Christmas", description: "Christmas" },

  // 2027 Holidays
  { date: "2027-01-26", name: "Republic Day", description: "Republic Day" },
  { date: "2027-03-08", name: "Mahashivratri", description: "Mahashivratri" },
  { date: "2027-03-23", name: "Holi", description: "Holi" },
  { date: "2027-03-26", name: "Good Friday", description: "Good Friday" },
  { date: "2027-04-14", name: "Dr. Ambedkar Jayanti", description: "Dr. B.R. Ambedkar Jayanti" },
  { date: "2027-05-01", name: "Maharashtra Day", description: "Maharashtra Day (Saturday)" },
  { date: "2027-08-15", name: "Independence Day", description: "Independence Day (Sunday)" },
  { date: "2027-10-02", name: "Mahatma Gandhi Jayanti", description: "Mahatma Gandhi Jayanti (Saturday)" },
  { date: "2027-10-10", name: "Dussehra", description: "Dussehra" },
  { date: "2027-10-29", name: "Diwali Laxmi Pujan", description: "Diwali *Laxmi Pujan (Muhurat Trading)", isMuhuratTrading: true },
  { date: "2027-12-25", name: "Christmas", description: "Christmas (Saturday)" },
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

/** Check if a given date is an official Indian market holiday. */
export function getIndianMarketHoliday(date: Date): MarketHoliday | null {
  const dateStr = toKolkataDateString(date);
  return INDIAN_MARKET_HOLIDAYS.find((h) => h.date === dateStr) ?? null;
}

/** Returns true if the date is an Indian market holiday. */
export function isIndianMarketHoliday(date: Date): boolean {
  return getIndianMarketHoliday(date) !== null;
}
