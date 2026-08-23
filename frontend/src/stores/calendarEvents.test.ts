import { beforeEach, describe, expect, it } from "vitest";
import { useCalendarStore } from "./calendarEvents";

describe("calendarEvents store", () => {
  beforeEach(() => {
    useCalendarStore.setState({
      events: [],
    });
  });

  it("adds, edits, moves, resizes, and deletes user events", () => {
    const store = useCalendarStore.getState();

    // 1. Add Event
    const added = store.addEvent({
      title: "Morning Gym",
      date: "2026-08-24",
      startTime: "07:00",
      endTime: "08:00",
      category: "gym",
      repeat: "none",
    });

    expect(useCalendarStore.getState().events).toHaveLength(1);
    expect(added.id).toBeDefined();

    // 2. Edit Event
    useCalendarStore.getState().updateEvent(added.id, {
      title: "Hardcore Gym Session",
      location: "Gold's Gym Mumbai",
    });
    const updated = useCalendarStore.getState().events.find((e) => e.id === added.id);
    expect(updated?.title).toBe("Hardcore Gym Session");
    expect(updated?.location).toBe("Gold's Gym Mumbai");

    // 3. Move Event
    useCalendarStore.getState().moveEvent(added.id, "2026-08-25", "08:00", "09:00");
    const moved = useCalendarStore.getState().events.find((e) => e.id === added.id);
    expect(moved?.date).toBe("2026-08-25");
    expect(moved?.startTime).toBe("08:00");
    expect(moved?.endTime).toBe("09:00");

    // 4. Resize Event
    useCalendarStore.getState().resizeEvent(added.id, "09:30");
    const resized = useCalendarStore.getState().events.find((e) => e.id === added.id);
    expect(resized?.endTime).toBe("09:30");

    // 5. Delete Event
    useCalendarStore.getState().deleteEvent(added.id);
    expect(useCalendarStore.getState().events).toHaveLength(0);
  });

  it("evaluates recurring events correctly across future dates without store bloat", () => {
    const store = useCalendarStore.getState();

    // Daily recurring event
    store.addEvent({
      title: "Daily Standup",
      date: "2026-08-24", // Monday
      startTime: "10:00",
      endTime: "10:30",
      category: "meeting",
      repeat: "daily",
    });

    // Weekday recurring event
    store.addEvent({
      title: "Weekday Market Analysis",
      date: "2026-08-24", // Monday
      startTime: "08:30",
      endTime: "09:00",
      category: "research",
      repeat: "weekdays",
    });

    // Weekly recurring event (Mondays only)
    store.addEvent({
      title: "Weekly Strategy Review",
      date: "2026-08-24", // Monday
      startTime: "16:00",
      endTime: "17:00",
      category: "trading",
      repeat: "weekly",
    });

    // Monthly recurring event (24th of month)
    store.addEvent({
      title: "Monthly Portfolio Rebalance",
      date: "2026-08-24",
      startTime: "17:00",
      endTime: "18:00",
      category: "trading",
      repeat: "monthly",
    });

    // Total stored events must remain 4 (no duplicated records)
    expect(useCalendarStore.getState().events).toHaveLength(4);

    // Check Tuesday (2026-08-25): Daily & Weekdays should appear; Weekly & Monthly should not
    const tuesdayEvents = useCalendarStore.getState().getEventsForDate("2026-08-25");
    expect(tuesdayEvents.map((e) => e.title)).toEqual([
      "Daily Standup",
      "Weekday Market Analysis",
    ]);

    // Check Saturday (2026-08-29): Daily should appear; Weekdays/Weekly/Monthly should not
    const saturdayEvents = useCalendarStore.getState().getEventsForDate("2026-08-29");
    expect(saturdayEvents.map((e) => e.title)).toEqual(["Daily Standup"]);

    // Check Next Monday (2026-08-31): Daily, Weekdays, and Weekly should appear
    const nextMondayEvents = useCalendarStore.getState().getEventsForDate("2026-08-31");
    expect(nextMondayEvents.map((e) => e.title)).toEqual([
      "Daily Standup",
      "Weekday Market Analysis",
      "Weekly Strategy Review",
    ]);

    // Check Next Month 24th (2026-09-24, Thursday): Daily, Weekdays, and Monthly should appear
    const nextMonth24thEvents = useCalendarStore.getState().getEventsForDate("2026-09-24");
    expect(nextMonth24thEvents.map((e) => e.title)).toEqual([
      "Daily Standup",
      "Weekday Market Analysis",
      "Monthly Portfolio Rebalance",
    ]);

    // Past date before creation (2026-08-20): None of the recurring events should appear
    const pastEvents = useCalendarStore.getState().getEventsForDate("2026-08-20");
    expect(pastEvents).toHaveLength(0);
  });
});
