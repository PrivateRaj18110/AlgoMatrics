import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { PersonalHealthPage } from "./PersonalHealthPage";
import { usePersonalHealth } from "@/stores/personalHealth";

describe("PersonalHealthPage integration", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    usePersonalHealth.getState().resetProgram();
  });

  it("renders the dashboard with initial unrecorded default state", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <PersonalHealthPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Header and description
    expect(screen.getByRole("heading", { name: "Personal Health" })).toBeInTheDocument();
    expect(screen.getByText(/Fitness, weight and recovery tracking/i)).toBeInTheDocument();

    // Initial targets and metrics
    expect(screen.getByText("Current Weight")).toBeInTheDocument();
    expect(screen.getByText("Target Weight")).toBeInTheDocument();
    expect(screen.getByText("60 kg")).toBeInTheDocument();

    // Check for "Not recorded" indicators instead of fake 0s
    const notRecordedBadges = screen.getAllByText("Not recorded");
    expect(notRecordedBadges.length).toBeGreaterThan(0);
  });

  it("switches seamlessly between all feature tabs", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <PersonalHealthPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // 1. Workout Tab
    fireEvent.click(screen.getByRole("button", { name: /Workout/i }));
    expect(screen.getByText(/This Week's Complete Schedule/i)).toBeInTheDocument();
    expect(screen.getByText(/Weekly Cycling/i)).toBeInTheDocument();

    // 2. Progress & Analytics Tab
    fireEvent.click(screen.getByRole("button", { name: /Progress & Analytics/i }));
    expect(screen.getByText(/Weight Loss Trend/i)).toBeInTheDocument();
    expect(screen.getByText(/Weight Loss Forecast/i)).toBeInTheDocument();
    expect(screen.getByText(/ESTIMATE — NOT A GUARANTEE/i)).toBeInTheDocument();

    // 3. Weekly Review Tab
    fireEvent.click(screen.getByRole("button", { name: /Weekly Review/i }));
    expect(screen.getByText(/Program Milestones/i)).toBeInTheDocument();
    expect(screen.getByText(/Weekly Summary & Performance Review/i)).toBeInTheDocument();

    // 4. Calendar Tab
    fireEvent.click(screen.getByRole("button", { name: /Calendar/i }));
    expect(screen.getByText(/Program Calendar \(25 August 2026/i)).toBeInTheDocument();
    expect(screen.getByText(/Status Legend/i)).toBeInTheDocument();

    // 5. Settings Tab
    fireEvent.click(screen.getByRole("button", { name: /Settings/i }));
    expect(screen.getByText(/Program Targets & Body Profile/i)).toBeInTheDocument();
    expect(screen.getByText(/Data Management \(CSV Backup & Restore\)/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Export CSV Backup/i })).toBeInTheDocument();
  });

  it("allows opening Daily Check-In, entering data, saving, and updating the entire dashboard", async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <PersonalHealthPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Open Check-In Modal
    fireEvent.click(screen.getByRole("button", { name: /\+ Daily Check-In/i }));
    expect(screen.getByRole("heading", { name: /Daily Check-In/i })).toBeInTheDocument();

    // Enter Morning Weight
    const weightInput = screen.getByLabelText(/Morning Weight/i);
    fireEvent.change(weightInput, { target: { value: "69.4" } });

    // Enter Calories
    const calInput = screen.getByLabelText(/Calories \(kcal\)/i);
    fireEvent.change(calInput, { target: { value: "1580" } });

    // Enter Cycling
    const cyclingInput = screen.getByLabelText(/Cycling \(km\)/i);
    fireEvent.change(cyclingInput, { target: { value: "20" } });

    // Enter Walking
    const walkingInput = screen.getByLabelText(/Walking \(steps\)/i);
    fireEvent.change(walkingInput, { target: { value: "5400" } });

    // Submit SAVE DAY
    const saveButton = screen.getByRole("button", { name: /SAVE DAY/i });
    fireEvent.click(saveButton);

    // Verify modal closes and dashboard updates with real entered data
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: /Daily Check-In/i })).not.toBeInTheDocument();
    });

    expect(screen.getAllByText("69.4 kg").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/1580/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/20 km/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/5,400/i).length).toBeGreaterThan(0);
  });

  it("updates settings targets without corrupting existing records", async () => {
    // Seed an existing record
    usePersonalHealth.getState().saveDayRecord({
      date: "2026-08-25",
      weightKg: 69.8,
      cyclingKm: 20,
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <PersonalHealthPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Switch to settings
    fireEvent.click(screen.getByRole("button", { name: /Settings/i }));

    const saveSettingsButton = screen.getByRole("button", { name: /Save Settings/i });
    fireEvent.click(saveSettingsButton);

    // Existing record still intact
    const record = usePersonalHealth.getState().getDayRecord("2026-08-25");
    expect(record?.weightKg).toBe(69.8);
    expect(record?.cyclingKm).toBe(20);
  });
});
