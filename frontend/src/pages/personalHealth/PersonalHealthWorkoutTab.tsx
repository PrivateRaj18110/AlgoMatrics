import { useState } from "react";

import { Badge, Button, Card } from "@/components/ui";
import {
  getTodayDateStr,
  getWorkoutPlanForDay,
  WEEKLY_SCHEDULE,
} from "@/lib/personalHealthCalculations";
import { DailyCheckInModal } from "./DailyCheckInModal";
import { usePersonalHealth } from "@/stores/personalHealth";
import type { WeekdayName } from "@/types/personalHealth";

export function PersonalHealthWorkoutTab() {
  const records = usePersonalHealth((s) => s.records);
  const todayStr = getTodayDateStr();
  const todayPlan = getWorkoutPlanForDay(todayStr);
  const todayRecord = records[todayStr];

  const [checkInOpen, setCheckInOpen] = useState(false);
  const [selectedDate, setSelectedDate] = useState(todayStr);

  const daysOrder: WeekdayName[] = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
  ];

  return (
    <div className="space-y-6">
      {/* Today's Workout Focus */}
      <Card
        title={`Today's Workout — ${todayPlan.dayOfWeek}`}
        actions={
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              setSelectedDate(todayStr);
              setCheckInOpen(true);
            }}
          >
            {todayRecord ? "Edit Today's Workout" : "Log Today's Workout"}
          </Button>
        }
      >
        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-accent-500/20 bg-accent-500/5 p-4 dark:bg-accent-500/10">
            <div>
              <p className="text-xs font-semibold tracking-wider text-accent-700 uppercase dark:text-accent-300">
                Daily Focus
              </p>
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                {todayPlan.focus}
              </h3>
            </div>
            {todayPlan.recoveryFocus && (
              <Badge color="blue">{todayPlan.recoveryFocus}</Badge>
            )}
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {/* Cycling */}
            <div className="rounded-xl border border-slate-200 p-4 dark:border-surface-800">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-200">
                  <span className="text-emerald-500 text-lg">🚴‍♂️</span> Cycling
                </span>
                <Badge color={todayRecord?.cyclingKm ? "green" : "slate"}>
                  {todayRecord?.cyclingKm !== undefined ? `${todayRecord.cyclingKm} km` : "Pending"}
                </Badge>
              </div>
              <p className="mt-2 text-2xl font-bold tabular-nums text-slate-900 dark:text-slate-100">
                {todayPlan.cyclingKm} km
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Intensity: {todayPlan.cyclingIntensity === "easy" ? "Easy Recovery" : "Moderate Pace"}
              </p>
            </div>

            {/* Walking */}
            <div className="rounded-xl border border-slate-200 p-4 dark:border-surface-800">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-200">
                  <span className="text-blue-500 text-lg">🚶‍♂️</span> Walking
                </span>
                <Badge color={todayRecord?.walkingSteps ? "green" : "slate"}>
                  {todayRecord?.walkingSteps !== undefined ? `${todayRecord.walkingSteps.toLocaleString()} steps` : "Pending"}
                </Badge>
              </div>
              <p className="mt-2 text-2xl font-bold tabular-nums text-slate-900 dark:text-slate-100">
                {todayPlan.walkingSteps.toLocaleString()} steps
              </p>
              <p className="mt-1 text-xs text-slate-500">Daily baseline NEAT cardio</p>
            </div>

            {/* Running */}
            <div className="rounded-xl border border-slate-200 p-4 dark:border-surface-800">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-200">
                  <span className="text-violet-500 text-lg">🏃‍♂️</span> Running
                </span>
                <Badge color={todayRecord?.runningKm ? "green" : "slate"}>
                  {todayRecord?.runningKm !== undefined ? `${todayRecord.runningKm} km` : todayPlan.runningKm > 0 ? "Pending" : "Rest"}
                </Badge>
              </div>
              <p className="mt-2 text-2xl font-bold tabular-nums text-slate-900 dark:text-slate-100">
                {todayPlan.runningKm > 0 ? `${todayPlan.runningKm} km` : "Rest"}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {todayPlan.runningKm > 0 ? "Paced aerobic run" : "No running scheduled"}
              </p>
            </div>
          </div>

          {/* Strength Exercises Detail */}
          {todayPlan.hasStrength ? (
            <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50/50 p-4 dark:border-surface-800 dark:bg-surface-850/50">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                    💪 Planned Strength Session: {todayPlan.strengthType}
                  </h4>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Perform 3 controlled sets with 60–90 seconds rest between sets.
                  </p>
                </div>
                {todayRecord?.strengthCompleted && (
                  <Badge color="green">Session Marked Done</Badge>
                )}
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {todayPlan.exercises.map((ex) => (
                  <div
                    key={ex.name}
                    className="flex items-center justify-between rounded-lg border border-slate-200 bg-white p-3 shadow-xs dark:border-surface-700 dark:bg-surface-900"
                  >
                    <div>
                      <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                        {ex.name}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">{ex.target}</p>
                    </div>
                    {ex.setsReps && (
                      <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-surface-800 dark:text-slate-300">
                        {ex.setsReps}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-slate-200 p-4 text-center text-sm text-slate-500 dark:border-surface-800">
              🛌 No heavy strength workout scheduled today. Focus on mobility, hydration, and nutrition.
            </div>
          )}

          {/* Today's recorded notes if any */}
          {(todayRecord?.notes || todayRecord?.recoveryNotes) && (
            <div className="rounded-lg border border-slate-200 bg-white p-3 text-xs dark:border-surface-800 dark:bg-surface-900">
              {todayRecord.notes && (
                <p>
                  <span className="font-semibold text-slate-700 dark:text-slate-300">Workout Notes:</span>{" "}
                  {todayRecord.notes}
                </p>
              )}
              {todayRecord.recoveryNotes && (
                <p className="mt-1">
                  <span className="font-semibold text-slate-700 dark:text-slate-300">Recovery Notes:</span>{" "}
                  {todayRecord.recoveryNotes}
                </p>
              )}
            </div>
          )}
        </div>
      </Card>

      {/* Full Week Schedule (Mon–Sun) */}
      <Card title="This Week's Complete Schedule (Monday → Sunday)">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-lg bg-slate-50 p-3 text-xs dark:bg-surface-850">
              <span className="text-slate-500">Weekly Cycling</span>
              <p className="mt-1 text-lg font-bold text-emerald-600 dark:text-emerald-400">140 km</p>
            </div>
            <div className="rounded-lg bg-slate-50 p-3 text-xs dark:bg-surface-850">
              <span className="text-slate-500">Weekly Running</span>
              <p className="mt-1 text-lg font-bold text-violet-600 dark:text-violet-400">20 km</p>
            </div>
            <div className="rounded-lg bg-slate-50 p-3 text-xs dark:bg-surface-850">
              <span className="text-slate-500">Weekly Walking</span>
              <p className="mt-1 text-lg font-bold text-blue-600 dark:text-blue-400">35,000 steps</p>
            </div>
            <div className="rounded-lg bg-slate-50 p-3 text-xs dark:bg-surface-850">
              <span className="text-slate-500">Weekly Strength</span>
              <p className="mt-1 text-lg font-bold text-red-600 dark:text-red-400">3 sessions</p>
            </div>
          </div>

          <div className="space-y-3">
            {daysOrder.map((dayName) => {
              const dayPlan = WEEKLY_SCHEDULE[dayName];
              const isToday = dayName === todayPlan.dayOfWeek;

              return (
                <div
                  key={dayName}
                  className={`rounded-xl border p-4 transition-colors ${
                    isToday
                      ? "border-accent-500 bg-accent-500/5 dark:bg-accent-500/10"
                      : "border-slate-200 bg-white hover:bg-slate-50/50 dark:border-surface-800 dark:bg-surface-900 dark:hover:bg-surface-850/50"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-2 dark:border-surface-800">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-slate-900 dark:text-white">{dayName}</span>
                      {isToday && <Badge color="blue">Today</Badge>}
                    </div>
                    <span className="text-xs text-slate-500 dark:text-slate-400">{dayPlan.focus}</span>
                  </div>

                  <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div className="text-xs">
                      <span className="font-medium text-slate-500">Cardio:</span>
                      <p className="font-semibold text-slate-800 dark:text-slate-200">
                        🚴‍♂️ {dayPlan.cyclingKm} km cycling {dayPlan.cyclingIntensity === "easy" ? "(Easy)" : ""} + 🚶‍♂️ 5k steps
                        {dayPlan.runningKm > 0 ? ` + 🏃‍♂️ ${dayPlan.runningKm} km run` : ""}
                      </p>
                    </div>

                    <div className="text-xs sm:col-span-2">
                      <span className="font-medium text-slate-500">
                        {dayPlan.hasStrength ? `Strength (${dayPlan.strengthType}):` : "Strength / Recovery:"}
                      </span>
                      {dayPlan.exercises.length > 0 ? (
                        <p className="text-slate-700 dark:text-slate-300">
                          {dayPlan.exercises.map((e) => `${e.name} (${e.target})`).join(", ")}
                        </p>
                      ) : (
                        <p className="text-slate-500 dark:text-slate-400">
                          {dayPlan.recoveryFocus || "Active recovery, stretching, and early sleep."}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </Card>

      <DailyCheckInModal
        open={checkInOpen}
        onClose={() => setCheckInOpen(false)}
        initialDate={selectedDate}
      />
    </div>
  );
}
