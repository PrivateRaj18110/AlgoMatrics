import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { CalendarPage } from "./CalendarPage";
import { useCalendarStore } from "@/stores/calendarEvents";

describe("CalendarPage", () => {
  beforeEach(() => {
    // Reset calendar store state
    useCalendarStore.setState({
      events: [
        {
          id: "test-gym",
          title: "Gym Workout",
          date: "2026-08-24",
          startTime: "07:00",
          endTime: "08:00",
          category: "gym",
          createdAt: "2026-08-23T00:00:00Z",
          updatedAt: "2026-08-23T00:00:00Z",
        },
      ],
    });
  });

  it("renders the weekly calendar time-grid by default", () => {
    render(<CalendarPage />);
    expect(screen.getByRole("heading", { name: /weekly calendar/i })).toBeInTheDocument();
    expect(screen.getByText("Asia/Kolkata (IST)")).toBeInTheDocument();

    // Verify Market Session strip
    expect(screen.getByText(/Pre-Market 09:00–09:15/i)).toBeInTheDocument();
    expect(screen.getByText(/Market Hours 09:15–15:15/i)).toBeInTheDocument();
    expect(screen.getByText(/Cash Market 15:15–15:45/i)).toBeInTheDocument();

    // Verify + Add Event button is present
    expect(screen.getByRole("button", { name: /\+ add event/i })).toBeInTheDocument();
  });

  it("allows switching between Day, Week, and Month views", async () => {
    const user = userEvent.setup();
    render(<CalendarPage />);

    // Click Month view
    const monthButton = screen.getByRole("button", { name: /^month$/i });
    await user.click(monthButton);
    expect(screen.getByText("Sun")).toBeInTheDocument();
    expect(screen.getByText("Mon")).toBeInTheDocument();

    // Switch back to Week view
    const weekButton = screen.getByRole("button", { name: /^week$/i });
    await user.click(weekButton);
    expect(screen.getByText("IST")).toBeInTheDocument();
  });

  it("allows adding a new user event through the Add Event modal", async () => {
    const user = userEvent.setup();
    render(<CalendarPage />);

    // Click + Add Event
    const addBtn = screen.getByRole("button", { name: /\+ add event/i });
    await user.click(addBtn);

    // Modal opens
    expect(screen.getByRole("heading", { name: /create calendar event/i })).toBeInTheDocument();

    // Fill form
    const titleInput = screen.getByPlaceholderText(/e\.g\. Morning Gym/i);
    await user.type(titleInput, "Team Architecture Sync");

    // Save event
    const saveBtn = screen.getByRole("button", { name: /create event/i });
    await user.click(saveBtn);

    // Verify event is in store
    const events = useCalendarStore.getState().events;
    expect(events.some((e) => e.title === "Team Architecture Sync")).toBe(true);
  });

  it("allows opening event details and deleting a user event", async () => {
    const user = userEvent.setup();
    render(<CalendarPage />);

    // Event title should be present
    const eventCards = screen.getAllByText(/Gym Workout/i);
    expect(eventCards.length).toBeGreaterThan(0);

    // Click on the event card
    await user.click(eventCards[0]);

    // Detail modal should open
    expect(screen.getByRole("heading", { name: /event details/i })).toBeInTheDocument();

    // Click Delete
    const deleteBtn = screen.getByRole("button", { name: /delete/i });
    await user.click(deleteBtn);

    // Confirm dialog
    expect(screen.getByText(/Are you sure you want to delete/i)).toBeInTheDocument();
    const confirmDeleteBtn = screen.getAllByRole("button", { name: /^delete$/i });
    await user.click(confirmDeleteBtn[confirmDeleteBtn.length - 1]);

    // Verify event is deleted from store
    const events = useCalendarStore.getState().events;
    expect(events.some((e) => e.id === "test-gym")).toBe(false);
  });

  it("renders system market blocks that open informational schedule details", async () => {
    const user = userEvent.setup();
    render(<CalendarPage />);

    // System market blocks exist on trading days with title attribute
    const marketHoursBlocks = screen.getAllByTitle(/Market Hours \(09:15–15:15 IST\)/i);
    expect(marketHoursBlocks.length).toBeGreaterThan(0);

    // Click on market hours grid block
    await user.click(marketHoursBlocks[0]);

    // Market schedule modal opens
    expect(screen.getByRole("heading", { name: /system market schedule/i })).toBeInTheDocument();
    expect(screen.getByText(/SYSTEM SCHEDULE/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Indian equity\/derivatives market/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Continuous automated matching/i)).toBeInTheDocument();
  });
});
