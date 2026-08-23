import { useEffect, useMemo, useRef, useState } from "react";
import {
  type CalendarEvent,
  CATEGORY_COLORS,
  useCalendarStore,
} from "@/stores/calendarEvents";
import {
  getIndianMarketDaySchedule,
  type MarketSessionWindow,
} from "@/lib/marketSessions";

interface CalendarGridProps {
  days: Date[];
  onQuickCreate: (dateStr: string, timeStr: string) => void;
  onSelectEvent: (event: CalendarEvent) => void;
  onSelectMarketBlock: (session: MarketSessionWindow) => void;
}

const HOURS = Array.from({ length: 24 }, (_, i) => i); // 0..23
const HOUR_HEIGHT = 64; // px per hour (total grid height 1536px)

function timeToMinutes(time: string): number {
  const [h, m] = time.split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}

function minutesToTime(minutes: number): string {
  const clamped = Math.max(0, Math.min(1439, Math.round(minutes / 15) * 15));
  const h = Math.floor(clamped / 60);
  const m = clamped % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function formatDateKey(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** Get current civil date & minutes in Asia/Kolkata (IST) */
function getKolkataTime(): { currentMinutes: number; todayStr: string } {
  const now = new Date();
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(now);
  const lookup = Object.fromEntries(parts.map((p) => [p.type, p.value]));
  const rawHour = Number(lookup.hour === "24" ? 0 : lookup.hour);
  const h = Number.isNaN(rawHour) ? now.getHours() : rawHour;
  const m = Number(lookup.minute) || now.getMinutes();
  return {
    currentMinutes: h * 60 + m,
    todayStr: `${lookup.year}-${lookup.month}-${lookup.day}`,
  };
}

export function CalendarGrid({
  days,
  onQuickCreate,
  onSelectEvent,
  onSelectMarketBlock,
}: CalendarGridProps) {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const getEventsForDate = useCalendarStore((s) => s.getEventsForDate);
  const moveEvent = useCalendarStore((s) => s.moveEvent);
  const resizeEvent = useCalendarStore((s) => s.resizeEvent);

  // State for dragging/resizing user events
  const [activeDrag, setActiveDrag] = useState<{
    eventId: string;
    type: "move" | "resize";
    initialDayIndex: number;
    initialStartMinutes: number;
    initialEndMinutes: number;
    currentDayIndex: number;
    currentStartMinutes: number;
    currentEndMinutes: number;
    startY: number;
    startX: number;
  } | null>(null);

  // Current time in Asia/Kolkata
  const [{ currentMinutes, todayStr }, setKolkataNow] = useState(getKolkataTime);
  useEffect(() => {
    const timer = setInterval(() => setKolkataNow(getKolkataTime()), 30000);
    return () => clearInterval(timer);
  }, []);

  // Focus default visible range to 06:00 → 22:00 (initial scroll at 06:00)
  useEffect(() => {
    if (scrollContainerRef.current) {
      // 06:00 AM position (6 * 64px = 384px)
      scrollContainerRef.current.scrollTop = 6 * HOUR_HEIGHT;
    }
  }, []);

  // Global mouse move & up listeners for drag / resize
  useEffect(() => {
    if (!activeDrag) return;

    const handleMouseMove = (e: MouseEvent) => {
      const deltaY = e.clientY - activeDrag.startY;
      const deltaMinutes = (deltaY / HOUR_HEIGHT) * 60;
      const duration = activeDrag.initialEndMinutes - activeDrag.initialStartMinutes;

      if (activeDrag.type === "move") {
        let newStart = activeDrag.initialStartMinutes + deltaMinutes;
        newStart = Math.max(0, Math.min(1440 - duration, newStart));
        const newEnd = newStart + duration;

        // Calculate day shift if columns are horizontal
        const deltaX = e.clientX - activeDrag.startX;
        const columnWidth = 140; // approximate
        const dayShift = Math.round(deltaX / columnWidth);
        const newDayIndex = Math.max(0, Math.min(days.length - 1, activeDrag.initialDayIndex + dayShift));

        setActiveDrag((prev) =>
          prev
            ? {
                ...prev,
                currentStartMinutes: newStart,
                currentEndMinutes: newEnd,
                currentDayIndex: newDayIndex,
              }
            : null
        );
      } else if (activeDrag.type === "resize") {
        let newEnd = activeDrag.initialEndMinutes + deltaMinutes;
        newEnd = Math.max(activeDrag.initialStartMinutes + 15, Math.min(1440, newEnd));

        setActiveDrag((prev) =>
          prev
            ? {
                ...prev,
                currentEndMinutes: newEnd,
              }
            : null
        );
      }
    };

    const handleMouseUp = () => {
      if (activeDrag) {
        const targetDate = formatDateKey(days[activeDrag.currentDayIndex] || days[0]);
        const newStart = minutesToTime(activeDrag.currentStartMinutes);
        const newEnd = minutesToTime(activeDrag.currentEndMinutes);

        if (activeDrag.type === "move") {
          moveEvent(activeDrag.eventId, targetDate, newStart, newEnd);
        } else if (activeDrag.type === "resize") {
          resizeEvent(activeDrag.eventId, newEnd);
        }
      }
      setActiveDrag(null);
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [activeDrag, days, moveEvent, resizeEvent]);

  // Pre-calculate market status and events for all visible days
  const dayData = useMemo(() => {
    return days.map((day) => {
      const dateStr = formatDateKey(day);
      const isToday = dateStr === todayStr;
      const marketSchedule = getIndianMarketDaySchedule(day);
      const userEvents = getEventsForDate(dateStr);
      return {
        day,
        dateStr,
        isToday,
        marketSchedule,
        userEvents,
      };
    });
  }, [days, getEventsForDate, todayStr]);

  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-surface-800 dark:bg-surface-900">
      {/* Sticky Day Column Headers */}
      <div className="flex border-b border-slate-200 bg-slate-50/80 backdrop-blur dark:border-surface-800 dark:bg-surface-850">
        {/* Time Axis Header Placeholder */}
        <div className="w-16 shrink-0 border-r border-slate-200 p-3 text-center text-xs font-semibold text-slate-400 dark:border-surface-800">
          IST
        </div>

        {/* Days Header Row */}
        <div className="grid flex-1 grid-cols-7 divide-x divide-slate-200 dark:divide-surface-800">
          {dayData.map(({ day, dateStr, isToday, marketSchedule }) => {
            const weekdayName = new Intl.DateTimeFormat("en-US", { weekday: "short" }).format(day);
            const dayNumber = day.getDate();

            return (
              <div
                key={dateStr}
                className={`p-2.5 text-center transition-colors ${
                  isToday
                    ? "bg-accent-500/10 font-bold text-accent-700 dark:bg-accent-500/15 dark:text-accent-300"
                    : "text-slate-700 dark:text-slate-300"
                }`}
              >
                <div className="text-[11px] font-semibold tracking-wider text-slate-400 uppercase">
                  {weekdayName}
                </div>
                <div
                  className={`mx-auto mt-0.5 flex size-7 items-center justify-center rounded-full text-sm font-semibold ${
                    isToday
                      ? "bg-accent-600 text-white shadow-sm"
                      : "text-slate-800 dark:text-slate-100"
                  }`}
                >
                  {dayNumber}
                </div>

                {/* Day status badge */}
                <div className="mt-1">
                  {marketSchedule.type === "open" ? (
                    <span className="inline-block rounded px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 bg-emerald-500/10 dark:text-emerald-300">
                      Open (3 Sessions)
                    </span>
                  ) : marketSchedule.type === "holiday" ? (
                    <span
                      title={marketSchedule.reason}
                      className="inline-block truncate max-w-full rounded px-1.5 py-0.5 text-[10px] font-medium text-rose-700 bg-rose-500/10 dark:text-rose-300"
                    >
                      {marketSchedule.holidayName}
                    </span>
                  ) : (
                    <span className="inline-block rounded px-1.5 py-0.5 text-[10px] font-medium text-slate-500 bg-slate-200/50 dark:bg-surface-800 dark:text-slate-400">
                      Market Closed
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Scrollable Time Grid */}
      <div
        ref={scrollContainerRef}
        className="relative flex flex-1 overflow-y-auto"
        style={{ height: "680px" }}
      >
        {/* Time Axis Column */}
        <div
          className="relative w-16 shrink-0 select-none border-r border-slate-200 bg-slate-50/40 dark:border-surface-800 dark:bg-surface-900"
          style={{ height: `${24 * HOUR_HEIGHT}px` }}
        >
          {HOURS.map((hour) => {
            const displayHour = hour === 0 ? "12 AM" : hour < 12 ? `${hour} AM` : hour === 12 ? "12 PM" : `${hour - 12} PM`;
            return (
              <div
                key={hour}
                className="absolute right-2 text-[11px] font-medium text-slate-400 dark:text-slate-500"
                style={{ top: `${hour * HOUR_HEIGHT - 8}px` }}
              >
                {displayHour}
              </div>
            );
          })}
        </div>

        {/* 7 Days Columns */}
        <div
          className="relative grid flex-1 grid-cols-7 divide-x divide-slate-100 dark:divide-surface-800/80"
          style={{ height: `${24 * HOUR_HEIGHT}px` }}
        >
          {/* Horizontal Hour Lines */}
          <div className="pointer-events-none absolute inset-0">
            {HOURS.map((hour) => (
              <div
                key={hour}
                className="absolute w-full border-t border-slate-100 dark:border-surface-800/60"
                style={{ top: `${hour * HOUR_HEIGHT}px` }}
              />
            ))}
          </div>

          {/* Day Columns */}
          {dayData.map(({ dateStr, isToday, marketSchedule, userEvents }, dayIndex) => {
            return (
              <div
                key={dateStr}
                className={`group relative h-full transition-colors ${
                  isToday ? "bg-accent-500/[0.02]" : ""
                }`}
                onClick={(e) => {
                  // Only fire if clicking on empty column background
                  if (e.target === e.currentTarget) {
                    const rect = e.currentTarget.getBoundingClientRect();
                    const clickY = e.clientY - rect.top;
                    const clickHour = Math.floor(clickY / HOUR_HEIGHT);
                    const timeStr = `${String(clickHour).padStart(2, "0")}:00`;
                    onQuickCreate(dateStr, timeStr);
                  }
                }}
              >
                {/* Current Time Indicator Line (Asia/Kolkata IST) */}
                {isToday && (
                  <div
                    className="pointer-events-none absolute left-0 right-0 z-30 flex items-center"
                    style={{ top: `${(currentMinutes / 60) * HOUR_HEIGHT}px` }}
                  >
                    <div className="size-2 -ml-1 rounded-full bg-loss-500 shadow-sm" />
                    <div className="h-[2px] w-full bg-loss-500/90 shadow-sm" />
                  </div>
                )}

                {/* 1. SYSTEM MARKET BLOCKS (Pre-Market, Market Hours, Cash Market) */}
                {marketSchedule.type === "open" &&
                  marketSchedule.windows.map((session) => {
                    const startMin = session.startHour * 60 + session.startMinute;
                    const endMin = session.endHour * 60 + session.endMinute;
                    const durationMin = endMin - startMin;

                    const topPx = (startMin / 60) * HOUR_HEIGHT;
                    const heightPx = Math.max(26, (durationMin / 60) * HOUR_HEIGHT);

                    const phaseStyles =
                      session.phase === "pre"
                        ? "border-l-4 border-sky-400 bg-sky-500/10 text-sky-950 dark:bg-sky-500/20 dark:text-sky-100 hover:bg-sky-500/20"
                        : session.phase === "main"
                        ? "border-l-4 border-blue-600 bg-blue-500/15 text-blue-950 dark:bg-blue-500/25 dark:text-blue-100 hover:bg-blue-500/25 shadow-sm"
                        : "border-l-4 border-indigo-500 bg-indigo-500/10 text-indigo-950 dark:bg-indigo-500/20 dark:text-indigo-100 hover:bg-indigo-500/20";

                    return (
                      <div
                        key={session.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectMarketBlock(session);
                        }}
                        className={`absolute left-1 right-1 z-10 cursor-pointer overflow-hidden rounded-md p-1.5 transition-all select-none ${phaseStyles}`}
                        style={{
                          top: `${topPx}px`,
                          height: `${heightPx}px`,
                        }}
                        title={`${session.name} (${session.startTime}–${session.endTime} IST)`}
                      >
                        <div className="flex items-center justify-between gap-1">
                          <div className="flex items-center gap-1 overflow-hidden">
                            <svg
                              className="size-3 shrink-0 opacity-70"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth="2"
                                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                              />
                            </svg>
                            <span className="truncate text-[11px] font-bold tracking-tight">
                              {session.name}
                            </span>
                          </div>
                          <span className="shrink-0 text-[10px] font-semibold opacity-75">
                            {session.startTime}–{session.endTime}
                          </span>
                        </div>

                        {heightPx > 40 && (
                          <p className="mt-0.5 truncate text-[10px] opacity-75">
                            {session.description}
                          </p>
                        )}
                      </div>
                    );
                  })}

                {/* 2. USER CALENDAR EVENTS (Draggable / Resizable) */}
                {userEvents.map((evt) => {
                  const isBeingDragged = activeDrag?.eventId === evt.id;
                  const startMin = isBeingDragged
                    ? activeDrag.currentStartMinutes
                    : timeToMinutes(evt.startTime);
                  const endMin = isBeingDragged
                    ? activeDrag.currentEndMinutes
                    : timeToMinutes(evt.endTime);

                  const durationMin = Math.max(15, endMin - startMin);
                  const topPx = (startMin / 60) * HOUR_HEIGHT;
                  const heightPx = Math.max(26, (durationMin / 60) * HOUR_HEIGHT);

                  const categoryConfig = CATEGORY_COLORS[evt.category] || CATEGORY_COLORS.other;

                  return (
                    <div
                      key={evt.id}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!isBeingDragged) onSelectEvent(evt);
                      }}
                      onMouseDown={(e) => {
                        // Start move drag (unless clicking resize handle)
                        if ((e.target as HTMLElement).dataset.resize) return;
                        e.stopPropagation();
                        setActiveDrag({
                          eventId: evt.id,
                          type: "move",
                          initialDayIndex: dayIndex,
                          initialStartMinutes: timeToMinutes(evt.startTime),
                          initialEndMinutes: timeToMinutes(evt.endTime),
                          currentDayIndex: dayIndex,
                          currentStartMinutes: timeToMinutes(evt.startTime),
                          currentEndMinutes: timeToMinutes(evt.endTime),
                          startY: e.clientY,
                          startX: e.clientX,
                        });
                      }}
                      className={`group/card absolute left-2 right-2 z-20 cursor-grab rounded-lg border p-1.5 shadow-sm transition-all select-none active:cursor-grabbing ${
                        categoryConfig.bg
                      } ${categoryConfig.border} ${categoryConfig.text} ${
                        isBeingDragged ? "opacity-75 shadow-lg ring-2 ring-accent-500" : ""
                      }`}
                      style={{
                        top: `${topPx}px`,
                        height: `${heightPx}px`,
                      }}
                    >
                      <div className="flex items-center justify-between gap-1">
                        <span className="truncate text-xs font-semibold">
                          {evt.title}
                        </span>
                        <span className="shrink-0 text-[10px] font-medium opacity-80">
                          {evt.startTime}–{evt.endTime}
                        </span>
                      </div>

                      {heightPx > 42 && evt.location && (
                        <p className="mt-0.5 truncate text-[10px] opacity-75">
                          📍 {evt.location}
                        </p>
                      )}

                      {/* Resize Handle at Bottom Edge */}
                      <div
                        data-resize="true"
                        onMouseDown={(e) => {
                          e.stopPropagation();
                          setActiveDrag({
                            eventId: evt.id,
                            type: "resize",
                            initialDayIndex: dayIndex,
                            initialStartMinutes: timeToMinutes(evt.startTime),
                            initialEndMinutes: timeToMinutes(evt.endTime),
                            currentDayIndex: dayIndex,
                            currentStartMinutes: timeToMinutes(evt.startTime),
                            currentEndMinutes: timeToMinutes(evt.endTime),
                            startY: e.clientY,
                            startX: e.clientX,
                          });
                        }}
                        className="absolute bottom-0 left-0 right-0 h-2 cursor-s-resize transition-colors hover:bg-black/10 dark:hover:bg-white/10"
                        title="Drag to adjust duration"
                      />
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
