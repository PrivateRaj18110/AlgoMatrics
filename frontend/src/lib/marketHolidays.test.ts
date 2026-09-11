import { describe, expect, it } from "vitest";
import {
  getIndianMarketHoliday,
  INDIAN_CLEARING_HOLIDAYS,
  INDIAN_MARKET_HOLIDAYS,
  isIndianMarketHoliday,
  toKolkataDateString,
} from "./marketHolidays";

describe("marketHolidays", () => {
  it("converts dates to Kolkata YYYY-MM-DD strings properly", () => {
    // 2026-01-26 Republic Day
    const date = new Date("2026-01-26T06:00:00.000Z"); // 11:30 AM IST on Jan 26
    expect(toKolkataDateString(date)).toBe("2026-01-26");
  });

  it("identifies all 2026 official Indian equity trading holidays", () => {
    const expectedTradingHolidays2026 = [
      { date: "2026-01-15", name: "Municipal Corporation Election - Maharashtra" },
      { date: "2026-01-26", name: "Republic Day" },
      { date: "2026-02-15", name: "Mahashivratri" },
      { date: "2026-03-03", name: "Holi" },
      { date: "2026-03-21", name: "Id-Ul-Fitr" },
      { date: "2026-03-26", name: "Shri Ram Navami" },
      { date: "2026-03-31", name: "Shri Mahavir Jayanti" },
      { date: "2026-04-03", name: "Good Friday" },
      { date: "2026-04-14", name: "Dr. Baba Saheb Ambedkar Jayanti" },
      { date: "2026-05-01", name: "Maharashtra Day" },
      { date: "2026-05-28", name: "Bakri Id" },
      { date: "2026-06-26", name: "Muharram" },
      { date: "2026-08-15", name: "Independence Day" },
      { date: "2026-09-14", name: "Ganesh Chaturthi" },
      { date: "2026-10-02", name: "Mahatma Gandhi Jayanti" },
      { date: "2026-10-20", name: "Dussehra" },
      { date: "2026-11-08", name: "Diwali Laxmi Pujan" },
      { date: "2026-11-10", name: "Diwali-Balipratipada" },
      { date: "2026-11-24", name: "Prakash Gurpurb Sri Guru Nanak Dev" },
      { date: "2026-12-25", name: "Christmas" },
    ];

    for (const item of expectedTradingHolidays2026) {
      const dt = new Date(`${item.date}T05:00:00.000Z`);
      expect(isIndianMarketHoliday(dt), `Expected ${item.date} (${item.name}) to be trading holiday`).toBe(true);
      const h = getIndianMarketHoliday(dt);
      expect(h?.name).toBe(item.name);
      expect(h?.type).toBe("TRADING");
    }
  });

  it("handles 08-Nov-2026 as special Diwali Laxmi Pujan with Muhurat Trading note", () => {
    const diwali2026 = new Date("2026-11-08T05:00:00.000Z");
    expect(isIndianMarketHoliday(diwali2026)).toBe(true);
    const holiday = getIndianMarketHoliday(diwali2026);
    expect(holiday?.name).toBe("Diwali Laxmi Pujan");
    expect(holiday?.isMuhuratTrading).toBe(true);
    expect(holiday?.description).toContain("Muhurat Trading");
  });

  it("identifies clearing holidays separately from trading holidays", () => {
    // 2026-04-01 is Annual Bank Closing (Clearing Holiday only)
    const bankClosing = new Date("2026-04-01T05:00:00.000Z");
    expect(isIndianMarketHoliday(bankClosing, "TRADING")).toBe(false);
    expect(isIndianMarketHoliday(bankClosing, "CLEARING")).toBe(true);

    const clearingHoliday = getIndianMarketHoliday(bankClosing, "CLEARING");
    expect(clearingHoliday?.name).toBe("Annual Bank Closing");
    expect(clearingHoliday?.type).toBe("CLEARING");

    expect(INDIAN_CLEARING_HOLIDAYS.length).toBe(20);
  });

  it("returns null for ordinary trading days", () => {
    const normalTradingDay = new Date("2026-08-24T05:00:00.000Z"); // Monday, August 24, 2026
    expect(isIndianMarketHoliday(normalTradingDay)).toBe(false);
    expect(getIndianMarketHoliday(normalTradingDay)).toBeNull();
  });

  it("covers required holiday metadata fields", () => {
    expect(INDIAN_MARKET_HOLIDAYS.length).toBeGreaterThan(30);
    for (const h of INDIAN_MARKET_HOLIDAYS) {
      expect(h.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(h.name.length).toBeGreaterThan(0);
      expect(h.description.length).toBeGreaterThan(0);
      expect(h.type).toBe("TRADING");
    }
  });
});

