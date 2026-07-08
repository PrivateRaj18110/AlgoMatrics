import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LoginPage } from "@/pages/auth/LoginPage";

const navigate = vi.fn();
vi.mock("react-router", async () => {
  const actual = await vi.importActual<typeof import("react-router")>("react-router");
  return { ...actual, useNavigate: () => navigate };
});

describe("LoginPage", () => {
  beforeEach(() => {
    navigate.mockReset();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("validates required fields before submitting", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter a valid e-mail")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows an error message when the API rejects the credentials", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      json: async () => ({ code: "authentication_failed", detail: "invalid e-mail or password" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
    await userEvent.type(screen.getByPlaceholderText("you@example.com"), "user@example.com");
    await userEvent.type(screen.getByLabelText(/password/i, { selector: "input" }), "secret123");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() =>
      expect(screen.getByText("invalid e-mail or password")).toBeInTheDocument(),
    );
    expect(navigate).not.toHaveBeenCalled();
  });
});
