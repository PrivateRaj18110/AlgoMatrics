import { useMemo, useState } from "react";

import {
  Badge,
  Button,
  Card,
  EmptyState,
  PageHeader,
  SkeletonRows,
  Tabs,
} from "@/components/ui";
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from "@/lib/hooks";
import { dateTime } from "@/lib/format";
import type { AppNotification } from "@/types/api";

function severityColor(severity: AppNotification["severity"]): "red" | "amber" | "green" | "blue" {
  if (severity === "critical") return "red";
  if (severity === "warning") return "amber";
  if (severity === "success") return "green";
  return "blue";
}

export function NotificationsPage() {
  const { data: notifications, isLoading } = useNotifications();
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();
  const [filter, setFilter] = useState<"all" | "unread">("all");

  const items = useMemo(() => notifications ?? [], [notifications]);
  const unreadCount = useMemo(() => items.filter((item) => !item.read).length, [items]);
  const visible = filter === "unread" ? items.filter((item) => !item.read) : items;

  return (
    <div>
      <PageHeader
        title="Notifications"
        description="Delivered alerts and system messages for this organization"
        actions={
          <Button
            variant="secondary"
            onClick={() => markAllRead.mutate()}
            loading={markAllRead.isPending}
            disabled={unreadCount === 0}
          >
            Mark all read
          </Button>
        }
      />

      <div className="mb-4">
        <Tabs
          active={filter}
          onChange={(key) => setFilter(key as "all" | "unread")}
          tabs={[
            { key: "all", label: `All (${items.length})` },
            { key: "unread", label: `Unread (${unreadCount})` },
          ]}
        />
      </div>

      <Card>
        {isLoading ? (
          <SkeletonRows rows={6} cols={3} />
        ) : visible.length === 0 ? (
          <EmptyState
            title={filter === "unread" ? "No unread notifications" : "No notifications yet"}
            body="Alerts about orders, strategies, risk, and billing appear here."
          />
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-surface-800/60">
            {visible.map((notification) => (
              <li
                key={notification.id}
                className={
                  notification.read
                    ? "flex items-start justify-between gap-4 py-3"
                    : "flex items-start justify-between gap-4 rounded-lg bg-accent-500/5 px-2 py-3"
                }
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Badge color={severityColor(notification.severity)}>
                      {notification.severity}
                    </Badge>
                    <p className="truncate text-sm font-medium">{notification.title}</p>
                    {!notification.read && (
                      <span className="size-2 shrink-0 rounded-full bg-accent-500" aria-label="unread" />
                    )}
                  </div>
                  {notification.body && (
                    <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                      {notification.body}
                    </p>
                  )}
                  <p className="mt-1 text-xs text-slate-400">{dateTime(notification.created_at)}</p>
                </div>
                {!notification.read && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => markRead.mutate(notification.id)}
                  >
                    Mark read
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
