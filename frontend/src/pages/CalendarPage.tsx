import { useMemo, useState } from "react";

import { Badge, Button, Card, PageHeader } from "@/components/ui";
import { formatInZone } from "@/lib/time";
import {
  addDays,
  getIndianMarketDaySchedule,
  type MarketSessionWindow,
  startOfWeek,
} from "@/lib/marketSessions";
import {
  type CalendarEvent,
  CATEGORY_COLORS,
  useCalendarStore,
} from "@/stores/calendarEvents";
import { CalendarGrid } from "@/components/calendar/CalendarGrid";
import { EventModal } from "@/components/calendar/EventModal";
import { EventDetailModal } from "@/components/calendar/EventDetailModal";
import { MarketBlockDetailModal } from "@/components/calendar/MarketBlockDetailModal";

type CalendarViewMode = "day" | "week" | "month";

export function CalendarPage() {
  const [view, setView] = useState<CalendarViewMode>("week");
  const [cursor, setCursor] = useState(() => new Date());

  // Modals state
  const [eventModalOpen, setEventModalOpen] = useState(false);
  const [quickCreateDate, setQuickCreateDate] = useState<string | undefined>();
  const [quickCreateTime, setQuickCreateTime] = useState<string | undefined>();
  const [editingEvent, setEditingEvent] = useState<CalendarEvent | null>(null);

  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null);
  const [selectedMarketBlock, setSelectedMarketBlock] = useState<MarketSessionWindow | null>(null);

  const getEventsForDate = useCalendarStore((s) => s.getEventsForDate);

  // Week days starting Sunday (0) or Monday (1)
  const weekStart = useMemo(() => startOfWeek(cursor, 0), [cursor]);
  const weekDays = useMemo(
    () => Array.from({ length: 7 }, (_, index) => addDays(weekStart, index)),
    [weekStart]
  );

  // Month days
  const monthGridDays = useMemo(() => {
    const firstDay = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const start = startOfWeek(firstDay, 0);
    return Array.from({ length: 35 }, (_, index) => addDays(start, index));
  }, [cursor]);

  // Date range title
  const dateRangeTitle = useMemo(() => {
    if (view === "day") {
      return formatInZone(cursor, "Asia/Kolkata", {
        weekday: "long",
        month: "long",
        day: "numeric",
        year: "numeric",
      });
    }
    if (view === "week") {
      const first = weekDays[0];
      const last = weekDays[6];
      const startMonth = formatInZone(first, "Asia/Kolkata", { month: "short" });
      const endMonth = formatInZone(last, "Asia/Kolkata", { month: "short" });
      const year = formatInZone(last, "Asia/Kolkata", { year: "numeric" });
      return `${startMonth} ${first.getDate()} – ${endMonth} ${last.getDate()}, ${year}`;
    }
    return formatInZone(cursor, "Asia/Kolkata", { month: "long", year: "numeric" });
  }, [cursor, view, weekDays]);

  const handleNavigate = (delta: number) => {
    if (view === "day") {
      setCursor(addDays(cursor, delta));
    } else if (view === "week") {
      setCursor(addDays(cursor, delta * 7));
    } else {
      const nextMonth = new Date(cursor);
      nextMonth.setMonth(cursor.getMonth() + delta);
      setCursor(nextMonth);
    }
  };

  const handleQuickCreate = (dateStr: string, timeStr: string) => {
    setEditingEvent(null);
    setQuickCreateDate(dateStr);
    setQuickCreateTime(timeStr);
    setEventModalOpen(true);
  };

  const handleOpenAddEvent = () => {
    setEditingEvent(null);
    setQuickCreateDate(undefined);
    setQuickCreateTime(undefined);
    setEventModalOpen(true);
  };

  const handleEditEvent = (evt: CalendarEvent) => {
    setSelectedEvent(null);
    setEditingEvent(evt);
    setEventModalOpen(true);
  };

  return (
    <div className="space-y-4">
      {/* Page Header */}
      <PageHeader
        title="Weekly Calendar"
        description="Unified market session blocks & personal productivity calendar in Asia/Kolkata (IST)."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {/* View Switchers */}
            <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-0.5 dark:border-surface-800 dark:bg-surface-850">
              <button
                type="button"
                onClick={() => setView("day")}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  view === "day"
                    ? "bg-white text-slate-900 shadow-xs dark:bg-surface-800 dark:text-white"
                    : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
                }`}
              >
                Day
              </button>
              <button
                type="button"
                onClick={() => setView("week")}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  view === "week"
                    ? "bg-white text-slate-900 shadow-xs dark:bg-surface-800 dark:text-white"
                    : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
                }`}
              >
                Week
              </button>
              <button
                type="button"
                onClick={() => setView("month")}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  view === "month"
                    ? "bg-white text-slate-900 shadow-xs dark:bg-surface-800 dark:text-white"
                    : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
                }`}
              >
                Month
              </button>
            </div>

            {/* Navigation buttons */}
            <div className="flex items-center gap-1">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => handleNavigate(-1)}
                aria-label="Previous period"
              >
                ‹ Prev
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setCursor(new Date())}>
                Today
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => handleNavigate(1)}
                aria-label="Next period"
              >
                Next ›
              </Button>
            </div>

            {/* Add Event Button */}
            <Button variant="primary" size="sm" onClick={handleOpenAddEvent}>
              + Add Event
            </Button>
          </div>
        }
      />

      {/* Date Title & Market Strip */}
      <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-xs dark:border-surface-800 dark:bg-surface-900 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">
            {dateRangeTitle}
          </h2>
          <Badge color="blue">Asia/Kolkata (IST)</Badge>
        </div>

        {/* Compact Market Schedule Summary */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-semibold text-slate-500 dark:text-slate-400">
            India Market:
          </span>
          <div className="flex items-center gap-1.5 rounded-md border border-sky-200 bg-sky-50 px-2 py-1 font-medium text-sky-900 dark:border-sky-900/50 dark:bg-sky-950/40 dark:text-sky-200">
            <span className="size-2 rounded-full bg-sky-500" />
            <span>Pre-Market 09:00–09:15</span>
          </div>
          <div className="flex items-center gap-1.5 rounded-md border border-blue-200 bg-blue-50 px-2 py-1 font-medium text-blue-900 dark:border-blue-900/50 dark:bg-blue-950/40 dark:text-blue-200">
            <span className="size-2 rounded-full bg-blue-600" />
            <span>Market Hours 09:15–15:15</span>
          </div>
          <div className="flex items-center gap-1.5 rounded-md border border-indigo-200 bg-indigo-50 px-2 py-1 font-medium text-indigo-900 dark:border-indigo-900/50 dark:bg-indigo-950/40 dark:text-indigo-200">
            <span className="size-2 rounded-full bg-indigo-500" />
            <span>Cash Market 15:15–15:45</span>
          </div>
        </div>
      </div>

      {/* Main Calendar View Area */}
      {view === "week" && (
        <CalendarGrid
          days={weekDays}
          onQuickCreate={handleQuickCreate}
          onSelectEvent={setSelectedEvent}
          onSelectMarketBlock={setSelectedMarketBlock}
        />
      )}

      {view === "day" && (
        <CalendarGrid
          days={[cursor]}
          onQuickCreate={handleQuickCreate}
          onSelectEvent={setSelectedEvent}
          onSelectMarketBlock={setSelectedMarketBlock}
        />
      )}

      {view === "month" && (
        <div className="grid grid-cols-7 gap-2">
          {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((dayName) => (
            <div
              key={dayName}
              className="p-2 text-center text-xs font-semibold text-slate-500 uppercase dark:text-slate-400"
            >
              {dayName}
            </div>
          ))}

          {monthGridDays.map((day) => {
            const dateStr = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
            const isToday =
              dateStr ===
              `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, "0")}-${String(new Date().getDate()).padStart(2, "0")}`;
            const isCurrentMonth = day.getMonth() === cursor.getMonth();
            const marketSchedule = getIndianMarketDaySchedule(day);
            const userEvents = getEventsForDate(dateStr);

            return (
              <Card
                key={dateStr}
                className={`min-h-28 transition-colors ${
                  isToday
                    ? "ring-2 ring-accent-500"
                    : !isCurrentMonth
                    ? "opacity-40"
                    : ""
                }`}
              >
                <div className="flex items-center justify-between">
                  <span
                    className={`text-xs font-bold ${
                      isToday
                        ? "flex size-5 items-center justify-center rounded-full bg-accent-600 text-white"
                        : "text-slate-700 dark:text-slate-300"
                    }`}
                  >
                    {day.getDate()}
                  </span>
                  {marketSchedule.type === "open" ? (
                    <span className="text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                      Open
                    </span>
                  ) : marketSchedule.type === "holiday" ? (
                    <span className="text-[10px] font-medium text-rose-500">
                      {marketSchedule.holidayName}
                    </span>
                  ) : (
                    <span className="text-[10px] text-slate-400">Closed</span>
                  )}
                </div>

                <div className="mt-2 space-y-1">
                  {userEvents.slice(0, 3).map((evt) => {
                    const catConfig =
                      CATEGORY_COLORS[evt.category] || CATEGORY_COLORS.other;
                    return (
                      <div
                        key={evt.id}
                        onClick={() => setSelectedEvent(evt)}
                        className={`truncate rounded px-1 py-0.5 text-[10px] font-medium cursor-pointer ${catConfig.badge}`}
                      >
                        {evt.startTime} {evt.title}
                      </div>
                    );
                  })}
                  {userEvents.length > 3 && (
                    <p className="text-[9px] text-slate-400">
                      +{userEvents.length - 3} more
                    </p>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Modals */}
      <EventModal
        open={eventModalOpen}
        onClose={() => setEventModalOpen(false)}
        initialDate={quickCreateDate}
        initialStartTime={quickCreateTime}
        editingEvent={editingEvent}
      />

      <EventDetailModal
        event={selectedEvent}
        open={selectedEvent !== null}
        onClose={() => setSelectedEvent(null)}
        onEdit={handleEditEvent}
      />

      <MarketBlockDetailModal
        session={selectedMarketBlock}
        open={selectedMarketBlock !== null}
        onClose={() => setSelectedMarketBlock(null)}
      />
    </div>
  );
}
