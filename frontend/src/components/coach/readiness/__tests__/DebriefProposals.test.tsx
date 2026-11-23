import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  acceptDebriefProposal,
  type DebriefProposal,
  type DebriefRead,
} from "@/lib/coachReadinessApi";
import { DebriefProposals } from "@/components/coach/readiness/DebriefProposals";

vi.mock("@/lib/coachReadinessApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/coachReadinessApi")>();
  return {
    ...actual,
    acceptDebriefProposal: vi.fn(),
  };
});

const saved: DebriefRead = {
  round_id: "round-1",
  application_id: "app-1",
  round_status: "completed",
  scheduled_at: null,
  duration_minutes: 60,
  status: "saved",
  version: 2,
  overall: 4,
  expectation: null,
  questions: [],
  went_well: null,
  do_differently: null,
  notes_text: null,
  questions_added: 0,
  proposals: [],
};

const qb: DebriefProposal = {
  id: "question_bank:abc",
  kind: "question_bank",
  questions: ["How do you handle pressure?", "Why this team?"],
  story_id: null,
  story_title: null,
  accepted: false,
};
const story: DebriefProposal = {
  id: "story_use:story-1",
  kind: "story_use",
  questions: [],
  story_id: "story-1",
  story_title: "Rescued a late delivery",
  accepted: false,
};

describe("DebriefProposals", () => {
  beforeEach(() => {
    vi.mocked(acceptDebriefProposal).mockReset();
    vi.mocked(acceptDebriefProposal).mockResolvedValue(saved);
  });

  it("offers the Question Bank batch and the story use", () => {
    render(
      <DebriefProposals roundId="round-1" proposals={[qb, story]} onAccepted={vi.fn()} />,
    );

    expect(screen.getByText(/Add 2 new questions to your Question Bank/)).toBeVisible();
    expect(screen.getByText(/Record that you used Rescued a late delivery/)).toBeVisible();
  });

  it("accepts through the public route and reports the new version", async () => {
    const user = userEvent.setup();
    const onAccepted = vi.fn();
    render(
      <DebriefProposals roundId="round-1" proposals={[qb]} onAccepted={onAccepted} />,
    );

    await user.click(screen.getByRole("button", { name: "Accept" }));

    await waitFor(() =>
      expect(vi.mocked(acceptDebriefProposal)).toHaveBeenCalledWith(
        "round-1",
        "question_bank:abc",
      ),
    );
    expect(onAccepted).toHaveBeenCalledWith(2, []);
  });

  it("dismiss stores nothing: the card just disappears", async () => {
    const user = userEvent.setup();
    render(
      <DebriefProposals roundId="round-1" proposals={[story]} onAccepted={vi.fn()} />,
    );

    await user.click(screen.getByRole("button", { name: "Not now" }));

    expect(screen.queryByText(/Record that you used/)).not.toBeInTheDocument();
    expect(vi.mocked(acceptDebriefProposal)).not.toHaveBeenCalled();
  });

  it("renders nothing once every proposal is accepted", () => {
    const { container } = render(
      <DebriefProposals
        roundId="round-1"
        proposals={[{ ...qb, accepted: true }]}
        onAccepted={vi.fn()}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
