import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/hooks", () => ({
  useAuditEvents: () => ({
    data: {
      total: 1,
      items: [
        {
          id: "audit-1",
          actor_user_id: "user-1",
          actor_type: "user",
          action: "orders.submitted",
          resource_type: "order",
          resource_id: "order-1",
          request_id: "request-1",
          correlation_id: "corr-1",
          session_id: "sess-1",
          before_state: null,
          after_state: { status: "submitted" },
          sequence: 42,
          entry_hash: "abc123",
          occurred_at: "2026-07-05T00:00:00Z",
        },
      ],
    },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
}));

import { AuditLogPage } from "@/pages/AuditLogPage";

describe("AuditLogPage", () => {
  it("renders organization audit events from the API hook", () => {
    render(<AuditLogPage />);

    expect(screen.getByText("orders.submitted")).toBeInTheDocument();
    expect(screen.getByText("order-1")).toBeInTheDocument();
    // The redesigned row surfaces the hash-chain sequence and correlation id.
    expect(screen.getByText("#42")).toBeInTheDocument();
    expect(screen.getByText("corr-1")).toBeInTheDocument();
  });
});
