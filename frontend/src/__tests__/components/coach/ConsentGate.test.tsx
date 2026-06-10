import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ConsentGate } from "@/components/coach/ConsentGate";

describe("ConsentGate", () => {
  const onAccept = vi.fn();
  const onDecline = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the consent dialog with correct title", () => {
    render(<ConsentGate onAccept={onAccept} onDecline={onDecline} />);
    // h2 heading specifically (multiple elements may match the text, use heading role)
    expect(screen.getByRole("heading", { name: /enable face analysis/i })).toBeInTheDocument();
  });

  it("renders the privacy guarantee section", () => {
    render(<ConsentGate onAccept={onAccept} onDecline={onDecline} />);
    expect(screen.getByText(/never sent to the server/i)).toBeInTheDocument();
  });

  it("renders both Accept and Cancel buttons", () => {
    render(<ConsentGate onAccept={onAccept} onDecline={onDecline} />);
    expect(screen.getByRole("button", { name: /enable face analysis/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
  });

  // test_consent_gate_calls_onAccept
  it("calls onAccept when the enable button is clicked", () => {
    render(<ConsentGate onAccept={onAccept} onDecline={onDecline} />);
    const acceptButton = screen.getByRole("button", { name: /enable face analysis/i });
    fireEvent.click(acceptButton);
    expect(onAccept).toHaveBeenCalledTimes(1);
    expect(onDecline).not.toHaveBeenCalled();
  });

  // test_consent_gate_calls_onDecline
  it("calls onDecline when the cancel button is clicked", () => {
    render(<ConsentGate onAccept={onAccept} onDecline={onDecline} />);
    const cancelButton = screen.getByRole("button", { name: /cancel/i });
    fireEvent.click(cancelButton);
    expect(onDecline).toHaveBeenCalledTimes(1);
    expect(onAccept).not.toHaveBeenCalled();
  });

  // test_consent_gate_blocks_face_capture_until_accepted
  it("does not auto-call onAccept — user must explicitly click", () => {
    render(<ConsentGate onAccept={onAccept} onDecline={onDecline} />);
    // Neither callback should be called without user interaction
    expect(onAccept).not.toHaveBeenCalled();
    expect(onDecline).not.toHaveBeenCalled();
  });

  it("has role=dialog for accessibility", () => {
    render(<ConsentGate onAccept={onAccept} onDecline={onDecline} />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("describes what face analysis does NOT collect", () => {
    render(<ConsentGate onAccept={onAccept} onDecline={onDecline} />);
    expect(screen.getByText(/raw video/i)).toBeInTheDocument();
  });
});
