import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { AppLayout } from "@/app/AppLayout";
import { useAuth } from "@/stores/auth";

describe("AppLayout navigation", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    useAuth.setState({
      user: {
        id: "u-1",
        email: "test@example.com",
        full_name: "Test User",
        status: "active",
        email_verified: true,
        mfa_enabled: false,
        avatar_url: null,
        timezone: "Asia/Kolkata",
        theme: "dark",
        preferences: {},
        notification_settings: {},
        is_platform_admin: true,
        created_at: "2026-01-01T00:00:00Z",
        last_login_at: null,
      },
      organizations: [
        {
          id: "org-1",
          name: "AlgoMatrics India",
          slug: "algomatrics-india",
          role: "owner",
          settings: {},
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
      activeOrgId: "org-1",
      status: "authenticated",
    });
  });

  it("renders System Health navigation item directly above Settings", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AppLayout />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const auditLogLink = screen.getByRole("link", { name: /Audit Log/i });
    const systemHealthLink = screen.getByRole("link", { name: /System Health/i });
    const settingsLink = screen.getByRole("link", { name: /Settings/i });

    expect(auditLogLink).toBeInTheDocument();
    expect(systemHealthLink).toBeInTheDocument();
    expect(settingsLink).toBeInTheDocument();

    expect(systemHealthLink).toHaveAttribute("href", "/app/system-health");
    expect(auditLogLink).toHaveAttribute("href", "/app/audit-log");
    expect(settingsLink).toHaveAttribute("href", "/app/settings");

    // Verify ordering in DOM
    const links = screen.getAllByRole("link");
    const auditIdx = links.indexOf(auditLogLink);
    const healthIdx = links.indexOf(systemHealthLink);
    const settingsIdx = links.indexOf(settingsLink);

    expect(auditIdx).toBeLessThan(healthIdx);
    expect(healthIdx).toBeLessThan(settingsIdx);
  });

  it("renders India market section and hides International market section by default", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AppLayout />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // India market group should be visible
    expect(screen.getByRole("button", { name: /India/i })).toBeInTheDocument();

    // International market group should NOT be visible
    expect(screen.queryByRole("button", { name: /International/i })).not.toBeInTheDocument();
  });
});
