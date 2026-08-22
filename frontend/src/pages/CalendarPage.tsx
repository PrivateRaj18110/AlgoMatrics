import { useMemo, useState } from "react";

import { Button, Card, PageHeader } from "@/components/ui";
import { formatInZone } from "@/lib/time";
import { addDays, formatSessionWindow, sessionsForDay, startOfWeek } from "@/lib/marketSessions";

type View = "weekly" | "monthly";

export function CalendarPage() {
  const [view, setView] = useState<View>("weekly");
  const [cursor, setCursor] = useState(() => new Date());

  const weekStart = startOfWeek(cursor);
  const days = useMemo(
    () => (view === "weekly" ? Array.from({ length: 7 }, (_, index) => addDays(weekStart, index)) : monthDays(cursor)),
    [cursor, view, weekStart],
  );

  return (
    <div>
      <PageHeader
        title="Calendar"
        description="Market sessions use IANA timezones. API timestamps stay UTC."
        actions={
          <div className="flex gap-2">
            <Button variant={view === "weekly" ? "primary" : "secondary"} size="sm" onClick={() => setView("weekly")}>
              Weekly
            </Button>
            <Button variant={view === "monthly" ? "primary" : "secondary"} size="sm" onClick={() => setView("monthly")}>
              Monthly
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setCursor(addDays(cursor, view === "weekly" ? -7 : -30))}>
              Previous
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setCursor(new Date())}>
              Today
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setCursor(addDays(cursor, view === "weekly" ? 7 : 30))}>
              Next
            </Button>
          </div>
        }
      />
      <div className={`grid gap-3 ${view === "weekly" ? "md:grid-cols-7" : "md:grid-cols-7"}`}>
        {days.map((day) => {
          const india = sessionsForDay(day, "india");
          const intl = sessionsForDay(day, "international");
          return (
            <Card key={day.toISOString()}>
              <p className="text-xs text-slate-500">
                {formatInZone(day, "Asia/Kolkata", { weekday: "short", day: "numeric", month: "short", year: "numeric" })}
              </p>
              <div className="mt-2 space-y-2 text-xs">
                {india.length ? (
                  india.map((session) => (
                    <p key={session.id}>
                      India · {session.venue}
                      <br />
                      {formatSessionWindow(session)}
                    </p>
                  ))
                ) : (
                  <p className="text-slate-400">India closed</p>
                )}
                {intl.length ? (
                  intl.map((session) => (
                    <p key={session.id}>
                      International · {session.venue}
                      <br />
                      {formatSessionWindow(session)}
                    </p>
                  ))
                ) : (
                  <p className="text-slate-400">International cash session closed</p>
                )}
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function monthDays(date: Date): Date[] {
  const first = new Date(date.getFullYear(), date.getMonth(), 1);
  const start = startOfWeek(first);
  return Array.from({ length: 42 }, (_, index) => addDays(start, index));
}
