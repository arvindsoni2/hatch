import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AiSetupReminder, AI_SETUP_REMINDER_SNOOZE_KEY } from "@/components/hatch/AiSetupReminder";

describe("AiSetupReminder", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("shows an actionable reminder when AI setup is incomplete", () => {
    render(<AiSetupReminder incomplete actionRequired="provider_or_local_model" />);

    expect(screen.getByText("Finish setting up Hatch AI")).toBeVisible();
    expect(screen.getByRole("link", { name: "Configure AI" })).toHaveAttribute("href", "/settings/ai");
  });

  it("persists a seven-day snooze without marking AI configured", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-10T10:00:00Z"));
    render(<AiSetupReminder incomplete actionRequired="provider_or_local_model" />);

    fireEvent.click(screen.getByRole("button", { name: "Not now" }));

    expect(screen.queryByText("Finish setting up Hatch AI")).not.toBeInTheDocument();
    const stored = JSON.parse(localStorage.getItem(AI_SETUP_REMINDER_SNOOZE_KEY) ?? "{}");
    expect(stored.snoozed_until).toBe("2026-07-17T10:00:00.000Z");
    expect(stored.configured).toBeUndefined();
    vi.useRealTimers();
  });
});
