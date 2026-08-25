import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
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

import { Card } from "@/components/ui";
import {
  calculate7DayRollingAvg,
  calculateWeightPrediction,
  diffDays,
  getTodayDateStr,
} from "@/lib/personalHealthCalculations";
import { usePersonalHealth } from "@/stores/personalHealth";

export function PersonalHealthProgressTab() {
  const config = usePersonalHealth((s) => s.config);
  const records = usePersonalHealth((s) => s.records);

  const [activeRange, setActiveRange] = useState<"7d" | "30d" | "all">("all");

  const allRecords = useMemo(() => {
    return Object.values(records).sort((a, b) => a.date.localeCompare(b.date));
  }, [records]);
  const todayStr = getTodayDateStr();

  // Filter records by range for charts
  const filteredRecords = useMemo(() => {
    if (activeRange === "7d") {
      return allRecords.filter((r) => diffDays(r.date, todayStr) <= 7 && diffDays(r.date, todayStr) >= 0);
    }
    if (activeRange === "30d") {
      return allRecords.filter((r) => diffDays(r.date, todayStr) <= 30 && diffDays(r.date, todayStr) >= 0);
    }
    return allRecords;
  }, [allRecords, activeRange, todayStr]);

  // Weight Trend Data
  const weightData = useMemo(() => {
    return filteredRecords
      .filter((r) => r.weightKg !== undefined && r.weightKg > 0)
      .map((r) => ({
        date: r.date.slice(5),
        actual: r.weightKg,
        rollingAvg: calculate7DayRollingAvg(allRecords, r.date),
        target: config.targetWeightKg,
      }));
  }, [filteredRecords, allRecords, config.targetWeightKg]);

  // Prediction
  const prediction = useMemo(
    () => calculateWeightPrediction(allRecords, config),
    [allRecords, config],
  );

  // Cardio & Calorie time-series data
  const cardioData = useMemo(() => {
    return filteredRecords.map((r) => ({
      date: r.date.slice(5),
      cycling: r.cyclingKm || 0,
      cyclingTarget: config.dailyCyclingKmTarget,
      running: r.runningKm || 0,
      walking: r.walkingSteps || 0,
      walkingTarget: config.dailyWalkingStepsTarget,
      calories: r.caloriesConsumed || 0,
      caloriesTarget: config.dailyCaloriesTarget,
      sleep: r.sleepHours || 0,
      energy: r.energyLevel || 0,
      soreness: r.sorenessLevel || 0,
    }));
  }, [filteredRecords, config]);

  // Aggregated Exercise Totals
  const exerciseTotals = useMemo(() => {
    let totalCycling = 0;
    let totalRunning = 0;
    let totalWalking = 0;
    let totalPushUps = 0;
    let totalCrunches = 0;
    let totalSquats = 0;
    let totalLunges = 0;
    let totalPlankSec = 0;
    let strengthSessions = 0;
    let calSum = 0;
    let calCount = 0;

    for (const r of allRecords) {
      if (r.cyclingKm) totalCycling += r.cyclingKm;
      if (r.runningKm) totalRunning += r.runningKm;
      if (r.walkingSteps) totalWalking += r.walkingSteps;
      if (r.pushUps) totalPushUps += r.pushUps;
      if (r.crunches) totalCrunches += r.crunches;
      if (r.squats) totalSquats += r.squats;
      if (r.lunges) totalLunges += r.lunges;
      if (r.plankSeconds) totalPlankSec += r.plankSeconds;
      if (r.strengthCompleted) strengthSessions++;
      if (r.caloriesConsumed) {
        calSum += r.caloriesConsumed;
        calCount++;
      }
    }

    return {
      totalCycling,
      totalRunning,
      totalWalking,
      totalPushUps,
      totalCrunches,
      totalSquats,
      totalLunges,
      totalPlankMin: Math.round(totalPlankSec / 60),
      strengthSessions,
      avgCalories: calCount > 0 ? Math.round(calSum / calCount) : null,
    };
  }, [allRecords]);

  return (
    <div className="space-y-6">
      {/* Time Range Selector */}
      <div className="flex items-center justify-between">
        <h3 className="text-base font-bold text-slate-900 dark:text-white">
          Analytics & Progress Progression
        </h3>
        <div className="flex gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1 dark:border-surface-800 dark:bg-surface-850">
          {(["7d", "30d", "all"] as const).map((range) => (
            <button
              key={range}
              type="button"
              onClick={() => setActiveRange(range)}
              className={`rounded-md px-3 py-1 text-xs font-semibold transition-colors ${
                activeRange === range
                  ? "bg-white text-accent-600 shadow-xs dark:bg-surface-700 dark:text-accent-300"
                  : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
              }`}
            >
              {range === "7d" ? "Last 7 Days" : range === "30d" ? "Last 30 Days" : "All Program"}
            </button>
          ))}
        </div>
      </div>

      {/* 1. Weight Progression & Prediction */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card title="Weight Loss Trend (Actual vs 7-Day Rolling Avg)" className="lg:col-span-2">
          {weightData.length > 0 ? (
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={weightData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11 }} unit="kg" />
                  <Tooltip
                    formatter={(val: unknown) => [`${val} kg`]}
                    contentStyle={{ backgroundColor: "rgba(15, 23, 42, 0.9)", borderColor: "#334155", color: "#fff", fontSize: 12 }}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <ReferenceLine y={config.startingWeightKg} stroke="#64748b" strokeDasharray="4 4" label={{ value: "Start 70kg", fill: "#64748b", fontSize: 10 }} />
                  <ReferenceLine y={config.targetWeightKg} stroke="#10b981" strokeDasharray="3 3" label={{ value: "Target 60kg", fill: "#10b981", fontSize: 10 }} />
                  <Line type="monotone" dataKey="actual" name="Actual Weight" stroke="#3b82f6" strokeWidth={2.5} dot={{ r: 3.5 }} />
                  <Line type="monotone" dataKey="rollingAvg" name="7-Day Rolling Avg" stroke="#f59e0b" strokeWidth={2} strokeDasharray="4 4" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="flex h-72 flex-col items-center justify-center text-center text-xs text-slate-400">
              <p>No weight records logged yet.</p>
            </div>
          )}
        </Card>

        {/* Prediction Card */}
        <Card title="Weight Loss Forecast" className="lg:col-span-1">
          <div className="space-y-4">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs dark:border-surface-800 dark:bg-surface-850">
              <span className="font-bold text-slate-900 dark:text-slate-100">
                ESTIMATE — NOT A GUARANTEE
              </span>
              <p className="mt-1 text-slate-500">
                Linear projection based strictly on recorded weight entries.
              </p>
            </div>

            {prediction.hasTrend ? (
              <div className="space-y-3">
                <div className="rounded-lg border border-slate-200 p-3 text-sm dark:border-surface-800">
                  <span className="text-xs text-slate-500">Daily Loss Rate:</span>
                  <p className="text-lg font-bold text-profit-600 dark:text-profit-400">
                    -{prediction.dailyLossRateKg} kg / day
                  </p>
                </div>

                <div className="space-y-2 text-xs">
                  <div className="flex items-center justify-between border-b border-slate-200 pb-1.5 dark:border-surface-800">
                    <span className="text-slate-600 dark:text-slate-400">Estimated 65.0 kg:</span>
                    <span className="font-bold text-slate-900 dark:text-slate-100">
                      {prediction.estimatedDate65kg || "Reached"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between border-b border-slate-200 pb-1.5 dark:border-surface-800">
                    <span className="text-slate-600 dark:text-slate-400">Estimated 62.0 kg:</span>
                    <span className="font-bold text-slate-900 dark:text-slate-100">
                      {prediction.estimatedDate62kg || "Reached"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between border-b border-slate-200 pb-1.5 dark:border-surface-800">
                    <span className="text-slate-600 dark:text-slate-400">Estimated 60.0 kg Target:</span>
                    <span className="font-bold text-accent-600 dark:text-accent-400">
                      {prediction.estimatedDate60kg || "Reached"}
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="rounded-lg border border-dashed border-slate-300 p-4 text-center text-xs text-slate-500 dark:border-surface-700">
                {prediction.message}
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* 2. Cardio Analytics (Cycling & Running) */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Cycling Distance (km / day)">
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={cardioData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} unit="km" />
                <Tooltip
                  formatter={(val: unknown) => [`${val} km`]}
                  contentStyle={{ backgroundColor: "rgba(15, 23, 42, 0.9)", borderColor: "#334155", color: "#fff", fontSize: 12 }}
                />
                <ReferenceLine y={config.dailyCyclingKmTarget} stroke="#10b981" strokeDasharray="3 3" label={{ value: "20km Target", fill: "#10b981", fontSize: 10 }} />
                <Bar dataKey="cycling" name="Cycling km" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
            <span>Program Total: <strong className="text-slate-900 dark:text-slate-100">{exerciseTotals.totalCycling} km</strong></span>
            <span>Target: 20 km / day</span>
          </div>
        </Card>

        <Card title="Running Distance (km / day)">
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={cardioData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} unit="km" />
                <Tooltip
                  formatter={(val: unknown) => [`${val} km`]}
                  contentStyle={{ backgroundColor: "rgba(15, 23, 42, 0.9)", borderColor: "#334155", color: "#fff", fontSize: 12 }}
                />
                <Bar dataKey="running" name="Running km" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
            <span>Program Total: <strong className="text-slate-900 dark:text-slate-100">{exerciseTotals.totalRunning} km</strong></span>
            <span>Weekly Target: 20 km</span>
          </div>
        </Card>
      </div>

      {/* 3. Strength Volume & Calorie Analytics */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card title="Cumulative Strength Reps" className="lg:col-span-1">
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-slate-200 p-3 text-center dark:border-surface-800">
              <span className="text-xs text-slate-500">Push-ups</span>
              <p className="mt-1 text-xl font-bold tabular-nums text-slate-900 dark:text-slate-100">
                {exerciseTotals.totalPushUps}
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 p-3 text-center dark:border-surface-800">
              <span className="text-xs text-slate-500">Crunches</span>
              <p className="mt-1 text-xl font-bold tabular-nums text-slate-900 dark:text-slate-100">
                {exerciseTotals.totalCrunches}
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 p-3 text-center dark:border-surface-800">
              <span className="text-xs text-slate-500">Squats</span>
              <p className="mt-1 text-xl font-bold tabular-nums text-slate-900 dark:text-slate-100">
                {exerciseTotals.totalSquats}
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 p-3 text-center dark:border-surface-800">
              <span className="text-xs text-slate-500">Lunges</span>
              <p className="mt-1 text-xl font-bold tabular-nums text-slate-900 dark:text-slate-100">
                {exerciseTotals.totalLunges}
              </p>
            </div>
          </div>
          <div className="mt-3 flex items-center justify-between rounded-lg bg-slate-50 p-3 text-xs dark:bg-surface-850">
            <span>Plank Hold Time:</span>
            <span className="font-bold text-slate-900 dark:text-slate-100">{exerciseTotals.totalPlankMin} minutes</span>
          </div>
        </Card>

        <Card title="Calorie Intake (kcal / day)" className="lg:col-span-2">
          <div className="h-60 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={cardioData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  formatter={(val: unknown) => [`${val} kcal`]}
                  contentStyle={{ backgroundColor: "rgba(15, 23, 42, 0.9)", borderColor: "#334155", color: "#fff", fontSize: 12 }}
                />
                <ReferenceLine y={config.dailyCaloriesTarget} stroke="#f59e0b" strokeDasharray="3 3" label={{ value: "1,600 Target", fill: "#f59e0b", fontSize: 10 }} />
                <Bar dataKey="calories" name="Calories Consumed" fill="#f59e0b" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
            <span>Avg Intake: <strong className="text-slate-900 dark:text-slate-100">{exerciseTotals.avgCalories ? `${exerciseTotals.avgCalories} kcal` : "—"}</strong></span>
            <span>Target: 1,600 kcal / day</span>
          </div>
        </Card>
      </div>

      {/* 4. Sleep & Recovery Trends */}
      <Card title="Sleep Duration & Energy Levels">
        <div className="h-56 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={cardioData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="sleep" orientation="left" tick={{ fontSize: 11 }} unit="h" />
              <YAxis yAxisId="energy" orientation="right" domain={[0, 10]} tick={{ fontSize: 11 }} unit="/10" />
              <Tooltip
                contentStyle={{ backgroundColor: "rgba(15, 23, 42, 0.9)", borderColor: "#334155", color: "#fff", fontSize: 12 }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <ReferenceLine yAxisId="sleep" y={7.5} stroke="#3b82f6" strokeDasharray="3 3" label={{ value: "7.5h Sleep", fill: "#3b82f6", fontSize: 10 }} />
              <Line yAxisId="sleep" type="monotone" dataKey="sleep" name="Sleep Hours" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} />
              <Line yAxisId="energy" type="monotone" dataKey="energy" name="Energy Level (1-10)" stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} />
              <Line yAxisId="energy" type="monotone" dataKey="soreness" name="Muscle Soreness (1-10)" stroke="#ef4444" strokeWidth={1.5} strokeDasharray="3 3" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  );
}
