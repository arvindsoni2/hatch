import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RemembersList } from "@/components/settings/RemembersList";

const KINDS = [
  "dismissed_patterns",
  "focus_areas_and_plans",
  "briefs",
  "debriefs",
  "explain_tips",
  "competency_overrides",
  "job_competencies",
] as const;

const LABELS: Record<string, string> = {
  dismissed_patterns: "Dismissed patterns",
  focus_areas_and_plans: "Focus areas and plans",
  briefs: "Briefs",
  debriefs: "Debriefs",
  explain_tips: "Explain tips",
  competency_overrides: "Competency overrides",
  job_competencies: "Job description competencies",
};

type MemoryBody = {
  kinds: {
    kind: (typeof KINDS)[number];
    count: number;
    last_updated: string | null;
  }[];
};

function inventory(overrides: Record<string, number> = {}): MemoryBody {
  return {
    kinds: KINDS.map((kind, index) => ({
      kind,
      count: overrides[kind] ?? index + 1,
      last_updated: "2026-11-02T10:00:00Z",
    })),
  };
}

function allZero(): MemoryBody {
  return { kinds: KINDS.map((kind) => ({ kind, count: 0, last_updated: null })) };
}

function response(body: unknown): Response {
  return { ok: true, json: async () => structuredClone(body), text: async () => "" } as Response;
}

describe("RemembersList", () => {
  let calls: { url: string; method: string }[] = [];
  let current: MemoryBody = inventory();

  beforeEach(() => {
    calls = [];
    current = inventory();
    vi.mocked(global.fetch).mockReset();
    vi.mocked(global.fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method });
      if (method === "GET" && url.endsWith("/api/coach/readiness/memory")) {
        return response(current);
      }
      if (method === "DELETE" && url.includes("/api/coach/readiness/memory/debriefs")) {
        current = allZero();
        return response({ kind: "debriefs", removed: 4 });
      }
      if (method === "DELETE" && url.endsWith("/api/coach/readiness/memory")) {
        current = allZero();
        return response({ removed: Object.fromEntries(KINDS.map((kind) => [kind, 1])) });
      }
      return response({});
    });
  });

  it("lists Patterns as derived and the seven stored kinds with job competencies last", async () => {
    render(<RemembersList />);

    expect(await screen.findByText("Patterns")).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Delete practice sessions in Coach" }),
    ).toHaveAttribute("href", "/coach");
    expect(within(screen.getByText("Patterns").closest("li")!).queryByRole("button")).toBeNull();

    const rows = screen.getAllByRole("listitem").slice(1).map((row) => row.textContent ?? "");
    expect(rows.map((text) => KINDS.find((kind) => text.startsWith(LABELS[kind])))).toEqual([
      ...KINDS,
    ]);
    expect(rows[rows.length - 1]).toContain("Job description competencies");
  });

  it("deletes debriefs with the round-questions option and its confirm copy", async () => {
    const user = userEvent.setup();
    render(<RemembersList />);

    const row = (await screen.findByText("Debriefs")).closest("li")!;
    await user.click(within(row).getByRole("button", { name: "Delete" }));

    expect(await screen.findByText("Delete debriefs?")).toBeVisible();
    expect(
      screen.getByText(/clears the whole question list on each round whose debrief is deleted/),
    ).toBeVisible();
    await user.click(screen.getByLabelText("Also clear questions on the round"));
    await user.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() =>
      expect(calls).toContainEqual({
        url: expect.stringContaining("/api/coach/readiness/memory/debriefs?clear_round_questions=true"),
        method: "DELETE",
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Debriefs: removed 4.");
  });

  it("deletes all readiness data after confirmation", async () => {
    const user = userEvent.setup();
    render(<RemembersList />);

    await screen.findByText("Patterns");
    await user.click(
      screen.getByRole("button", { name: "Delete all Coach readiness data" }),
    );

    expect(await screen.findByText("Delete all Coach readiness data?")).toBeVisible();
    expect(
      screen.getByText(/Your practice sessions, interview rounds, stories and Question Bank entries are untouched/),
    ).toBeVisible();

    const confirm = screen
      .getAllByRole("button", { name: "Delete all Coach readiness data" })
      .at(-1)!;
    await user.click(confirm);

    await waitFor(() =>
      expect(calls).toContainEqual(
        expect.objectContaining({ method: "DELETE", url: expect.stringMatching(/\/memory$/) }),
      ),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Removed 7 readiness rows. Phase 1 data is untouched.",
    );
    expect(screen.getAllByText(/0 rows/)).toHaveLength(7);
  });
});
