import { describe, expect, it } from "vitest";

import {
  calculate7DayRollingAvg,
  calculateBMI,
  calculateDailyScore,
  calculateProgramProgress,
  calculateStreaks,
  calculateWeightPrediction,
  DEFAULT_PROGRAM_CONFIG,
  detectCalorieWarning,
  detectRecoveryWarning,
  exportToCSV,
  getWorkoutPlanForDay,
  importFromCSV,
  WEEKLY_SCHEDULE,
} from "./personalHealthCalculations";
import type { HealthDayRecord } from "@/types/personalHealth";

describe("personalHealthCalculations", () => {
  it("calculates BMI and Target BMI correctly", () => {
    // 70 kg at 165 cm
    const bmiStart = calculateBMI(70, 165);
    expect(bmiStart).toBe(25.7);

    // 60 kg at 165 cm
    const bmiTarget = calculateBMI(60, 165);
    expect(bmiTarget).toBe(22.0);
  });

  it("calculates program progress dates", () => {
    const progress = calculateProgramProgress("2026-08-25", DEFAULT_PROGRAM_CONFIG);
    expect(progress.dayNumber).toBe(1);
    expect(progress.totalDays).toBe(98);
    expect(progress.daysRemaining).toBe(97);
    expect(progress.progressPct).toBe(1);

    const progressMid = calculateProgramProgress("2026-09-25", DEFAULT_PROGRAM_CONFIG);
    expect(progressMid.dayNumber).toBe(32);
    expect(progressMid.daysRemaining).toBe(66);
  });

  it("verifies weekly schedule matches all program requirements", () => {
    // Monday
    const mon = WEEKLY_SCHEDULE.Monday;
    expect(mon.cyclingKm).toBe(20);
    expect(mon.walkingSteps).toBe(5000);
    expect(mon.hasStrength).toBe(true);
    expect(mon.exercises.map((e) => e.name)).toEqual(["Push-ups", "Crunches", "Bodyweight Squats", "Plank"]);

    // Tuesday
    const tue = WEEKLY_SCHEDULE.Tuesday;
    expect(tue.cyclingKm).toBe(20);
    expect(tue.walkingSteps).toBe(5000);
    expect(tue.runningKm).toBe(5);
    expect(tue.hasStrength).toBe(false);

    // Wednesday
    const wed = WEEKLY_SCHEDULE.Wednesday;
    expect(wed.cyclingKm).toBe(20);
    expect(wed.walkingSteps).toBe(5000);
    expect(wed.hasStrength).toBe(true);
    expect(wed.exercises.length).toBe(6);

    // Thursday
    const thu = WEEKLY_SCHEDULE.Thursday;
    expect(thu.cyclingKm).toBe(20);
    expect(thu.runningKm).toBe(5);

    // Friday
    const fri = WEEKLY_SCHEDULE.Friday;
    expect(fri.cyclingKm).toBe(20);
    expect(fri.hasStrength).toBe(true);

    // Saturday
    const sat = WEEKLY_SCHEDULE.Saturday;
    expect(sat.cyclingKm).toBe(20);
    expect(sat.runningKm).toBe(10);

    // Sunday
    const sun = WEEKLY_SCHEDULE.Sunday;
    expect(sun.cyclingKm).toBe(20);
    expect(sun.cyclingIntensity).toBe("easy");
    expect(sun.runningKm).toBe(0);

    // Weekly totals
    const totalCycling = Object.values(WEEKLY_SCHEDULE).reduce((acc, d) => acc + d.cyclingKm, 0);
    const totalRunning = Object.values(WEEKLY_SCHEDULE).reduce((acc, d) => acc + d.runningKm, 0);
    const totalWalking = Object.values(WEEKLY_SCHEDULE).reduce((acc, d) => acc + d.walkingSteps, 0);
    const totalStrength = Object.values(WEEKLY_SCHEDULE).filter((d) => d.hasStrength).length;

    expect(totalCycling).toBe(140);
    expect(totalRunning).toBe(20);
    expect(totalWalking).toBe(35000);
    expect(totalStrength).toBe(3);
  });

  it("calculates 7-day rolling average correctly", () => {
    const records: HealthDayRecord[] = [
      { date: "2026-08-25", weightKg: 70.0, updatedAt: "" },
      { date: "2026-08-26", weightKg: 69.8, updatedAt: "" },
      { date: "2026-08-27", weightKg: 69.5, updatedAt: "" },
      { date: "2026-08-28", weightKg: 69.3, updatedAt: "" },
      { date: "2026-08-29", weightKg: 69.0, updatedAt: "" },
      { date: "2026-08-30", weightKg: 68.8, updatedAt: "" },
      { date: "2026-08-31", weightKg: 68.5, updatedAt: "" },
    ];

    const avg = calculate7DayRollingAvg(records, "2026-08-31");
    // (70.0 + 69.8 + 69.5 + 69.3 + 69.0 + 68.8 + 68.5) / 7 = 484.9 / 7 = 69.27 -> 69.3
    expect(avg).toBe(69.3);
  });

  it("predicts target dates with realistic linear trend without hallucinating", () => {
    // With < 3 records, indicates insufficient data
    const predictionLow = calculateWeightPrediction([
      { date: "2026-08-25", weightKg: 70.0, updatedAt: "" },
    ]);
    expect(predictionLow.hasTrend).toBe(false);
    expect(predictionLow.message).toContain("Not enough historical data yet");

    // With 4 days of consistent ~0.1 kg/day loss
    const predictionGood = calculateWeightPrediction([
      { date: "2026-08-25", weightKg: 70.0, updatedAt: "" },
      { date: "2026-08-26", weightKg: 69.9, updatedAt: "" },
      { date: "2026-08-27", weightKg: 69.8, updatedAt: "" },
      { date: "2026-08-28", weightKg: 69.7, updatedAt: "" },
    ]);
    expect(predictionGood.hasTrend).toBe(true);
    expect(predictionGood.estimatedDate65kg).toBeDefined();
    expect(predictionGood.estimatedDate60kg).toBeDefined();
  });

  it("calculates daily progress scores with expected component weights", () => {
    const plan = getWorkoutPlanForDay("2026-08-25"); // Tuesday (Cycling 20km, Walking 5000, Running 5km)
    const recordFull: HealthDayRecord = {
      date: "2026-08-25",
      caloriesConsumed: 1600,
      cyclingKm: 20,
      walkingSteps: 5000,
      runningKm: 5,
      strengthCompleted: true,
      weightKg: 70.0,
      updatedAt: "",
    };

    const score = calculateDailyScore(recordFull, plan, DEFAULT_PROGRAM_CONFIG);
    expect(score).toBe(100);
  });

  it("calculates streaks accurately without penalizing recovery days", () => {
    const recordsMap: Record<string, HealthDayRecord> = {
      "2026-08-25": {
        date: "2026-08-25",
        caloriesConsumed: 1600,
        cyclingKm: 20,
        walkingSteps: 5000,
        strengthCompleted: true,
        weightKg: 70.0,
        updatedAt: "",
      },
      "2026-08-26": {
        date: "2026-08-26",
        caloriesConsumed: 1620,
        cyclingKm: 20,
        walkingSteps: 5000,
        runningKm: 5,
        weightKg: 69.8,
        updatedAt: "",
      },
    };

    const streaks = calculateStreaks(recordsMap, DEFAULT_PROGRAM_CONFIG, "2026-08-26");
    expect(streaks.currentStreak).toBe(2);
    expect(streaks.cyclingStreak).toBe(2);
    expect(streaks.walkingStreak).toBe(2);
  });

  it("detects safety warnings for poor recovery and low calories", () => {
    const poorRecoveryRecords: HealthDayRecord[] = [
      { date: "2026-08-25", sleepHours: 4.5, energyLevel: 2, sorenessLevel: 9, updatedAt: "" },
      { date: "2026-08-26", sleepHours: 5.0, energyLevel: 3, sorenessLevel: 8, updatedAt: "" },
      { date: "2026-08-27", sleepHours: 4.0, energyLevel: 2, sorenessLevel: 9, updatedAt: "" },
    ];
    const recWarn = detectRecoveryWarning(poorRecoveryRecords);
    expect(recWarn).toContain("Recovery may need attention");

    const lowCalRecords: HealthDayRecord[] = [
      { date: "2026-08-25", caloriesConsumed: 1000, updatedAt: "" },
      { date: "2026-08-26", caloriesConsumed: 950, updatedAt: "" },
      { date: "2026-08-27", caloriesConsumed: 1050, updatedAt: "" },
    ];
    const calWarn = detectCalorieWarning(lowCalRecords);
    expect(calWarn).toContain("Nutrition reminder");
  });

  it("exports and imports CSV round-trip cleanly", () => {
    const original: HealthDayRecord[] = [
      {
        date: "2026-08-25",
        weightKg: 70.0,
        caloriesConsumed: 1600,
        cyclingKm: 20,
        walkingSteps: 5000,
        runningKm: 0,
        pushUps: 15,
        crunches: 20,
        squats: 15,
        plankSeconds: 45,
        strengthCompleted: true,
        sleepHours: 8,
        waterLiters: 3,
        energyLevel: 8,
        sorenessLevel: 3,
        recoveryNotes: "Felt strong today",
        notes: "Program kickoff",
        updatedAt: "2026-08-25T10:00:00.000Z",
      },
    ];

    const csv = exportToCSV(original, DEFAULT_PROGRAM_CONFIG);
    expect(csv).toContain("2026-08-25");
    expect(csv).toContain("70");

    const imported = importFromCSV(csv);
    expect(imported.success).toBe(true);
    expect(imported.records?.length).toBe(1);
    expect(imported.records?.[0].date).toBe("2026-08-25");
    expect(imported.records?.[0].weightKg).toBe(70);
    expect(imported.records?.[0].strengthCompleted).toBe(true);
    expect(imported.records?.[0].notes).toBe("Program kickoff");
  });
});
