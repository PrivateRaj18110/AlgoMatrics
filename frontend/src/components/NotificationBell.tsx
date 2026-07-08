import { useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import { Badge } from "@/components/ui";
import { api } from "@/lib/api";
import { useNotifications, useUnreadCount } from "@/lib/hooks";
import { timeAgo } from "@/lib/format";
import { liveChannel } from "@/lib/ws";
import { useAuth } from "@/stores/auth";

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { data: notifications } = useNotifications();
  const { data: unread } = useUnreadCount();
  const client = useQueryClient();
  const activeOrgId = useAuth((state) => state.activeOrgId);

  useEffect(() => {
    if (!activeOrgId) return;
    const unsubscribe = liveChannel.subscribe("notifications", () => {
      client.invalidateQueries({ queryKey: ["notifications"] });
      client.invalidateQueries({ queryKey: ["notifications-unread"] });
    });
    return unsubscribe;
  }, [activeOrgId, client]);

  useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  async function markAllRead() {
    await api("/notifications/read-all", { method: "POST" });
    client.invalidateQueries({ queryKey: ["notifications"] });
    client.invalidateQueries({ queryKey: ["notifications-unread"] });
  }

  const count = unread?.count ?? 0;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((value) => !value)}
        className="relative rounded-md p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-surface-800"
        aria-label={`Notifications (${count} unread)`}
      >
        <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeWidth="1.6"
            d="M15 17h5l-1.4-1.4A2 2 0 0118 14.2V11a6 6 0 00-12 0v3.2a2 2 0 01-.6 1.4L4 17h5m6 0v1a3 3 0 01-6 0v-1"
          />
        </svg>
        {count > 0 && (
          <span className="absolute top-1 right-1 flex size-4 items-center justify-center rounded-full bg-loss-500 text-[10px] font-bold text-white">
            {count > 9 ? "9+" : count}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-80 rounded-xl border border-slate-200 bg-white shadow-xl dark:border-surface-700 dark:bg-surface-900">
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2.5 dark:border-surface-800">
            <span className="text-sm font-semibold">Notifications</span>
            {count > 0 && (
              <button onClick={markAllRead} className="text-xs text-accent-500 hover:underline">
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-96 overflow-y-auto">
            {!notifications || notifications.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-slate-400">No notifications yet</p>
            ) : (
              notifications.map((notification) => (
                <div
                  key={notification.id}
                  className={clsx(
                    "border-b border-slate-100 px-4 py-2.5 dark:border-surface-800/60",
                    !notification.read && "bg-accent-500/5",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium">{notification.title}</p>
                    <Badge
                      color={
                        notification.severity === "critical" || notification.severity === "warning"
                          ? notification.severity === "critical"
                            ? "red"
                            : "amber"
                          : notification.severity === "success"
                            ? "green"
                            : "blue"
                      }
                    >
                      {notification.severity}
                    </Badge>
                  </div>
                  {notification.body && (
                    <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                      {notification.body}
                    </p>
                  )}
                  <p className="mt-1 text-[11px] text-slate-400">{timeAgo(notification.created_at)}</p>
                </div>
              ))
            )}
          </div>
          <div className="border-t border-slate-200 px-4 py-2 text-center dark:border-surface-800">
            <Link
              to="/app/notifications"
              onClick={() => setOpen(false)}
              className="text-xs font-medium text-accent-500 hover:underline"
            >
              View all notifications
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
