import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/stores/auth", () => ({
  useAuth: (selector: (state: { loadContext: () => Promise<void> }) => unknown) =>
    selector({ loadContext: vi.fn().mockResolvedValue(undefined) }),
}));

import { AcceptInvitationPage } from "@/pages/auth/AcceptInvitationPage";

describe("AcceptInvitationPage", () => {
  it("explains when the invitation token is missing", () => {
    render(
      <MemoryRouter initialEntries={["/invitations/accept"]}>
        <AcceptInvitationPage />
      </MemoryRouter>,
    );

    expect(screen.getByText(/missing its token/i)).toBeInTheDocument();
  });
});
