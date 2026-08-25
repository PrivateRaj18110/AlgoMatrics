import { useMemo, useState } from "react";

import {
  addDays,
  calculateDailyScore,
  diffDays,
  getTodayDateStr,
  getWorkoutPlanForDay,
} from "@/lib/personalHealthCalculations";
import { DailyCheckInModal } from "./DailyCheckInModal";
import { usePersonalHealth } from "@/stores/personalHealth";

export function PersonalHealthCalendarTab() {
  const config = usePersonalHealth((s) => s.config);
  const records = usePersonalHealth((s) => s.records);

  const [checkInOpen, setCheckInOpen] = useState(false);
  const [selectedDate, setSelectedDate] = useState(getTodayDateStr());
  const [filterMonth, setFilterMonth] = useState<string>("all"); // "all" | "2026-08" | "2026-09" | "2026-10" | "2026-11"

  const todayStr = getTodayDateStr();

  // Generate all dates from start to end (Aug 25 -> Nov 30)
  const allProgramDates = useMemo(() => {
    const dates: string[] = [];
    let cur = config.startDate;
    while (cur <= config.endDate) {
      dates.push(cur);
      cur = addDays(cur, 1);
    }
    return dates;
  }, [config.startDate, config.endDate]);

  const displayedDates = useMemo(() => {
    if (filterMonth === "all") return allProgramDates;
    return allProgramDates.filter((d) => d.startsWith(filterMonth));
  }, [allProgramDates, filterMonth]);

  function getStatus(dateStr: string) {
    const record = records[dateStr];
    const plan = getWorkoutPlanForDay(dateStr);
    const isPast = dateStr < todayStr;
    const isToday = dateStr === todayStr;

    if (!record) {
      if (isPast) {
        return {
          label: "Missed",
          color: "bg-slate-100 text-slate-400 border-slate-200 dark:bg-surface-850 dark:border-surface-800",
          badge: "slate",
        };
      }
      return {
        label: isToday ? "Today (Planned)" : "Planned",
        color: "bg-blue-50/60 text-blue-700 border-blue-200 dark:bg-blue-950/20 dark:border-blue-900/40 dark:text-blue-300",
        badge: "blue",
      };
    }

    const score = calculateDailyScore(record, plan, config);
    if (score >= 60) {
      return {
        label: `Completed (${score}%)`,
        color: "bg-emerald-50 text-emerald-800 border-emerald-300 dark:bg-emerald-950/30 dark:border-emerald-800 dark:text-emerald-300",
        badge: "green",
      };
    }
    return {
      label: `Partial (${score}%)`,
      color: "bg-amber-50 text-amber-800 border-amber-300 dark:bg-amber-950/30 dark:border-amber-800 dark:text-amber-300",
      badge: "amber",
    };
  }

  return (
    <div className="space-y-6">
      {/* Filter & Legend Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-bold text-slate-900 dark:text-white">
            Program Calendar (25 August 2026 → 30 November 2026)
          </h3>
          <p className="text-xs text-slate-500">
            Click any day to view or edit workout, calories, and weight details.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Month selector */}
          <div className="flex gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1 dark:border-surface-800 dark:bg-surface-850">
            {[
              { id: "all", label: "All Program (98 Days)" },
              { id: "2026-08", label: "Aug" },
              { id: "2026-09", label: "Sep" },
              { id: "2026-10", label: "Oct" },
              { id: "2026-11", label: "Nov" },
            ].map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => setFilterMonth(m.id)}
                className={`rounded px-2.5 py-1 text-xs font-semibold transition-colors ${
                  filterMonth === m.id
                    ? "bg-white text-accent-600 shadow-xs dark:bg-surface-700 dark:text-accent-300"
                    : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Color Code Legend */}
      <div className="flex flex-wrap items-center gap-4 text-xs">
        <span className="font-semibold text-slate-500">Status Legend:</span>
        <span className="flex items-center gap-1.5">
          <span className="size-3 rounded-full bg-blue-500" /> Planned / Upcoming
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-3 rounded-full bg-emerald-500" /> Completed (≥60%)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-3 rounded-full bg-amber-500" /> Partially Completed
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-3 rounded-full bg-slate-300 dark:bg-slate-700" /> Missed / Unrecorded
        </span>
      </div>

      {/* Calendar Grid */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7">
        {displayedDates.map((dateStr) => {
          const plan = getWorkoutPlanForDay(dateStr);
          const record = records[dateStr];
          const status = getStatus(dateStr);
          const isToday = dateStr === todayStr;
          const dayNum = diffDays(config.startDate, dateStr) + 1;

          return (
            <div
              key={dateStr}
              onClick={() => {
                setSelectedDate(dateStr);
                setCheckInOpen(true);
              }}
              className={`cursor-pointer rounded-xl border p-3.5 transition-all hover:scale-[1.02] hover:shadow-md ${status.color} ${
                isToday ? "ring-2 ring-accent-500 shadow-sm" : ""
              }`}
            >
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs font-bold">{plan.dayOfWeek.slice(0, 3)}</span>
                  <span className="ml-1 text-xs opacity-75">{dateStr.slice(5)}</span>
                </div>
                <span className="text-[10px] font-semibold opacity-80">Day {dayNum}</span>
              </div>

              <div className="mt-2 text-xs">
                <span className="font-semibold">{status.label}</span>
              </div>

              {/* Day metrics breakdown */}
              <div className="mt-2.5 space-y-1 text-[11px] opacity-90 border-t border-current/15 pt-2">
                <div className="flex items-center justify-between">
                  <span>🚴‍♂️ Cycling:</span>
                  <span className="font-semibold tabular-nums">
                    {record?.cyclingKm !== undefined ? `${record.cyclingKm} / ` : ""}{plan.cyclingKm} km
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span>🚶‍♂️ Steps:</span>
                  <span className="font-semibold tabular-nums">
                    {record?.walkingSteps !== undefined ? `${record.walkingSteps.toLocaleString()}` : "5k plan"}
                  </span>
                </div>

                {plan.runningKm > 0 && (
                  <div className="flex items-center justify-between">
                    <span>🏃‍♂️ Run:</span>
                    <span className="font-semibold tabular-nums">
                      {record?.runningKm !== undefined ? `${record.runningKm} / ` : ""}{plan.runningKm} km
                    </span>
                  </div>
                )}

                {record?.weightKg && (
                  <div className="flex items-center justify-between text-slate-900 font-bold dark:text-white">
                    <span>⚖️ Weight:</span>
                    <span className="tabular-nums">{record.weightKg} kg</span>
                  </div>
                )}

                {record?.caloriesConsumed && (
                  <div className="flex items-center justify-between">
                    <span>🍎 Cals:</span>
                    <span className="tabular-nums">{record.caloriesConsumed} kcal</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <DailyCheckInModal
        open={checkInOpen}
        onClose={() => setCheckInOpen(false)}
        initialDate={selectedDate}
      />
    </div>
  );
}
