import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const markRead = vi.fn();
const markAllRead = vi.fn();

vi.mock("@/lib/hooks", () => ({
  useNotifications: () => ({
    data: [
      {
        id: "notif-1",
        type: "order.filled",
        severity: "success",
        title: "Order filled",
        body: "Your RELIANCE order filled at 2950.",
        payload: {},
        read: false,
        created_at: "2026-07-05T00:00:00Z",
      },
      {
        id: "notif-2",
        type: "risk.breach",
        severity: "critical",
        title: "Risk limit breached",
        body: "",
        payload: {},
        read: true,
        created_at: "2026-07-04T00:00:00Z",
      },
    ],
    isLoading: false,
  }),
  useMarkNotificationRead: () => ({ mutate: markRead, isPending: false }),
  useMarkAllNotificationsRead: () => ({ mutate: markAllRead, isPending: false }),
}));

import { NotificationsPage } from "@/pages/NotificationsPage";

describe("NotificationsPage", () => {
  it("renders notification history with unread and read entries", () => {
    render(<NotificationsPage />);

    expect(screen.getByText("Order filled")).toBeInTheDocument();
    expect(screen.getByText("Risk limit breached")).toBeInTheDocument();
    expect(screen.getByText("All (2)")).toBeInTheDocument();
    expect(screen.getByText("Unread (1)")).toBeInTheDocument();
  });
});
