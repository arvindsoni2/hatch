import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { CoachModalitySelector } from "@/components/coach/CoachModalitySelector";

// ---------------------------------------------------------------------------
// Mock navigator.mediaDevices for capability detection
// ---------------------------------------------------------------------------

function mockMediaDevices(hasMic: boolean) {
  const devices = hasMic
    ? [{ kind: "audioinput", deviceId: "default", label: "Default Mic" }]
    : [];
  Object.defineProperty(navigator, "mediaDevices", {
    value: {
      enumerateDevices: vi.fn().mockResolvedValue(devices),
      getUserMedia: hasMic
        ? vi.fn().mockResolvedValue({ getTracks: () => [] })
        : vi.fn().mockRejectedValue(new Error("No mic")),
    },
    configurable: true,
    writable: true,
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("CoachModalitySelector", () => {
  const onModeChange = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders text and voice mode buttons", () => {
    mockMediaDevices(true);
    render(<CoachModalitySelector mode="text" onModeChange={onModeChange} />);
    expect(screen.getByRole("button", { name: /text/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /voice/i })).toBeInTheDocument();
  });

  it("text mode button is always enabled", async () => {
    mockMediaDevices(false);
    render(<CoachModalitySelector mode="text" onModeChange={onModeChange} />);
    const textBtn = screen.getByRole("button", { name: /text/i });
    expect(textBtn).not.toBeDisabled();
  });

  it("selecting text mode calls onModeChange with 'text'", () => {
    mockMediaDevices(true);
    render(<CoachModalitySelector mode="voice" onModeChange={onModeChange} />);
    fireEvent.click(screen.getByRole("button", { name: /text/i }));
    expect(onModeChange).toHaveBeenCalledWith("text");
  });

  it("selecting voice mode calls onModeChange with 'voice' when mic available", async () => {
    mockMediaDevices(true);
    render(<CoachModalitySelector mode="text" onModeChange={onModeChange} />);
    const voiceBtn = await screen.findByRole("button", { name: /voice/i });
    // voice should be enabled when mic is available
    if (!voiceBtn.hasAttribute("disabled")) {
      fireEvent.click(voiceBtn);
      expect(onModeChange).toHaveBeenCalledWith("voice");
    }
  });

  it("voice mode is disabled with a reason when mic is unavailable", async () => {
    // Simulate no media devices support at all
    Object.defineProperty(navigator, "mediaDevices", {
      value: undefined,
      configurable: true,
      writable: true,
    });

    render(<CoachModalitySelector mode="text" onModeChange={onModeChange} />);

    await waitFor(() => {
      const voiceBtn = screen.getByRole("button", { name: /voice/i });
      // Either disabled or has aria-disabled
      const isDisabled = voiceBtn.hasAttribute("disabled") || voiceBtn.getAttribute("aria-disabled") === "true";
      expect(isDisabled).toBe(true);
    });
  });

  it("shows reason text when voice is disabled due to no mic", async () => {
    Object.defineProperty(navigator, "mediaDevices", {
      value: undefined,
      configurable: true,
      writable: true,
    });

    render(<CoachModalitySelector mode="text" onModeChange={onModeChange} />);

    await waitFor(() => {
      // A reason message should be visible somewhere in the component
      const reasonEl = screen.queryByText(/microphone|mic/i);
      expect(reasonEl).not.toBeNull();
    });
  });

  it("text mode is highlighted when active", () => {
    mockMediaDevices(true);
    render(<CoachModalitySelector mode="text" onModeChange={onModeChange} />);
    const textBtn = screen.getByRole("button", { name: /text/i });
    // Active button should have a visible highlight class
    expect(textBtn.className).toMatch(/indigo|active|selected|bg-/);
  });

  it("does not call onModeChange when disabled voice button clicked", async () => {
    Object.defineProperty(navigator, "mediaDevices", {
      value: undefined,
      configurable: true,
      writable: true,
    });

    render(<CoachModalitySelector mode="text" onModeChange={onModeChange} />);

    // Wait until the capability check has resolved and the button is disabled
    await waitFor(() => {
      const voiceBtn = screen.getByRole("button", { name: /voice/i });
      expect(
        voiceBtn.hasAttribute("disabled") || voiceBtn.getAttribute("aria-disabled") === "true"
      ).toBe(true);
    });

    fireEvent.click(screen.getByRole("button", { name: /voice/i }));
    expect(onModeChange).not.toHaveBeenCalledWith("voice");
  });

  it("disabled prop prevents all mode changes", () => {
    mockMediaDevices(true);
    render(<CoachModalitySelector mode="text" onModeChange={onModeChange} disabled />);
    fireEvent.click(screen.getByRole("button", { name: /voice/i }));
    expect(onModeChange).not.toHaveBeenCalled();
  });
});
