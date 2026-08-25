import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge, Button, Card, PageHeader, StatCard } from "@/components/ui";
import {
  calculate7DayRollingAvg,
  calculateBMI,
  calculateDailyScore,
  calculateProgramProgress,
  calculateStreaks,
  detectCalorieWarning,
  detectRecoveryWarning,
  getTodayDateStr,
  getWorkoutPlanForDay,
} from "@/lib/personalHealthCalculations";
import { DailyCheckInModal } from "./DailyCheckInModal";
import { ProgressRing } from "./ProgressRing";
import { usePersonalHealth } from "@/stores/personalHealth";

export function PersonalHealthDashboard() {
  const config = usePersonalHealth((s) => s.config);
  const records = usePersonalHealth((s) => s.records);

  const [checkInOpen, setCheckInOpen] = useState(false);
  const [selectedDate, setSelectedDate] = useState(getTodayDateStr());

  const todayStr = getTodayDateStr();
  const allRecords = useMemo(() => {
    return Object.values(records).sort((a, b) => a.date.localeCompare(b.date));
  }, [records]);
  const todayRecord = records[todayStr];
  const todayPlan = getWorkoutPlanForDay(todayStr);

  const programProgress = calculateProgramProgress(todayStr, config);

  // Latest recorded weight or starting weight
  const weightsList = allRecords.filter((r) => r.weightKg !== undefined && r.weightKg > 0);

  const latestWeightRecord = weightsList.length > 0 ? weightsList[weightsList.length - 1] : null;
  const currentWeightKg = latestWeightRecord ? latestWeightRecord.weightKg! : config.startingWeightKg;

  // Previous recorded weight to calculate change
  const previousWeightRecord =
    weightsList.length > 1 ? weightsList[weightsList.length - 2] : null;
  const weightDeltaFromPrev =
    previousWeightRecord && latestWeightRecord
      ? Number((latestWeightRecord.weightKg! - previousWeightRecord.weightKg!).toFixed(1))
      : null;

  const weightLostKg = Math.max(0, Number((config.startingWeightKg - currentWeightKg).toFixed(1)));
  const weightRemainingKg = Math.max(0, Number((currentWeightKg - config.targetWeightKg).toFixed(1)));
  const totalGoalKg = config.startingWeightKg - config.targetWeightKg;
  const goalCompletionPct = Math.min(100, Math.max(0, Math.round((weightLostKg / totalGoalKg) * 100)));

  const currentBMI = calculateBMI(currentWeightKg, config.heightCm);
  const targetBMI = calculateBMI(config.targetWeightKg, config.heightCm);
  const rollingAvg7Day = calculate7DayRollingAvg(allRecords, todayStr);

  const streaks = calculateStreaks(records, config, todayStr);

  const todayScore = calculateDailyScore(todayRecord, todayPlan, config);

  // Weekly running & totals for current week (Mon-Sun)
  const p = todayStr.split("-").map(Number);
  const d = new Date(p[0], p[1] - 1, p[2]);
  const dayOfWeek = (d.getDay() + 6) % 7; // Mon = 0
  let currentWeekRunningKm = 0;
  let weekCycling = 0;
  let weekWalking = 0;
  let weekRunning = 0;
  let weekStrength = 0;
  for (let i = 0; i <= 6; i++) {
    const targetDate = new Date(d);
    targetDate.setDate(d.getDate() - dayOfWeek + i);
    const y = targetDate.getFullYear();
    const m = String(targetDate.getMonth() + 1).padStart(2, "0");
    const day = String(targetDate.getDate()).padStart(2, "0");
    const dateKey = `${y}-${m}-${day}`;
    const rec = records[dateKey];
    if (rec?.runningKm) {
      currentWeekRunningKm += rec.runningKm;
      weekRunning += rec.runningKm;
    }
    if (rec?.cyclingKm) weekCycling += rec.cyclingKm;
    if (rec?.walkingSteps) weekWalking += rec.walkingSteps;
    if (rec?.strengthCompleted) weekStrength++;
  }
  const weekTotals = { cycling: weekCycling, walking: weekWalking, running: weekRunning, strength: weekStrength };

  // Chart data for weight trend (last 30 days)
  const chartData = allRecords
    .filter((r) => r.weightKg !== undefined && r.weightKg > 0)
    .map((r) => ({
      date: r.date.slice(5), // MM-DD
      actual: r.weightKg,
      rollingAvg: calculate7DayRollingAvg(allRecords, r.date),
      target: config.targetWeightKg,
    }));

  // Safety Warnings
  const recoveryWarning = detectRecoveryWarning(allRecords);
  const calorieWarning = detectCalorieWarning(allRecords);

  return (
    <div className="space-y-6">
      {/* Header with program day timeline */}
      <PageHeader
        title="Personal Health"
        description="Fitness, weight and recovery tracking"
        actions={
          <div className="flex items-center gap-3">
            <div className="text-right text-xs">
              <span className="font-semibold text-slate-900 dark:text-slate-100">
                Day {programProgress.dayNumber} / {programProgress.totalDays}
              </span>
              <span className="ml-2 text-slate-500 dark:text-slate-400">
                ({programProgress.daysRemaining} days remaining)
              </span>
            </div>
            <Button
              variant="primary"
              onClick={() => {
                setSelectedDate(todayStr);
                setCheckInOpen(true);
              }}
              className="font-semibold shadow-sm"
            >
              + Daily Check-In
            </Button>
          </div>
        }
      />

      {/* Safety / Nutrition Warnings */}
      {recoveryWarning && (
        <div className="flex items-center gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-800 dark:text-amber-300">
          <span className="text-xl">⚠️</span>
          <p>{recoveryWarning}</p>
        </div>
      )}
      {calorieWarning && (
        <div className="flex items-center gap-3 rounded-xl border border-blue-500/30 bg-blue-500/10 p-4 text-sm text-blue-800 dark:text-blue-300">
          <span className="text-xl">ℹ️</span>
          <p>{calorieWarning}</p>
        </div>
      )}

      {/* Profile / Program Summary Cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard
          label="Current Weight"
          value={latestWeightRecord?.weightKg ? `${latestWeightRecord.weightKg} kg` : `${config.startingWeightKg} kg`}
          sub={
            weightDeltaFromPrev !== null
              ? `${weightDeltaFromPrev > 0 ? "+" : ""}${weightDeltaFromPrev} kg from prev`
              : "Starting weight"
          }
          valueClass="text-slate-900 dark:text-slate-100"
        />
        <StatCard
          label="Target Weight"
          value={`${config.targetWeightKg} kg`}
          sub={`${weightRemainingKg} kg remaining`}
          valueClass="text-accent-600 dark:text-accent-400"
        />
        <StatCard
          label="Weight Lost"
          value={`${weightLostKg} kg`}
          sub={`${goalCompletionPct}% goal reached`}
          valueClass="text-profit-600 dark:text-profit-400"
        />
        <StatCard
          label="Current BMI"
          value={currentBMI ? String(currentBMI) : "—"}
          sub={`Target: ${targetBMI}`}
          valueClass="text-slate-900 dark:text-slate-100"
        />
        <StatCard
          label="7-Day Avg Weight"
          value={rollingAvg7Day ? `${rollingAvg7Day} kg` : "—"}
          sub="Rolling average"
          valueClass="text-slate-900 dark:text-slate-100"
        />
        <StatCard
          label="Daily Score / Streak"
          value={`${todayScore}%`}
          sub={`🔥 ${streaks.currentStreak} day streak (Best: ${streaks.bestStreak})`}
          valueClass={todayScore >= 80 ? "text-profit-600 dark:text-profit-400" : "text-amber-600 dark:text-amber-400"}
        />
      </div>

      {/* Today's Progress Cards / Rings */}
      <Card title="Today's Progress & Targets">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {/* Calories */}
          <div className="flex flex-col items-center justify-between rounded-xl border border-slate-100 bg-slate-50/50 p-4 dark:border-surface-800 dark:bg-surface-850/50">
            <ProgressRing
              percentage={
                todayRecord?.caloriesConsumed
                  ? Math.min(100, (todayRecord.caloriesConsumed / config.dailyCaloriesTarget) * 100)
                  : 0
              }
              valueText={
                todayRecord?.caloriesConsumed !== undefined
                  ? `${todayRecord.caloriesConsumed}`
                  : "Not recorded"
              }
              subText="kcal"
              label="Calories"
              colorClass="text-amber-500"
            />
            <span className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              {todayRecord?.caloriesConsumed !== undefined
                ? `${Math.max(0, config.dailyCaloriesTarget - todayRecord.caloriesConsumed)} kcal left`
                : `Target: ${config.dailyCaloriesTarget} kcal`}
            </span>
          </div>

          {/* Cycling */}
          <div className="flex flex-col items-center justify-between rounded-xl border border-slate-100 bg-slate-50/50 p-4 dark:border-surface-800 dark:bg-surface-850/50">
            <ProgressRing
              percentage={
                todayRecord?.cyclingKm
                  ? Math.min(100, (todayRecord.cyclingKm / config.dailyCyclingKmTarget) * 100)
                  : 0
              }
              valueText={
                todayRecord?.cyclingKm !== undefined ? `${todayRecord.cyclingKm} km` : "Not recorded"
              }
              subText={`of ${config.dailyCyclingKmTarget} km`}
              label="Cycling"
              colorClass="text-emerald-500"
            />
            <span className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              Streak: {streaks.cyclingStreak} days
            </span>
          </div>

          {/* Walking */}
          <div className="flex flex-col items-center justify-between rounded-xl border border-slate-100 bg-slate-50/50 p-4 dark:border-surface-800 dark:bg-surface-850/50">
            <ProgressRing
              percentage={
                todayRecord?.walkingSteps
                  ? Math.min(100, (todayRecord.walkingSteps / config.dailyWalkingStepsTarget) * 100)
                  : 0
              }
              valueText={
                todayRecord?.walkingSteps !== undefined
                  ? `${todayRecord.walkingSteps.toLocaleString()}`
                  : "Not recorded"
              }
              subText={`of ${config.dailyWalkingStepsTarget.toLocaleString()}`}
              label="Walking Steps"
              colorClass="text-blue-500"
            />
            <span className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              Streak: {streaks.walkingStreak} days
            </span>
          </div>

          {/* Running */}
          <div className="flex flex-col items-center justify-between rounded-xl border border-slate-100 bg-slate-50/50 p-4 dark:border-surface-800 dark:bg-surface-850/50">
            <ProgressRing
              percentage={Math.min(100, (currentWeekRunningKm / config.weeklyRunningKmTarget) * 100)}
              valueText={`${currentWeekRunningKm} km`}
              subText={`of ${config.weeklyRunningKmTarget} km wk`}
              label="Weekly Running"
              colorClass="text-violet-500"
            />
            <span className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              {todayPlan.runningKm ? `Today: ${todayPlan.runningKm} km` : "Rest day"}
            </span>
          </div>

          {/* Strength */}
          <div className="flex flex-col items-center justify-between rounded-xl border border-slate-100 bg-slate-50/50 p-4 dark:border-surface-800 dark:bg-surface-850/50">
            <ProgressRing
              percentage={todayRecord?.strengthCompleted ? 100 : todayPlan.hasStrength ? 0 : 100}
              valueText={
                todayRecord?.strengthCompleted
                  ? "Completed"
                  : todayPlan.hasStrength
                  ? todayRecord ? "Pending" : "Not recorded"
                  : "Rest Day"
              }
              subText={todayPlan.hasStrength ? todayPlan.strengthType?.slice(0, 14) : "Active rest"}
              label="Strength Session"
              colorClass="text-red-500"
            />
            <span className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              Week: {weekTotals.strength} / {config.weeklyStrengthSessionsTarget}
            </span>
          </div>

          {/* Weight */}
          <div className="flex flex-col items-center justify-between rounded-xl border border-slate-100 bg-slate-50/50 p-4 dark:border-surface-800 dark:bg-surface-850/50">
            <ProgressRing
              percentage={goalCompletionPct}
              valueText={
                todayRecord?.weightKg !== undefined ? `${todayRecord.weightKg} kg` : "Not recorded"
              }
              subText="Morning weight"
              label="Weight"
              colorClass="text-cyan-500"
            />
            <span className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              Target: {config.targetWeightKg} kg
            </span>
          </div>
        </div>
      </Card>

      {/* Workout Overview & Quick Trends Grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Today's Workout Card */}
        <Card
          title={`Today's Workout (${todayPlan.dayOfWeek})`}
          actions={
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setSelectedDate(todayStr);
                setCheckInOpen(true);
              }}
            >
              Log Today
            </Button>
          }
          className="lg:col-span-1"
        >
          <div className="space-y-4">
            <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-3 text-xs dark:border-surface-800 dark:bg-surface-850/80">
              <span className="font-semibold text-slate-900 dark:text-slate-100">
                Focus:
              </span>{" "}
              <span className="text-slate-600 dark:text-slate-400">{todayPlan.focus}</span>
            </div>

            <div className="space-y-2.5">
              <div className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-surface-800">
                <span className="flex items-center gap-2">
                  <span className="text-emerald-500">🚴‍♂️</span> Cycling
                </span>
                <span className="font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                  {todayRecord?.cyclingKm !== undefined ? `${todayRecord.cyclingKm} / ` : ""}{todayPlan.cyclingKm} km
                </span>
              </div>

              <div className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-surface-800">
                <span className="flex items-center gap-2">
                  <span className="text-blue-500">🚶‍♂️</span> Walking
                </span>
                <span className="font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                  {todayRecord?.walkingSteps !== undefined ? `${todayRecord.walkingSteps.toLocaleString()} / ` : ""}
                  {todayPlan.walkingSteps.toLocaleString()} steps
                </span>
              </div>

              {todayPlan.runningKm > 0 && (
                <div className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-surface-800">
                  <span className="flex items-center gap-2">
                    <span className="text-violet-500">🏃‍♂️</span> Running
                  </span>
                  <span className="font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                    {todayRecord?.runningKm !== undefined ? `${todayRecord.runningKm} / ` : ""}{todayPlan.runningKm} km
                  </span>
                </div>
              )}

              {todayPlan.hasStrength && (
                <div className="space-y-2 rounded-lg border border-slate-200 p-3 text-xs dark:border-surface-800">
                  <div className="flex items-center justify-between font-semibold text-slate-800 dark:text-slate-200">
                    <span className="flex items-center gap-1.5">
                      <span className="text-red-500">💪</span> {todayPlan.strengthType}
                    </span>
                    {todayRecord?.strengthCompleted && (
                      <Badge color="green">Completed</Badge>
                    )}
                  </div>
                  <ul className="space-y-1 pl-5 list-disc text-slate-600 dark:text-slate-400">
                    {todayPlan.exercises.map((ex) => (
                      <li key={ex.name}>
                        <span className="font-medium text-slate-700 dark:text-slate-300">{ex.name}</span>: {ex.target}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </Card>

        {/* Weight Trend Chart Preview & This Week */}
        <div className="space-y-6 lg:col-span-2">
          <Card title="Weight Progression & Rolling Trend">
            {chartData.length > 0 ? (
              <div className="h-60 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11 }} unit="kg" />
                    <Tooltip
                      formatter={(val: unknown) => [`${val} kg`]}
                      contentStyle={{ backgroundColor: "rgba(15, 23, 42, 0.9)", borderColor: "#334155", color: "#fff", fontSize: 12 }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <ReferenceLine y={config.targetWeightKg} stroke="#10b981" strokeDasharray="3 3" label={{ value: "Target 60kg", fill: "#10b981", fontSize: 10 }} />
                    <Line type="monotone" dataKey="actual" name="Actual Weight" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} />
                    <Line type="monotone" dataKey="rollingAvg" name="7-Day Rolling Avg" stroke="#f59e0b" strokeWidth={2} strokeDasharray="4 4" dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="flex h-60 flex-col items-center justify-center text-center text-xs text-slate-400">
                <span className="text-3xl">📈</span>
                <p className="mt-2 font-medium">No recorded weight entries yet</p>
                <p className="mt-1">Log your first morning weight check-in to begin tracking trend.</p>
              </div>
            )}
          </Card>

          {/* This Week Summary */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-surface-800 dark:bg-surface-900">
              <span className="text-xs font-semibold text-slate-500 uppercase">Week Cycling</span>
              <p className="mt-1 text-xl font-bold tabular-nums text-emerald-600 dark:text-emerald-400">
                {weekTotals.cycling} / 140 km
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-surface-800 dark:bg-surface-900">
              <span className="text-xs font-semibold text-slate-500 uppercase">Week Running</span>
              <p className="mt-1 text-xl font-bold tabular-nums text-violet-600 dark:text-violet-400">
                {weekTotals.running} / 20 km
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-surface-800 dark:bg-surface-900">
              <span className="text-xs font-semibold text-slate-500 uppercase">Week Walking</span>
              <p className="mt-1 text-xl font-bold tabular-nums text-blue-600 dark:text-blue-400">
                {weekTotals.walking.toLocaleString()} / 35k
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-surface-800 dark:bg-surface-900">
              <span className="text-xs font-semibold text-slate-500 uppercase">Week Strength</span>
              <p className="mt-1 text-xl font-bold tabular-nums text-red-600 dark:text-red-400">
                {weekTotals.strength} / 3
              </p>
            </div>
          </div>
        </div>
      </div>

      <DailyCheckInModal
        open={checkInOpen}
        onClose={() => setCheckInOpen(false)}
        initialDate={selectedDate}
      />
    </div>
  );
}
