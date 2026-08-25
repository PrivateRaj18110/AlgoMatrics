import { useMemo, useState } from "react";

import { Badge, Card } from "@/components/ui";
import {
  addDays,
  calculateMilestones,
  getTodayDateStr,
  getWeeklyReview,
} from "@/lib/personalHealthCalculations";
import { usePersonalHealth } from "@/stores/personalHealth";
import type { WeeklyReviewData } from "@/types/personalHealth";

export function PersonalHealthWeeklyReviewTab() {
  const config = usePersonalHealth((s) => s.config);
  const records = usePersonalHealth((s) => s.records);

  const todayStr = getTodayDateStr();
  const allRecords = useMemo(() => {
    return Object.values(records).sort((a, b) => a.date.localeCompare(b.date));
  }, [records]);

  // Generate weeks from program start (25 Aug 2026) to today or end
  const weeklyReviews = useMemo(() => {
    const list: WeeklyReviewData[] = [];
    let curWeekStart = config.startDate;
    let weekNum = 1;

    while (curWeekStart <= config.endDate) {
      const review = getWeeklyReview(records, curWeekStart, weekNum, config);
      list.push(review);
      curWeekStart = addDays(curWeekStart, 7);
      weekNum++;
    }

    return list;
  }, [records, config]);

  const [selectedWeekNum, setSelectedWeekNum] = useState<number>(1);

  // Find the current active week based on today's date
  const currentWeekReview = useMemo(() => {
    return (
      weeklyReviews.find((w) => todayStr >= w.startDate && todayStr <= w.endDate) ||
      weeklyReviews[0]
    );
  }, [weeklyReviews, todayStr]);

  const activeReview = useMemo(() => {
    return weeklyReviews.find((w) => w.weekNumber === selectedWeekNum) || currentWeekReview;
  }, [weeklyReviews, selectedWeekNum, currentWeekReview]);

  const milestones = useMemo(
    () => calculateMilestones(allRecords, config),
    [allRecords, config],
  );

  return (
    <div className="space-y-6">
      {/* 1. Milestone Achievements */}
      <Card title="Program Milestones">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {milestones.map((m) => (
            <div
              key={m.id}
              className={`rounded-xl border p-4 transition-colors ${
                m.achieved
                  ? "border-emerald-500/40 bg-emerald-500/5 dark:bg-emerald-500/10"
                  : "border-slate-200 bg-white dark:border-surface-800 dark:bg-surface-900"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">
                  {m.category}
                </span>
                <Badge color={m.achieved ? "green" : "slate"}>
                  {m.achieved ? "Achieved ✓" : `${m.progressPct}%`}
                </Badge>
              </div>
              <h4 className="mt-2 text-sm font-bold text-slate-900 dark:text-slate-100">
                {m.title}
              </h4>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{m.description}</p>
              <div className="mt-3 flex items-center justify-between text-xs text-slate-600 dark:text-slate-300">
                <span>Current: {m.currentValue}</span>
                <span>Target: {m.targetValue}</span>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* 2. Weekly Review Selector & Details */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-bold text-slate-900 dark:text-white">
            Weekly Summary & Performance Review
          </h3>
          <p className="text-xs text-slate-500">
            Week {activeReview.weekNumber} ({activeReview.startDate} → {activeReview.endDate})
          </p>
        </div>

        {/* Week Selector Tabs */}
        <div className="flex flex-wrap gap-1.5">
          {weeklyReviews.slice(0, 14).map((w) => (
            <button
              key={w.weekNumber}
              type="button"
              onClick={() => setSelectedWeekNum(w.weekNumber)}
              className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition-colors ${
                activeReview.weekNumber === w.weekNumber
                  ? "bg-accent-600 text-white shadow-xs"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-surface-800 dark:text-slate-300"
              }`}
            >
              W{w.weekNumber}
            </button>
          ))}
        </div>
      </div>

      {/* Active Week Summary Card */}
      <Card title={`Week ${activeReview.weekNumber} Review (${activeReview.startDate} to ${activeReview.endDate})`}>
        <div className="space-y-6">
          {/* Top Metrics Grid */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <div className="rounded-xl border border-slate-200 p-3 dark:border-surface-800">
              <span className="text-xs text-slate-500">Start / End Weight</span>
              <p className="mt-1 text-lg font-bold text-slate-900 dark:text-slate-100">
                {activeReview.startingWeightKg ? `${activeReview.startingWeightKg}` : "—"} /{" "}
                {activeReview.endingWeightKg ? `${activeReview.endingWeightKg} kg` : "—"}
              </p>
              <span className="text-xs text-slate-400">
                {activeReview.weightChangeKg !== null
                  ? `${activeReview.weightChangeKg > 0 ? "+" : ""}${activeReview.weightChangeKg} kg`
                  : "No weight change"}
              </span>
            </div>

            <div className="rounded-xl border border-slate-200 p-3 dark:border-surface-800">
              <span className="text-xs text-slate-500">Average Calories</span>
              <p className="mt-1 text-lg font-bold text-amber-600 dark:text-amber-400">
                {activeReview.avgCalories ? `${activeReview.avgCalories} kcal` : "—"}
              </p>
              <span className="text-xs text-slate-400">Target: 1,600 kcal</span>
            </div>

            <div className="rounded-xl border border-slate-200 p-3 dark:border-surface-800">
              <span className="text-xs text-slate-500">Total Cycling</span>
              <p className="mt-1 text-lg font-bold text-emerald-600 dark:text-emerald-400">
                {activeReview.totalCyclingKm} / {activeReview.targetCyclingKm} km
              </p>
              <span className="text-xs text-slate-400">7 x 20 km daily</span>
            </div>

            <div className="rounded-xl border border-slate-200 p-3 dark:border-surface-800">
              <span className="text-xs text-slate-500">Total Running</span>
              <p className="mt-1 text-lg font-bold text-violet-600 dark:text-violet-400">
                {activeReview.totalRunningKm} / {activeReview.targetRunningKm} km
              </p>
              <span className="text-xs text-slate-400">5k + 5k + 10k</span>
            </div>

            <div className="rounded-xl border border-slate-200 p-3 dark:border-surface-800">
              <span className="text-xs text-slate-500">Total Walking</span>
              <p className="mt-1 text-lg font-bold text-blue-600 dark:text-blue-400">
                {activeReview.totalWalkingSteps.toLocaleString()} steps
              </p>
              <span className="text-xs text-slate-400">Target: 35,000</span>
            </div>

            <div className="rounded-xl border border-slate-200 p-3 dark:border-surface-800">
              <span className="text-xs text-slate-500">Strength Sessions</span>
              <p className="mt-1 text-lg font-bold text-red-600 dark:text-red-400">
                {activeReview.strengthSessionsCompleted} / {activeReview.targetStrengthSessions}
              </p>
              <span className="text-xs text-slate-400">Mon, Wed, Fri</span>
            </div>
          </div>

          {/* Completion & Best Day */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-surface-800 dark:bg-surface-850">
              <span className="text-xs font-semibold text-slate-500 uppercase">Workout Completion Rate</span>
              <p className="mt-1 text-2xl font-bold text-slate-900 dark:text-slate-100">
                {activeReview.workoutCompletionPct}%
              </p>
              <p className="mt-1 text-xs text-slate-400">
                {activeReview.daysRecorded} of 7 days logged
              </p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-surface-800 dark:bg-surface-850">
              <span className="text-xs font-semibold text-slate-500 uppercase">Best Performance Day</span>
              <p className="mt-1 text-base font-bold text-emerald-600 dark:text-emerald-400">
                {activeReview.bestDay ? `${activeReview.bestDay.date} (${activeReview.bestDay.score}%)` : "—"}
              </p>
              <p className="mt-1 text-xs text-slate-400">Highest daily adherence score</p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-surface-800 dark:bg-surface-850">
              <span className="text-xs font-semibold text-slate-500 uppercase">Missed Targets</span>
              {activeReview.missedTargets.length > 0 ? (
                <ul className="mt-1 list-disc pl-4 text-xs text-amber-600 dark:text-amber-400">
                  {activeReview.missedTargets.map((m) => (
                    <li key={m}>{m}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-xs font-medium text-emerald-600">All weekly targets met! 🎉</p>
              )}
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
