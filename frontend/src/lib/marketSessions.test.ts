import { describe, expect, it } from "vitest";
import {
  getIndianMarketDaySchedule,
  INDIAN_MARKET_WINDOWS,
  weekdayInZone,
} from "./marketSessions";

describe("marketSessions", () => {
  it("provides 3 exact Indian market windows on ordinary trading days (Monday)", () => {
    // 2026-08-24 is Monday
    const monday = new Date("2026-08-24T05:00:00.000Z");
    expect(weekdayInZone(monday, "Asia/Kolkata")).toBe(1);

    const schedule = getIndianMarketDaySchedule(monday);
    expect(schedule.type).toBe("open");
    if (schedule.type === "open") {
      expect(schedule.windows).toHaveLength(3);

      // Window 1: Pre-Market 09:00 - 09:15
      expect(schedule.windows[0].name).toBe("Pre-Market");
      expect(schedule.windows[0].startTime).toBe("09:00");
      expect(schedule.windows[0].endTime).toBe("09:15");
      expect(schedule.windows[0].phase).toBe("pre");

      // Window 2: Market Hours 09:15 - 15:15
      expect(schedule.windows[1].name).toBe("Market Hours");
      expect(schedule.windows[1].startTime).toBe("09:15");
      expect(schedule.windows[1].endTime).toBe("15:15");
      expect(schedule.windows[1].phase).toBe("main");

      // Window 3: Cash Market 15:15 - 15:45
      expect(schedule.windows[2].name).toBe("Cash Market");
      expect(schedule.windows[2].startTime).toBe("15:15");
      expect(schedule.windows[2].endTime).toBe("15:45");
      expect(schedule.windows[2].phase).toBe("post");
    }
  });

  it("marks Saturday and Sunday as Market Closed (weekend)", () => {
    // 2026-08-29 is Saturday
    const saturday = new Date("2026-08-29T05:00:00.000Z");
    expect(weekdayInZone(saturday, "Asia/Kolkata")).toBe(6);
    const satSchedule = getIndianMarketDaySchedule(saturday);
    expect(satSchedule.type).toBe("weekend");
    if (satSchedule.type === "weekend") {
      expect(satSchedule.reason).toBe("Market Closed");
    }

    // 2026-08-30 is Sunday
    const sunday = new Date("2026-08-30T05:00:00.000Z");
    expect(weekdayInZone(sunday, "Asia/Kolkata")).toBe(0);
    const sunSchedule = getIndianMarketDaySchedule(sunday);
    expect(sunSchedule.type).toBe("weekend");
    if (sunSchedule.type === "weekend") {
      expect(sunSchedule.reason).toBe("Market Closed");
    }
  });

  it("marks official Indian market holidays as Market Closed with holiday name", () => {
    // 2026-10-02 Mahatma Gandhi Jayanti (Friday)
    const gandhiJayanti = new Date("2026-10-02T05:00:00.000Z");
    expect(weekdayInZone(gandhiJayanti, "Asia/Kolkata")).toBe(5);

    const schedule = getIndianMarketDaySchedule(gandhiJayanti);
    expect(schedule.type).toBe("holiday");
    if (schedule.type === "holiday") {
      expect(schedule.holidayName).toBe("Mahatma Gandhi Jayanti");
      expect(schedule.reason).toBe("Market Closed — Mahatma Gandhi Jayanti");
    }
  });

  it("uses Asia/Kolkata timezone for all Indian market windows", () => {
    for (const w of INDIAN_MARKET_WINDOWS) {
      expect(w.timezone).toBe("Asia/Kolkata");
    }
  });
});
