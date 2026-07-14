import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SetupStatusPanel } from "@/components/setup/SetupStatusPanel";

describe("SetupStatusPanel", () => {
  it("distinguishes selected setup from active setup and exposes host actions", () => {
    const onCheckAgain = vi.fn();
    render(<SetupStatusPanel
      loading={false}
      error={null}
      onCheckAgain={onCheckAgain}
      status={{
        overall_status: "pending_host_action",
        onboarding: { status: "complete", last_completed_step: "protect-workspace" },
        intent: { schema_version: 2, ai_mode: "cloud", backend_profile: "full", experience: "custom" },
        ai: { mode: "cloud", status: "pending_host_action", healthy: false },
        capabilities: { profile: "core", selected_profile: "full", enabled: [], operation: null },
        next_actions: [{ id: "provider.secret", label: "Configure secret", command: "hatch secrets set anthropic", args: [] }],
      }}
    />);

    expect(screen.getByText(/Selected: Cloud AI.*Full capabilities/i)).toBeVisible();
    expect(screen.getByText(/Active: Standard Hatch/i)).toBeVisible();
    expect(screen.getByText("hatch secrets set anthropic")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    expect(onCheckAgain).toHaveBeenCalledOnce();
  });
});
