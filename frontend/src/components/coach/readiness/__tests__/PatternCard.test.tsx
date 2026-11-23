import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PatternCard } from "@/components/coach/readiness/PatternCard";
import type { Pattern } from "@/lib/coachReadinessApi";

const base: Pattern = {
  fingerprint: "a".repeat(64),
  group: {
    role_family: "Delivery Lead",
    interview_type: "behavioural",
    contract_version: "coach_conversational_report_v1",
  },
  dimension: "specificity",
  kind: "forming",
  trend: "not_enough_evidence",
  trend_label: null,
  supporting: [
    {
      session_id: "s1",
      completed_at: "2026-05-01T10:00:00Z",
      level: "developing",
      difficulty: "realistic",
      role_level: "senior",
    },
  ],
  stale: false,
  dismissed: false,
  seen_again: false,
};

describe("PatternCard", () => {
  it("shows a forming pattern as needs more practice with 1 of 2", () => {
    render(<PatternCard pattern={base} />);

    expect(screen.getByText("Needs more practice")).toBeVisible();
    expect(screen.getByText(/1 of 2 sessions/i)).toBeVisible();
  });

  it("uses the glossary copy for every kind", () => {
    const cases = [
      ["focus", "Focus area suggestion"],
      ["strength", "Strength"],
      ["mixed", "Mixed results"],
    ] as const;
    for (const [kind, copy] of cases) {
      const { unmount } = render(
        <PatternCard pattern={{ ...base, kind }} />,
      );
      expect(screen.getByText(copy)).toBeVisible();
      unmount();
    }
  });

  it("renders difficulty-guarded trend labels", () => {
    const cases = [
      ["improving", "Improving"],
      ["easier_difficulty", "Changed at an easier difficulty"],
      ["getting_weaker", "Getting weaker"],
      ["harder_difficulty", "Lower at a harder difficulty"],
    ] as const;
    for (const [label, copy] of cases) {
      const { unmount } = render(
        <PatternCard pattern={{ ...base, trend_label: label }} />,
      );
      expect(screen.getByText(copy)).toBeVisible();
      unmount();
    }
  });

  it("keeps polling after a StrictMode effect replay", async () => {
    const user = userEvent.setup();
    let tipsRequests = 0;
    vi.mocked(global.fetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/tips")) {
        tipsRequests += 1;
        return tipsRequests === 1
          ? { ok: true, status: 202, json: async () => ({ operation_id: "op-1", status: "queued" }), text: async () => "" } as Response
          : { ok: true, status: 200, json: async () => ({ tips: ["A tip."], status: "succeeded" }), text: async () => "" } as Response;
      }
      if (url.includes("/operations/op-1")) {
        return { ok: true, status: 200, json: async () => ({ operation_id: "op-1", status: "succeeded" }), text: async () => "" } as Response;
      }
      return { ok: true, status: 200, json: async () => ({}), text: async () => "" } as Response;
    });

    render(
      <React.StrictMode>
        <PatternCard pattern={base} />
      </React.StrictMode>,
    );
    await user.click(screen.getByRole("button", { name: "Tips" }));

    await waitFor(() => expect(screen.getByText("A tip.")).toBeVisible());
  });

  it("dismisses and can undo a dismissal", async () => {
    const user = userEvent.setup();
    const onDismiss = vi.fn();
    const onUndo = vi.fn();
    const { rerender } = render(
      <PatternCard pattern={base} onDismiss={onDismiss} onUndo={onUndo} />,
    );

    await user.click(screen.getByRole("button", { name: "Dismiss this pattern" }));
    expect(onDismiss).toHaveBeenCalledWith(base.fingerprint);

    rerender(
      <PatternCard
        pattern={{ ...base, dismissed: true }}
        onDismiss={onDismiss}
        onUndo={onUndo}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Undo dismissal" }));
    expect(onUndo).toHaveBeenCalledWith(base.fingerprint);
  });

  it("says when a new support set follows a dismissal", () => {
    render(<PatternCard pattern={{ ...base, seen_again: true }} />);

    expect(
      screen.getByText("Seen again since you dismissed it"),
    ).toBeVisible();
  });

  it("marks stale patterns as older", () => {
    render(<PatternCard pattern={{ ...base, stale: true }} />);

    expect(screen.getByText("Older")).toBeVisible();
  });
});
