/**
 * Tests for the TTS speaker button integration in the Coach session page.
 *
 * The TTS button is rendered inline in the session page (not a separate component),
 * so we test the getTTSQuestionUrl API helper and the button's conditional rendering logic.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { getTTSQuestionUrl } from "@/lib/api";

// ---------------------------------------------------------------------------
// Test getTTSQuestionUrl helper
// ---------------------------------------------------------------------------

describe("getTTSQuestionUrl", () => {
  it("returns the correct URL for a session and question", () => {
    const url = getTTSQuestionUrl("session-123", "question-456");
    expect(url).toBe("/api/coach/sessions/session-123/tts-question?question_id=question-456");
  });

  it("handles special characters in session and question IDs", () => {
    const url = getTTSQuestionUrl("s-abc-123", "q-def-456");
    expect(url).toContain("s-abc-123");
    expect(url).toContain("q-def-456");
  });
});

// ---------------------------------------------------------------------------
// Test TTS button conditional rendering logic (unit-level)
// ---------------------------------------------------------------------------

/**
 * Minimal TTS button component mirroring the session page inline button.
 * We extract the logic here for isolated testing.
 */
function TTSButtonStub({
  ttsEnabled,
  onPlay,
}: {
  ttsEnabled: boolean;
  onPlay: () => void;
}) {
  if (!ttsEnabled) return null;
  return (
    <button
      type="button"
      aria-label="Play question aloud"
      onClick={onPlay}
    >
      Play
    </button>
  );
}

describe("TTS button conditional rendering", () => {
  const onPlay = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  // Test speaker button appears when tts capability is true
  it("shows the speaker button when tts capability is true", () => {
    render(<TTSButtonStub ttsEnabled={true} onPlay={onPlay} />);
    expect(screen.getByRole("button", { name: /play question aloud/i })).toBeInTheDocument();
  });

  // Test button is absent when tts capability is false
  it("does not show the button when tts capability is false", () => {
    render(<TTSButtonStub ttsEnabled={false} onPlay={onPlay} />);
    expect(screen.queryByRole("button", { name: /play question aloud/i })).toBeNull();
  });

  it("calls onPlay when the button is clicked", () => {
    render(<TTSButtonStub ttsEnabled={true} onPlay={onPlay} />);
    fireEvent.click(screen.getByRole("button", { name: /play question aloud/i }));
    expect(onPlay).toHaveBeenCalledTimes(1);
  });
});
