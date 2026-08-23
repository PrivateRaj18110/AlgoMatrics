import { create } from "zustand";
import { persist } from "zustand/middleware";

export type EventCategory =
  | "personal"
  | "fitness"
  | "gym"
  | "meeting"
  | "work"
  | "trading"
  | "research"
  | "appointment"
  | "other";

export type RepeatOption = "none" | "daily" | "weekdays" | "weekly" | "monthly";

export interface CalendarEvent {
  id: string;
  title: string;
  date: string; // YYYY-MM-DD
  startTime: string; // HH:MM (24-hour)
  endTime: string; // HH:MM (24-hour)
  category: EventCategory;
  description?: string;
  location?: string;
  reminder?: string;
  repeat?: RepeatOption;
  createdAt: string;
  updatedAt: string;
}

export interface NewCalendarEventInput {
  title: string;
  date: string;
  startTime: string;
  endTime: string;
  category: EventCategory;
  description?: string;
  location?: string;
  reminder?: string;
  repeat?: RepeatOption;
}

interface CalendarState {
  events: CalendarEvent[];
  addEvent: (input: NewCalendarEventInput) => CalendarEvent;
  updateEvent: (id: string, updates: Partial<NewCalendarEventInput>) => void;
  deleteEvent: (id: string) => void;
  moveEvent: (id: string, newDate: string, newStartTime: string, newEndTime: string) => void;
  resizeEvent: (id: string, newEndTime: string) => void;
  getEventsForDate: (dateStr: string) => CalendarEvent[];
}

/** Category color mappings */
export const CATEGORY_COLORS: Record<
  EventCategory,
  {
    bg: string;
    border: string;
    text: string;
    badge: string;
    dot: string;
    label: string;
  }
> = {
  gym: {
    bg: "bg-emerald-500/15 dark:bg-emerald-500/20 hover:bg-emerald-500/25",
    border: "border-emerald-500/40 dark:border-emerald-400/50",
    text: "text-emerald-900 dark:text-emerald-200",
    badge: "bg-emerald-500/20 text-emerald-700 dark:text-emerald-300",
    dot: "bg-emerald-500",
    label: "Gym",
  },
  fitness: {
    bg: "bg-teal-500/15 dark:bg-teal-500/20 hover:bg-teal-500/25",
    border: "border-teal-500/40 dark:border-teal-400/50",
    text: "text-teal-900 dark:text-teal-200",
    badge: "bg-teal-500/20 text-teal-700 dark:text-teal-300",
    dot: "bg-teal-500",
    label: "Fitness",
  },
  meeting: {
    bg: "bg-purple-500/15 dark:bg-purple-500/20 hover:bg-purple-500/25",
    border: "border-purple-500/40 dark:border-purple-400/50",
    text: "text-purple-900 dark:text-purple-200",
    badge: "bg-purple-500/20 text-purple-700 dark:text-purple-300",
    dot: "bg-purple-500",
    label: "Meeting",
  },
  work: {
    bg: "bg-indigo-500/15 dark:bg-indigo-500/20 hover:bg-indigo-500/25",
    border: "border-indigo-500/40 dark:border-indigo-400/50",
    text: "text-indigo-900 dark:text-indigo-200",
    badge: "bg-indigo-500/20 text-indigo-700 dark:text-indigo-300",
    dot: "bg-indigo-500",
    label: "Work",
  },
  trading: {
    bg: "bg-amber-500/15 dark:bg-amber-500/20 hover:bg-amber-500/25",
    border: "border-amber-500/40 dark:border-amber-400/50",
    text: "text-amber-900 dark:text-amber-200",
    badge: "bg-amber-500/20 text-amber-700 dark:text-amber-300",
    dot: "bg-amber-500",
    label: "Trading",
  },
  research: {
    bg: "bg-cyan-500/15 dark:bg-cyan-500/20 hover:bg-cyan-500/25",
    border: "border-cyan-500/40 dark:border-cyan-400/50",
    text: "text-cyan-900 dark:text-cyan-200",
    badge: "bg-cyan-500/20 text-cyan-700 dark:text-cyan-300",
    dot: "bg-cyan-500",
    label: "Research",
  },
  appointment: {
    bg: "bg-blue-500/15 dark:bg-blue-500/20 hover:bg-blue-500/25",
    border: "border-blue-500/40 dark:border-blue-400/50",
    text: "text-blue-900 dark:text-blue-200",
    badge: "bg-blue-500/20 text-blue-700 dark:text-blue-300",
    dot: "bg-blue-500",
    label: "Appointment",
  },
  personal: {
    bg: "bg-rose-500/15 dark:bg-rose-500/20 hover:bg-rose-500/25",
    border: "border-rose-500/40 dark:border-rose-400/50",
    text: "text-rose-900 dark:text-rose-200",
    badge: "bg-rose-500/20 text-rose-700 dark:text-rose-300",
    dot: "bg-rose-500",
    label: "Personal",
  },
  other: {
    bg: "bg-slate-500/15 dark:bg-slate-500/20 hover:bg-slate-500/25",
    border: "border-slate-500/40 dark:border-slate-400/50",
    text: "text-slate-900 dark:text-slate-200",
    badge: "bg-slate-500/20 text-slate-700 dark:text-slate-300",
    dot: "bg-slate-500",
    label: "Other",
  },
};

function generateId(): string {
  return "evt-" + Math.random().toString(36).substring(2, 9) + Date.now().toString(36);
}

/** Parse YYYY-MM-DD safely into local calendar day components without timezone skew */
function parseDateParts(dateStr: string): { year: number; month: number; day: number; dayOfWeek: number } {
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(y, (m || 1) - 1, d || 1);
  return { year: y, month: m, day: d, dayOfWeek: dt.getDay() };
}

/** Initial curated seed events for the current week to provide immediate rich demo state */
function getInitialSeedEvents(): CalendarEvent[] {
  const today = new Date();
  const y = today.getFullYear();
  const m = String(today.getMonth() + 1).padStart(2, "0");
  const d = String(today.getDate()).padStart(2, "0");
  const todayStr = `${y}-${m}-${d}`;

  return [
    {
      id: "seed-gym-1",
      title: "Gym Workout",
      date: todayStr,
      startTime: "07:00",
      endTime: "08:00",
      category: "gym",
      description: "Morning cardio and upper body strength routine",
      location: "Gold's Gym",
      repeat: "weekdays",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    },
    {
      id: "seed-quant-sync",
      title: "Quant Strategy Review",
      date: todayStr,
      startTime: "16:00",
      endTime: "17:30",
      category: "research",
      description: "Review mean reversion backtests & volatility regime models",
      location: "Algo Matrics Desk",
      repeat: "weekly",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    },
  ];
}

export const useCalendarStore = create<CalendarState>()(
  persist(
    (set, get) => ({
      events: getInitialSeedEvents(),

      addEvent: (input: NewCalendarEventInput) => {
        const newEvent: CalendarEvent = {
          ...input,
          id: generateId(),
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };
        set((state) => ({
          events: [...state.events, newEvent],
        }));
        return newEvent;
      },

      updateEvent: (id: string, updates: Partial<NewCalendarEventInput>) => {
        set((state) => ({
          events: state.events.map((e) =>
            e.id === id ? { ...e, ...updates, updatedAt: new Date().toISOString() } : e
          ),
        }));
      },

      deleteEvent: (id: string) => {
        set((state) => ({
          events: state.events.filter((e) => e.id !== id),
        }));
      },

      moveEvent: (id: string, newDate: string, newStartTime: string, newEndTime: string) => {
        set((state) => ({
          events: state.events.map((e) =>
            e.id === id
              ? {
                  ...e,
                  date: newDate,
                  startTime: newStartTime,
                  endTime: newEndTime,
                  updatedAt: new Date().toISOString(),
                }
              : e
          ),
        }));
      },

      resizeEvent: (id: string, newEndTime: string) => {
        set((state) => ({
          events: state.events.map((e) =>
            e.id === id
              ? {
                  ...e,
                  endTime: newEndTime,
                  updatedAt: new Date().toISOString(),
                }
              : e
          ),
        }));
      },

      getEventsForDate: (dateStr: string) => {
        const allEvents = get().events;
        const target = parseDateParts(dateStr);

        return allEvents.filter((e) => {
          if (e.date === dateStr) return true;
          // Recurrence rule only applies on or after the original start date
          if (dateStr < e.date) return false;

          const origin = parseDateParts(e.date);

          if (e.repeat === "daily") {
            return true;
          }
          if (e.repeat === "weekdays") {
            return target.dayOfWeek >= 1 && target.dayOfWeek <= 5;
          }
          if (e.repeat === "weekly") {
            return target.dayOfWeek === origin.dayOfWeek;
          }
          if (e.repeat === "monthly") {
            return target.day === origin.day;
          }
          return false;
        });
      },
    }),
    {
      name: "algo-matrics-calendar-events-v1",
    }
  )
);
