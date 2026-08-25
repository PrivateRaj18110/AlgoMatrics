import { useState } from "react";

import { PersonalHealthCalendarTab } from "./PersonalHealthCalendarTab";
import { PersonalHealthDashboard } from "./PersonalHealthDashboard";
import { PersonalHealthProgressTab } from "./PersonalHealthProgressTab";
import { PersonalHealthSettingsTab } from "./PersonalHealthSettingsTab";
import { PersonalHealthWeeklyReviewTab } from "./PersonalHealthWeeklyReviewTab";
import { PersonalHealthWorkoutTab } from "./PersonalHealthWorkoutTab";

type PersonalHealthTab =
  | "dashboard"
  | "workout"
  | "progress"
  | "weekly-review"
  | "calendar"
  | "settings";

const TABS: { id: PersonalHealthTab; label: string; icon: string }[] = [
  { id: "dashboard", label: "Dashboard", icon: "📊" },
  { id: "workout", label: "Workout", icon: "💪" },
  { id: "progress", label: "Progress & Analytics", icon: "📈" },
  { id: "weekly-review", label: "Weekly Review", icon: "🗓️" },
  { id: "calendar", label: "Calendar", icon: "📅" },
  { id: "settings", label: "Settings", icon: "⚙️" },
];

export function PersonalHealthPage() {
  const [activeTab, setActiveTab] = useState<PersonalHealthTab>("dashboard");

  return (
    <div className="space-y-6">
      {/* Top Tab Navigation Bar */}
      <div className="flex items-center gap-1.5 overflow-x-auto border-b border-slate-200 pb-2 dark:border-surface-800">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium whitespace-nowrap transition-colors ${
              activeTab === tab.id
                ? "bg-accent-500/15 text-accent-700 shadow-xs dark:bg-accent-500/20 dark:text-accent-300"
                : "text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-surface-800 dark:hover:text-slate-200"
            }`}
          >
            <span>{tab.icon}</span>
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Active Tab View */}
      {activeTab === "dashboard" && <PersonalHealthDashboard />}
      {activeTab === "workout" && <PersonalHealthWorkoutTab />}
      {activeTab === "progress" && <PersonalHealthProgressTab />}
      {activeTab === "weekly-review" && <PersonalHealthWeeklyReviewTab />}
      {activeTab === "calendar" && <PersonalHealthCalendarTab />}
      {activeTab === "settings" && <PersonalHealthSettingsTab />}
    </div>
  );
}
