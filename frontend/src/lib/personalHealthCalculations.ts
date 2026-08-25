import type {
  DaySchedulePlan,
  HealthDayRecord,
  HealthProgramConfig,
  MilestoneItem,
  WeekdayName,
  WeeklyReviewData,
  WeightPrediction,
} from "@/types/personalHealth";

export const DEFAULT_PROGRAM_CONFIG: HealthProgramConfig = {
  startDate: "2026-08-25",
  endDate: "2026-11-30",
  startingWeightKg: 70.0,
  targetWeightKg: 60.0,
  heightCm: 165,
  dailyCaloriesTarget: 1600,
  dailyCyclingKmTarget: 20,
  dailyWalkingStepsTarget: 5000,
  weeklyRunningKmTarget: 20,
  weeklyStrengthSessionsTarget: 3,
};

export const WEEKLY_SCHEDULE: Record<WeekdayName, DaySchedulePlan> = {
  Monday: {
    dayOfWeek: "Monday",
    focus: "Upper Body + Core Strength & Daily Cardio",
    cyclingKm: 20,
    cyclingIntensity: "moderate",
    walkingSteps: 5000,
    runningKm: 0,
    hasStrength: true,
    strengthType: "Upper Body + Core",
    exercises: [
      { name: "Push-ups", target: "3 × 10–20 reps", setsReps: "3x15" },
      { name: "Crunches", target: "3 × 15–20 reps", setsReps: "3x20" },
      { name: "Bodyweight Squats", target: "3 × 15 reps", setsReps: "3x15" },
      { name: "Plank", target: "3 × 30–45 sec", setsReps: "3x45s" },
    ],
  },
  Tuesday: {
    dayOfWeek: "Tuesday",
    focus: "Running 5 km & Daily Cardio (No Heavy Strength)",
    cyclingKm: 20,
    cyclingIntensity: "moderate",
    walkingSteps: 5000,
    runningKm: 5,
    hasStrength: false,
    strengthType: "Cardio Focus (No heavy strength)",
    exercises: [],
    recoveryFocus: "Hydration and leg recovery after 5 km run",
  },
  Wednesday: {
    dayOfWeek: "Wednesday",
    focus: "Full Body Strength & Daily Cardio",
    cyclingKm: 20,
    cyclingIntensity: "moderate",
    walkingSteps: 5000,
    runningKm: 0,
    hasStrength: true,
    strengthType: "Full Body",
    exercises: [
      { name: "Push-ups", target: "3 × 10–20 reps", setsReps: "3x15" },
      { name: "Bodyweight Squats", target: "3 × 15 reps", setsReps: "3x15" },
      { name: "Lunges", target: "3 × 10 each leg", setsReps: "3x10" },
      { name: "Crunches", target: "3 × 15–20 reps", setsReps: "3x20" },
      { name: "Glute Bridge", target: "3 × 15 reps", setsReps: "3x15" },
      { name: "Plank", target: "3 × 30–45 sec", setsReps: "3x45s" },
    ],
  },
  Thursday: {
    dayOfWeek: "Thursday",
    focus: "Running 5 km & Daily Cardio",
    cyclingKm: 20,
    cyclingIntensity: "moderate",
    walkingSteps: 5000,
    runningKm: 5,
    hasStrength: false,
    strengthType: "Cardio Focus (No heavy strength)",
    exercises: [],
    recoveryFocus: "Pacing and stretching",
  },
  Friday: {
    dayOfWeek: "Friday",
    focus: "Upper Body + Core Strength & Daily Cardio",
    cyclingKm: 20,
    cyclingIntensity: "moderate",
    walkingSteps: 5000,
    runningKm: 0,
    hasStrength: true,
    strengthType: "Upper Body + Core",
    exercises: [
      { name: "Push-ups", target: "3 × 10–20 reps", setsReps: "3x15" },
      { name: "Crunches", target: "3 × 15–20 reps", setsReps: "3x20" },
      { name: "Bodyweight Squats", target: "3 × 15 reps", setsReps: "3x15" },
      { name: "Plank", target: "3 × 30–45 sec", setsReps: "3x45s" },
    ],
  },
  Saturday: {
    dayOfWeek: "Saturday",
    focus: "Long Run 10 km & Daily Cardio",
    cyclingKm: 20,
    cyclingIntensity: "moderate",
    walkingSteps: 5000,
    runningKm: 10,
    hasStrength: false,
    strengthType: "Optional Light Strength / Mobility",
    exercises: [],
    recoveryFocus: "Long run endurance and post-run nutrition",
  },
  Sunday: {
    dayOfWeek: "Sunday",
    focus: "Active Recovery & Easy Cycling (No Hard Running)",
    cyclingKm: 20,
    cyclingIntensity: "easy",
    walkingSteps: 5000,
    runningKm: 0,
    hasStrength: false,
    strengthType: "Recovery & Mobility",
    exercises: [],
    recoveryFocus: "Full body mobility, foam rolling, early sleep",
  },
};

const WEEKDAY_NAMES: WeekdayName[] = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
];

export function getWeekdayName(dateStr: string): WeekdayName {
  const parts = parseDate(dateStr);
  const d = new Date(parts.year, parts.month - 1, parts.day);
  return WEEKDAY_NAMES[d.getDay()] ?? "Monday";
}

export function getWorkoutPlanForDay(dateStr: string): DaySchedulePlan {
  const dayName = getWeekdayName(dateStr);
  return WEEKLY_SCHEDULE[dayName] || WEEKLY_SCHEDULE.Monday;
}

export function parseDate(dateStr: string): { year: number; month: number; day: number } {
  const [y, m, d] = dateStr.split("-").map(Number);
  return { year: y || 2026, month: m || 1, day: d || 1 };
}

export function formatDate(year: number, month: number, day: number): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${year}-${pad(month)}-${pad(day)}`;
}

export function addDays(dateStr: string, days: number): string {
  const p = parseDate(dateStr);
  const d = new Date(p.year, p.month - 1, p.day);
  d.setDate(d.getDate() + days);
  return formatDate(d.getFullYear(), d.getMonth() + 1, d.getDate());
}

export function diffDays(dateA: string, dateB: string): number {
  const pa = parseDate(dateA);
  const pb = parseDate(dateB);
  const da = Date.UTC(pa.year, pa.month - 1, pa.day);
  const db = Date.UTC(pb.year, pb.month - 1, pb.day);
  return Math.round((db - da) / (1000 * 60 * 60 * 24));
}

export function getTodayDateStr(): string {
  const now = new Date();
  return formatDate(now.getFullYear(), now.getMonth() + 1, now.getDate());
}

export function calculateBMI(weightKg: number, heightCm: number): number {
  if (heightCm <= 0 || weightKg <= 0) return 0;
  const heightM = heightCm / 100;
  return Number((weightKg / (heightM * heightM)).toFixed(1));
}

export function calculateProgramProgress(
  currentDateStr: string,
  config: HealthProgramConfig = DEFAULT_PROGRAM_CONFIG,
): {
  totalDays: number;
  dayNumber: number;
  daysRemaining: number;
  isBeforeStart: boolean;
  isAfterEnd: boolean;
  progressPct: number;
} {
  const totalDays = Math.max(1, diffDays(config.startDate, config.endDate) + 1);
  const daysFromStart = diffDays(config.startDate, currentDateStr);
  const daysToEnd = diffDays(currentDateStr, config.endDate);

  const isBeforeStart = daysFromStart < 0;
  const isAfterEnd = daysToEnd < 0;

  const dayNumber = isBeforeStart ? 1 : isAfterEnd ? totalDays : daysFromStart + 1;
  const daysRemaining = Math.max(0, daysToEnd);
  const progressPct = Math.min(100, Math.max(0, Math.round((dayNumber / totalDays) * 100)));

  return {
    totalDays,
    dayNumber,
    daysRemaining,
    isBeforeStart,
    isAfterEnd,
    progressPct,
  };
}

export function calculate7DayRollingAvg(
  records: HealthDayRecord[],
  targetDateStr: string,
): number | null {
  const sorted = [...records]
    .filter((r) => r.weightKg !== undefined && r.weightKg > 0 && r.date <= targetDateStr)
    .sort((a, b) => b.date.localeCompare(a.date));

  // Get weights from the last 7 calendar days
  const windowRecords = sorted.filter((r) => diffDays(r.date, targetDateStr) <= 6 && diffDays(r.date, targetDateStr) >= 0);

  if (windowRecords.length === 0) {
    // If no records in the exact 7-day window, fall back to the most recent up to 7 records
    const recent = sorted.slice(0, 7);
    if (recent.length === 0) return null;
    const sum = recent.reduce((acc, cur) => acc + (cur.weightKg || 0), 0);
    return Number((sum / recent.length).toFixed(1));
  }

  const sum = windowRecords.reduce((acc, cur) => acc + (cur.weightKg || 0), 0);
  return Number((sum / windowRecords.length).toFixed(1));
}

export function calculateWeightPrediction(
  records: HealthDayRecord[],
  config: HealthProgramConfig = DEFAULT_PROGRAM_CONFIG,
): WeightPrediction {
  const validRecords = [...records]
    .filter((r) => r.weightKg !== undefined && r.weightKg > 0)
    .sort((a, b) => a.date.localeCompare(b.date));

  if (validRecords.length < 3) {
    return {
      hasTrend: false,
      dailyLossRateKg: null,
      estimatedDate65kg: null,
      estimatedDate62kg: null,
      estimatedDate60kg: null,
      message: "Not enough historical data yet. Continue recording weight to establish a trend.",
    };
  }

  // Calculate linear regression over days since first record
  const firstDate = validRecords[0].date;
  const latestRecord = validRecords[validRecords.length - 1];
  const latestWeight = latestRecord.weightKg!;
  const latestDate = latestRecord.date;

  const points = validRecords.map((r) => ({
    x: diffDays(firstDate, r.date),
    y: r.weightKg!,
  }));

  const n = points.length;
  const sumX = points.reduce((acc, p) => acc + p.x, 0);
  const sumY = points.reduce((acc, p) => acc + p.y, 0);
  const sumXY = points.reduce((acc, p) => acc + p.x * p.y, 0);
  const sumX2 = points.reduce((acc, p) => acc + p.x * p.x, 0);

  const denominator = n * sumX2 - sumX * sumX;
  if (denominator === 0) {
    return {
      hasTrend: false,
      dailyLossRateKg: null,
      estimatedDate65kg: null,
      estimatedDate62kg: null,
      estimatedDate60kg: null,
      message: "Continue recording weight across different days to establish a trend.",
    };
  }

  const slope = (n * sumXY - sumX * sumY) / denominator; // kg per day

  if (slope >= -0.005) {
    return {
      hasTrend: false,
      dailyLossRateKg: Number(slope.toFixed(3)),
      estimatedDate65kg: null,
      estimatedDate62kg: null,
      estimatedDate60kg: null,
      message: "Current weight trend is stable or plateaued. Continue consistent daily deficit and workouts.",
    };
  }

  const dailyLossRate = Math.abs(slope);

  const calcTargetDate = (targetKg: number): string | null => {
    if (latestWeight <= targetKg) return latestDate;
    const daysNeeded = Math.round((latestWeight - targetKg) / dailyLossRate);
    if (daysNeeded <= 0 || daysNeeded > 365) return null;
    return addDays(latestDate, daysNeeded);
  };

  return {
    hasTrend: true,
    dailyLossRateKg: Number(dailyLossRate.toFixed(3)),
    estimatedDate65kg: calcTargetDate(65),
    estimatedDate62kg: calcTargetDate(62),
    estimatedDate60kg: calcTargetDate(config.targetWeightKg),
  };
}

export function calculateDailyScore(
  record: HealthDayRecord | undefined,
  plan: DaySchedulePlan,
  config: HealthProgramConfig = DEFAULT_PROGRAM_CONFIG,
): number {
  if (!record) return 0;

  // 1. Calories (20%)
  let calScore = 0;
  if (record.caloriesConsumed !== undefined && record.caloriesConsumed > 0) {
    const diff = Math.abs(record.caloriesConsumed - config.dailyCaloriesTarget);
    if (diff <= 100) calScore = 100;
    else if (diff <= 300) calScore = 80;
    else if (diff <= 500) calScore = 60;
    else calScore = 40;
  }

  // 2. Cycling (20%)
  let cyclingScore = 0;
  const targetCycling = plan.cyclingKm || config.dailyCyclingKmTarget;
  if (targetCycling > 0) {
    const actualCycling = record.cyclingKm || 0;
    cyclingScore = Math.min(100, Math.round((actualCycling / targetCycling) * 100));
  } else {
    cyclingScore = 100;
  }

  // 3. Walking (10%)
  let walkingScore = 0;
  const targetWalking = plan.walkingSteps || config.dailyWalkingStepsTarget;
  if (targetWalking > 0) {
    const actualWalking = record.walkingSteps || 0;
    walkingScore = Math.min(100, Math.round((actualWalking / targetWalking) * 100));
  } else {
    walkingScore = 100;
  }

  // 4. Running (20%)
  let runningScore = 0;
  if (plan.runningKm > 0) {
    const actualRunning = record.runningKm || 0;
    runningScore = Math.min(100, Math.round((actualRunning / plan.runningKm) * 100));
  } else {
    // If no running planned today, grant 100%
    runningScore = 100;
  }

  // 5. Strength (20%)
  let strengthScore = 0;
  if (plan.hasStrength) {
    if (record.strengthCompleted) strengthScore = 100;
    else {
      // Partial credit for exercise reps
      const hasExercises = (record.pushUps || 0) + (record.crunches || 0) + (record.squats || 0) + (record.plankSeconds || 0) > 0;
      strengthScore = hasExercises ? 60 : 0;
    }
  } else {
    // Rest / non-strength day
    strengthScore = 100;
  }

  // 6. Weight Logging Consistency (10%)
  const weightScore = record.weightKg && record.weightKg > 0 ? 100 : 0;

  const totalScore =
    calScore * 0.2 +
    cyclingScore * 0.2 +
    walkingScore * 0.1 +
    runningScore * 0.2 +
    strengthScore * 0.2 +
    weightScore * 0.1;

  return Math.round(totalScore);
}

export function calculateStreaks(
  records: Record<string, HealthDayRecord>,
  config: HealthProgramConfig = DEFAULT_PROGRAM_CONFIG,
  currentDateStr: string = getTodayDateStr(),
): {
  currentStreak: number;
  bestStreak: number;
  cyclingStreak: number;
  walkingStreak: number;
  strengthStreak: number;
} {
  const dates: string[] = [];
  const start = config.startDate;
  const end = currentDateStr > config.endDate ? config.endDate : currentDateStr;

  let cur = start;
  while (cur <= end) {
    dates.push(cur);
    cur = addDays(cur, 1);
  }

  let currentStreak = 0;
  let bestStreak = 0;
  let runningStreak = 0;

  let cyclingStreak = 0;
  let runningCycling = 0;

  let walkingStreak = 0;
  let runningWalking = 0;

  let strengthStreak = 0;
  let runningStrength = 0;

  for (const d of dates) {
    const record = records[d];
    const plan = getWorkoutPlanForDay(d);
    const score = calculateDailyScore(record, plan, config);

    // Overall daily streak (>= 60% completion or active recording)
    if (score >= 60) {
      runningStreak++;
      if (runningStreak > bestStreak) bestStreak = runningStreak;
    } else if (d < currentDateStr) {
      runningStreak = 0;
    }

    // Cycling streak
    if ((record?.cyclingKm || 0) >= (plan.cyclingKm * 0.8)) {
      runningCycling++;
    } else if (d < currentDateStr) {
      runningCycling = 0;
    }

    // Walking streak
    if ((record?.walkingSteps || 0) >= (plan.walkingSteps * 0.8)) {
      runningWalking++;
    } else if (d < currentDateStr) {
      runningWalking = 0;
    }

    // Strength session streak
    if (plan.hasStrength) {
      if (record?.strengthCompleted || (record?.pushUps || 0) > 0) {
        runningStrength++;
      } else if (d < currentDateStr) {
        runningStrength = 0;
      }
    }
  }

  currentStreak = runningStreak;
  cyclingStreak = runningCycling;
  walkingStreak = runningWalking;
  strengthStreak = runningStrength;

  return {
    currentStreak,
    bestStreak,
    cyclingStreak,
    walkingStreak,
    strengthStreak,
  };
}

export function calculateMilestones(
  records: HealthDayRecord[],
  config: HealthProgramConfig = DEFAULT_PROGRAM_CONFIG,
): MilestoneItem[] {
  const validRecords = [...records].sort((a, b) => a.date.localeCompare(b.date));
  const weights = validRecords.filter((r) => r.weightKg !== undefined && r.weightKg > 0);

  const startWeight = config.startingWeightKg;
  const targetWeight = config.targetWeightKg;
  const totalGoalKg = startWeight - targetWeight; // 10 kg

  const minWeight = weights.length > 0 ? Math.min(...weights.map((r) => r.weightKg!)) : startWeight;
  const maxLostKg = Math.max(0, startWeight - minWeight);

  const totalCycling = validRecords.reduce((acc, r) => acc + (r.cyclingKm || 0), 0);
  const totalRunning = validRecords.reduce((acc, r) => acc + (r.runningKm || 0), 0);

  // Group by week for running & consistency
  const weekRuns: Record<string, number> = {};
  for (const r of validRecords) {
    if (r.runningKm) {
      const p = parseDate(r.date);
      const d = new Date(p.year, p.month - 1, p.day);
      const weekStart = addDays(r.date, -((d.getDay() + 6) % 7));
      weekRuns[weekStart] = (weekRuns[weekStart] || 0) + r.runningKm;
    }
  }
  const has20kRunningWeek = Object.values(weekRuns).some((km) => km >= 20);

  return [
    {
      id: "weight-1kg",
      title: "1 kg Lost",
      category: "weight",
      description: "First milestone on the road to 60 kg.",
      achieved: maxLostKg >= 1.0,
      currentValue: `${maxLostKg.toFixed(1)} kg`,
      targetValue: "1.0 kg",
      progressPct: Math.min(100, Math.round((maxLostKg / 1.0) * 100)),
    },
    {
      id: "weight-5pct",
      title: "5% Body Weight Lost",
      category: "weight",
      description: "Lose 3.5 kg from starting 70 kg.",
      achieved: maxLostKg >= startWeight * 0.05,
      currentValue: `${maxLostKg.toFixed(1)} kg`,
      targetValue: `${(startWeight * 0.05).toFixed(1)} kg`,
      progressPct: Math.min(100, Math.round((maxLostKg / (startWeight * 0.05)) * 100)),
    },
    {
      id: "weight-5kg",
      title: "5 kg Lost (Halfway to 60 kg)",
      category: "weight",
      description: "Reach 65.0 kg milestone.",
      achieved: maxLostKg >= 5.0,
      currentValue: `${maxLostKg.toFixed(1)} kg`,
      targetValue: "5.0 kg",
      progressPct: Math.min(100, Math.round((maxLostKg / 5.0) * 100)),
    },
    {
      id: "weight-target",
      title: "Target Weight (60.0 kg)",
      category: "weight",
      description: "Complete full 10 kg weight transformation.",
      achieved: minWeight <= targetWeight,
      currentValue: `${minWeight.toFixed(1)} kg`,
      targetValue: `${targetWeight.toFixed(1)} kg`,
      progressPct: Math.min(100, Math.round((maxLostKg / totalGoalKg) * 100)),
    },
    {
      id: "cycling-100k",
      title: "100 km Cycling",
      category: "cycling",
      description: "First 100 km in the saddle.",
      achieved: totalCycling >= 100,
      currentValue: `${totalCycling.toFixed(0)} km`,
      targetValue: "100 km",
      progressPct: Math.min(100, Math.round((totalCycling / 100) * 100)),
    },
    {
      id: "cycling-500k",
      title: "500 km Cycling",
      category: "cycling",
      description: "Major cardiovascular milestone.",
      achieved: totalCycling >= 500,
      currentValue: `${totalCycling.toFixed(0)} km`,
      targetValue: "500 km",
      progressPct: Math.min(100, Math.round((totalCycling / 500) * 100)),
    },
    {
      id: "cycling-1000k",
      title: "1,000 km Cycling",
      category: "cycling",
      description: "Elite endurance milestone across the program.",
      achieved: totalCycling >= 1000,
      currentValue: `${totalCycling.toFixed(0)} km`,
      targetValue: "1,000 km",
      progressPct: Math.min(100, Math.round((totalCycling / 1000) * 100)),
    },
    {
      id: "running-20k-week",
      title: "First 20 km Running Week",
      category: "running",
      description: "Complete the weekly 5k + 5k + 10k running target.",
      achieved: has20kRunningWeek,
      currentValue: `${totalRunning.toFixed(0)} km total`,
      targetValue: "20 km in 1 week",
      progressPct: has20kRunningWeek ? 100 : Math.min(100, Math.round((totalRunning / 20) * 100)),
    },
    {
      id: "consistency-4w",
      title: "4-Week Consistency",
      category: "consistency",
      description: "28 consecutive days of active tracking & training.",
      achieved: validRecords.length >= 28,
      currentValue: `${validRecords.length} days`,
      targetValue: "28 days",
      progressPct: Math.min(100, Math.round((validRecords.length / 28) * 100)),
    },
    {
      id: "consistency-8w",
      title: "8-Week Consistency",
      category: "consistency",
      description: "56 days of persistent nutrition & daily cardio.",
      achieved: validRecords.length >= 56,
      currentValue: `${validRecords.length} days`,
      targetValue: "56 days",
      progressPct: Math.min(100, Math.round((validRecords.length / 56) * 100)),
    },
    {
      id: "program-final-week",
      title: "Final Program Week",
      category: "program",
      description: "Enter the final stretch leading to 30 November 2026.",
      achieved: diffDays(config.startDate, getTodayDateStr()) >= 91,
      currentValue: `Day ${Math.max(1, diffDays(config.startDate, getTodayDateStr()) + 1)}`,
      targetValue: "Day 92",
      progressPct: Math.min(100, Math.round(((diffDays(config.startDate, getTodayDateStr()) + 1) / 98) * 100)),
    },
  ];
}

export function detectRecoveryWarning(records: HealthDayRecord[]): string | null {
  const sorted = [...records].sort((a, b) => b.date.localeCompare(a.date));
  const recent = sorted.slice(0, 3);
  if (recent.length < 3) return null;

  const poorRecoveryCount = recent.filter(
    (r) =>
      (r.sleepHours !== undefined && r.sleepHours < 6) ||
      (r.energyLevel !== undefined && r.energyLevel <= 3) ||
      (r.sorenessLevel !== undefined && r.sorenessLevel >= 8),
  ).length;

  if (poorRecoveryCount >= 3) {
    return "Recovery may need attention. Consider reducing training intensity and prioritizing sleep, nutrition and recovery.";
  }
  return null;
}

export function detectCalorieWarning(records: HealthDayRecord[]): string | null {
  const sorted = [...records].sort((a, b) => b.date.localeCompare(a.date));
  const recent = sorted.slice(0, 3);
  if (recent.length < 3) return null;

  const lowCalorieCount = recent.filter(
    (r) => r.caloriesConsumed !== undefined && r.caloriesConsumed > 0 && r.caloriesConsumed < 1200,
  ).length;

  if (lowCalorieCount >= 3) {
    return "Nutrition reminder: Daily intake is significantly below target. Ensure adequate protein, carbs, and micronutrients to support 20 km daily cycling and recovery.";
  }
  return null;
}

export function getWeeklyReview(
  records: Record<string, HealthDayRecord>,
  weekStartDateStr: string,
  weekNumber: number,
  config: HealthProgramConfig = DEFAULT_PROGRAM_CONFIG,
): WeeklyReviewData {
  const days: string[] = [];
  for (let i = 0; i < 7; i++) {
    days.push(addDays(weekStartDateStr, i));
  }
  const weekEndDateStr = days[6];

  let totalCycling = 0;
  let totalRunning = 0;
  let totalWalking = 0;
  let totalStrength = 0;
  let totalCalories = 0;
  let calCount = 0;
  const weights: number[] = [];
  let bestDay: { date: string; score: number } | null = null;
  let recordedDays = 0;
  let totalScoreSum = 0;

  for (const d of days) {
    const record = records[d];
    const plan = getWorkoutPlanForDay(d);
    if (record) {
      recordedDays++;
      if (record.cyclingKm) totalCycling += record.cyclingKm;
      if (record.runningKm) totalRunning += record.runningKm;
      if (record.walkingSteps) totalWalking += record.walkingSteps;
      if (record.strengthCompleted) totalStrength++;
      if (record.caloriesConsumed) {
        totalCalories += record.caloriesConsumed;
        calCount++;
      }
      if (record.weightKg) weights.push(record.weightKg);

      const score = calculateDailyScore(record, plan, config);
      totalScoreSum += score;
      if (!bestDay || score > bestDay.score) {
        bestDay = { date: d, score };
      }
    }
  }

  const startingWeight = weights.length > 0 ? weights[0] : null;
  const endingWeight = weights.length > 0 ? weights[weights.length - 1] : null;
  const weightChange = startingWeight !== null && endingWeight !== null ? Number((endingWeight - startingWeight).toFixed(1)) : null;
  const avgWeight = weights.length > 0 ? Number((weights.reduce((a, b) => a + b, 0) / weights.length).toFixed(1)) : null;
  const avgCalories = calCount > 0 ? Math.round(totalCalories / calCount) : null;

  const missedTargets: string[] = [];
  if (totalCycling < 140) missedTargets.push(`Cycling (${totalCycling}/140 km)`);
  if (totalRunning < 20) missedTargets.push(`Running (${totalRunning}/20 km)`);
  if (totalWalking < 35000) missedTargets.push(`Walking (${totalWalking.toLocaleString()}/35,000 steps)`);
  if (totalStrength < 3) missedTargets.push(`Strength (${totalStrength}/3 sessions)`);

  const workoutCompletionPct = recordedDays > 0 ? Math.min(100, Math.round(totalScoreSum / 7)) : 0;

  return {
    weekNumber,
    startDate: weekStartDateStr,
    endDate: weekEndDateStr,
    startingWeightKg: startingWeight,
    endingWeightKg: endingWeight,
    weightChangeKg: weightChange,
    avgWeightKg: avgWeight,
    avgCalories,
    totalCyclingKm: totalCycling,
    targetCyclingKm: 140,
    totalRunningKm: totalRunning,
    targetRunningKm: 20,
    totalWalkingSteps: totalWalking,
    targetWalkingSteps: 35000,
    strengthSessionsCompleted: totalStrength,
    targetStrengthSessions: 3,
    workoutCompletionPct,
    bestDay,
    missedTargets,
    daysRecorded: recordedDays,
  };
}

export function exportToCSV(
  records: HealthDayRecord[],
  _config: HealthProgramConfig = DEFAULT_PROGRAM_CONFIG,
): string {
  const headers = [
    "date",
    "weightKg",
    "caloriesConsumed",
    "cyclingKm",
    "walkingSteps",
    "runningKm",
    "pushUps",
    "crunches",
    "squats",
    "lunges",
    "plankSeconds",
    "strengthCompleted",
    "sleepHours",
    "waterLiters",
    "energyLevel",
    "sorenessLevel",
    "recoveryNotes",
    "notes",
    "updatedAt",
  ];

  const rows = [...records]
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((r) => [
      r.date,
      r.weightKg ?? "",
      r.caloriesConsumed ?? "",
      r.cyclingKm ?? "",
      r.walkingSteps ?? "",
      r.runningKm ?? "",
      r.pushUps ?? "",
      r.crunches ?? "",
      r.squats ?? "",
      r.lunges ?? "",
      r.plankSeconds ?? "",
      r.strengthCompleted ? "true" : "false",
      r.sleepHours ?? "",
      r.waterLiters ?? "",
      r.energyLevel ?? "",
      r.sorenessLevel ?? "",
      `"${(r.recoveryNotes || "").replace(/"/g, '""')}"`,
      `"${(r.notes || "").replace(/"/g, '""')}"`,
      r.updatedAt || "",
    ]);

  return [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
}

export function importFromCSV(csvText: string): {
  success: boolean;
  records?: HealthDayRecord[];
  error?: string;
} {
  try {
    const lines = csvText.trim().split(/\r?\n/);
    if (lines.length < 2) {
      return { success: false, error: "CSV file is empty or missing data rows." };
    }

    const headers = lines[0].split(",").map((h) => h.trim().replace(/^"|"$/g, ""));
    const dateIdx = headers.indexOf("date");
    if (dateIdx === -1) {
      return { success: false, error: "CSV missing required 'date' column header." };
    }

    const records: HealthDayRecord[] = [];

    for (let i = 1; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) continue;

      // Simple CSV row parser handling quotes
      const values: string[] = [];
      let inQuotes = false;
      let curVal = "";
      for (let j = 0; j < line.length; j++) {
        const char = line[j];
        if (char === '"') {
          inQuotes = !inQuotes;
        } else if (char === "," && !inQuotes) {
          values.push(curVal.trim());
          curVal = "";
        } else {
          curVal += char;
        }
      }
      values.push(curVal.trim());

      const rowMap: Record<string, string> = {};
      headers.forEach((h, idx) => {
        rowMap[h] = values[idx] || "";
      });

      const dateStr = rowMap.date?.replace(/^"|"$/g, "").trim();
      if (!dateStr || !/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
        continue;
      }

      const num = (v: string | undefined) => (v && !isNaN(Number(v)) ? Number(v) : undefined);

      records.push({
        date: dateStr,
        weightKg: num(rowMap.weightKg),
        caloriesConsumed: num(rowMap.caloriesConsumed),
        cyclingKm: num(rowMap.cyclingKm),
        walkingSteps: num(rowMap.walkingSteps),
        runningKm: num(rowMap.runningKm),
        pushUps: num(rowMap.pushUps),
        crunches: num(rowMap.crunches),
        squats: num(rowMap.squats),
        lunges: num(rowMap.lunges),
        plankSeconds: num(rowMap.plankSeconds),
        strengthCompleted: rowMap.strengthCompleted === "true",
        sleepHours: num(rowMap.sleepHours),
        waterLiters: num(rowMap.waterLiters),
        energyLevel: num(rowMap.energyLevel),
        sorenessLevel: num(rowMap.sorenessLevel),
        recoveryNotes: rowMap.recoveryNotes?.replace(/^"|"$/g, "").replace(/""/g, '"') || undefined,
        notes: rowMap.notes?.replace(/^"|"$/g, "").replace(/""/g, '"') || undefined,
        updatedAt: rowMap.updatedAt || new Date().toISOString(),
      });
    }

    if (records.length === 0) {
      return { success: false, error: "No valid date records found in CSV file." };
    }

    return { success: true, records };
  } catch (err) {
    return { success: false, error: `Failed to parse CSV: ${String(err)}` };
  }
}
