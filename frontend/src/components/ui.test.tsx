import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Badge, Button, EmptyState, Switch, statusColor } from "@/components/ui";

describe("UI primitives", () => {
  it("renders a button and handles clicks", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Deploy</Button>);
    await userEvent.click(screen.getByRole("button", { name: "Deploy" }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("disables button while loading", () => {
    render(
      <Button loading onClick={() => undefined}>
        Save
      </Button>,
    );
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("toggles a switch", async () => {
    const onChange = vi.fn();
    render(<Switch checked={false} onChange={onChange} label="MFA" />);
    await userEvent.click(screen.getByRole("switch"));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("renders empty state with action", () => {
    render(<EmptyState title="Nothing here" body="Add something" />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.getByText("Add something")).toBeInTheDocument();
  });

  it("maps statuses to colors and renders badges", () => {
    expect(statusColor("filled")).toBe("green");
    expect(statusColor("rejected")).toBe("red");
    expect(statusColor("pending")).toBe("amber");
    expect(statusColor("submitted")).toBe("blue");
    render(<Badge color="green">active</Badge>);
    expect(screen.getByText("active")).toBeInTheDocument();
  });
});
