import { describe, expect, it } from "vitest";
import {
  getIndianMarketHoliday,
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

  it("identifies known Indian market holidays correctly", () => {
    const repDay2026 = new Date("2026-01-26T05:00:00.000Z");
    expect(isIndianMarketHoliday(repDay2026)).toBe(true);
    const holiday = getIndianMarketHoliday(repDay2026);
    expect(holiday?.name).toBe("Republic Day");

    const diwali2026 = new Date("2026-11-08T05:00:00.000Z");
    expect(isIndianMarketHoliday(diwali2026)).toBe(true);
    expect(getIndianMarketHoliday(diwali2026)?.isMuhuratTrading).toBe(true);

    const christmas2026 = new Date("2026-12-25T05:00:00.000Z");
    expect(isIndianMarketHoliday(christmas2026)).toBe(true);
    expect(getIndianMarketHoliday(christmas2026)?.name).toBe("Christmas");
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
    }
  });
});
