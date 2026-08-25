import { beforeEach, describe, expect, it } from "vitest";

import { usePersonalHealth } from "./personalHealth";
import { DEFAULT_PROGRAM_CONFIG } from "@/lib/personalHealthCalculations";

describe("usePersonalHealth store", () => {
  beforeEach(() => {
    usePersonalHealth.getState().resetProgram();
  });

  it("initializes with DEFAULT_PROGRAM_CONFIG and empty records", () => {
    const state = usePersonalHealth.getState();
    expect(state.config).toEqual(DEFAULT_PROGRAM_CONFIG);
    expect(state.records).toEqual({});
    expect(state.getAllRecordsList()).toEqual([]);
  });

  it("saves a new day record and retrieves it", () => {
    const store = usePersonalHealth.getState();
    store.saveDayRecord({
      date: "2026-08-25",
      weightKg: 69.8,
      caloriesConsumed: 1600,
      cyclingKm: 20,
      walkingSteps: 5200,
      strengthCompleted: true,
      notes: "Day 1 feeling energized",
    });

    const record = usePersonalHealth.getState().getDayRecord("2026-08-25");
    expect(record).toBeDefined();
    expect(record?.weightKg).toBe(69.8);
    expect(record?.cyclingKm).toBe(20);
    expect(record?.strengthCompleted).toBe(true);
    expect(record?.notes).toBe("Day 1 feeling energized");
  });

  it("updates and edits an existing day record without losing previous fields", () => {
    const store = usePersonalHealth.getState();
    store.saveDayRecord({
      date: "2026-08-25",
      weightKg: 69.8,
      cyclingKm: 20,
    });

    store.saveDayRecord({
      date: "2026-08-25",
      caloriesConsumed: 1550,
      walkingSteps: 5500,
    });

    const record = usePersonalHealth.getState().getDayRecord("2026-08-25");
    expect(record?.weightKg).toBe(69.8);
    expect(record?.cyclingKm).toBe(20);
    expect(record?.caloriesConsumed).toBe(1550);
    expect(record?.walkingSteps).toBe(5500);
  });

  it("deletes a day record cleanly", () => {
    const store = usePersonalHealth.getState();
    store.saveDayRecord({ date: "2026-08-25", weightKg: 70 });
    expect(usePersonalHealth.getState().getDayRecord("2026-08-25")).toBeDefined();

    store.deleteDayRecord("2026-08-25");
    expect(usePersonalHealth.getState().getDayRecord("2026-08-25")).toBeUndefined();
    expect(usePersonalHealth.getState().getAllRecordsList().length).toBe(0);
  });

  it("imports records and handles overwrite option", () => {
    const store = usePersonalHealth.getState();
    store.saveDayRecord({ date: "2026-08-25", weightKg: 70 });

    store.importRecords(
      [
        { date: "2026-08-26", weightKg: 69.8, updatedAt: "" },
        { date: "2026-08-27", weightKg: 69.5, updatedAt: "" },
      ],
      false, // append
    );

    expect(usePersonalHealth.getState().getAllRecordsList().length).toBe(3);

    store.importRecords(
      [{ date: "2026-08-28", weightKg: 69.2, updatedAt: "" }],
      true, // overwrite
    );

    expect(usePersonalHealth.getState().getAllRecordsList().length).toBe(1);
    expect(usePersonalHealth.getState().getDayRecord("2026-08-28")).toBeDefined();
  });

  it("updates program targets in settings", () => {
    const store = usePersonalHealth.getState();
    store.updateConfig({
      dailyCaloriesTarget: 1500,
      dailyCyclingKmTarget: 25,
    });

    const state = usePersonalHealth.getState();
    expect(state.config.dailyCaloriesTarget).toBe(1500);
    expect(state.config.dailyCyclingKmTarget).toBe(25);
    expect(state.config.targetWeightKg).toBe(60.0); // unedited stays intact
  });
});
