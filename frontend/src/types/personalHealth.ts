export interface HealthProgramConfig {
  startDate: string; // YYYY-MM-DD (e.g. 2026-08-25)
  endDate: string; // YYYY-MM-DD (e.g. 2026-11-30)
  startingWeightKg: number; // 70.0
  targetWeightKg: number; // 60.0
  heightCm: number; // 165
  dailyCaloriesTarget: number; // 1600
  dailyCyclingKmTarget: number; // 20
  dailyWalkingStepsTarget: number; // 5000
  weeklyRunningKmTarget: number; // 20
  weeklyStrengthSessionsTarget: number; // 3
}

export interface HealthDayRecord {
  date: string; // YYYY-MM-DD
  weightKg?: number;
  caloriesConsumed?: number;
  cyclingKm?: number;
  walkingSteps?: number;
  runningKm?: number;
  pushUps?: number;
  crunches?: number;
  squats?: number;
  lunges?: number;
  plankSeconds?: number;
  strengthCompleted?: boolean;
  sleepHours?: number;
  waterLiters?: number;
  energyLevel?: number; // 1 to 10
  sorenessLevel?: number; // 1 to 10
  recoveryNotes?: string;
  notes?: string;
  updatedAt: string; // ISO string
}

export type WeekdayName = "Monday" | "Tuesday" | "Wednesday" | "Thursday" | "Friday" | "Saturday" | "Sunday";

export interface PlannedExercise {
  name: string;
  target: string;
  setsReps?: string;
  notes?: string;
}

export interface DaySchedulePlan {
  dayOfWeek: WeekdayName;
  focus: string;
  cyclingKm: number;
  cyclingIntensity?: "moderate" | "easy" | "intervals";
  walkingSteps: number;
  runningKm: number;
  hasStrength: boolean;
  strengthType?: string;
  exercises: PlannedExercise[];
  recoveryFocus?: string;
}

export interface WeightPrediction {
  hasTrend: boolean;
  dailyLossRateKg: number | null; // e.g. 0.1 kg/day
  estimatedDate65kg: string | null;
  estimatedDate62kg: string | null;
  estimatedDate60kg: string | null;
  message?: string;
}

export interface MilestoneItem {
  id: string;
  title: string;
  category: "weight" | "cycling" | "running" | "consistency" | "program";
  description: string;
  achieved: boolean;
  achievedDate?: string;
  currentValue?: string;
  targetValue?: string;
  progressPct: number;
}

export interface WeeklyReviewData {
  weekNumber: number;
  startDate: string;
  endDate: string;
  startingWeightKg: number | null;
  endingWeightKg: number | null;
  weightChangeKg: number | null;
  avgWeightKg: number | null;
  avgCalories: number | null;
  totalCyclingKm: number;
  targetCyclingKm: number;
  totalRunningKm: number;
  targetRunningKm: number;
  totalWalkingSteps: number;
  targetWalkingSteps: number;
  strengthSessionsCompleted: number;
  targetStrengthSessions: number;
  workoutCompletionPct: number;
  bestDay: { date: string; score: number } | null;
  missedTargets: string[];
  daysRecorded: number;
}
