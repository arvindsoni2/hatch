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

function inventory(count = 1): MemoryBody {
  return {
    kinds: KINDS.map((kind, index) => ({
      kind,
      count: index === 6 ? count : 2,
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

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

describe("RemembersList", () => {
  let calls: { url: string; method: string }[] = [];
  let current: MemoryBody = inventory();
  let failDelete = false;
  let hangRefresh: ReturnType<typeof deferred<MemoryBody>> | null = null;

  beforeEach(() => {
    calls = [];
    current = inventory();
    failDelete = false;
    hangRefresh = null;
    vi.mocked(global.fetch).mockReset();
    vi.mocked(global.fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method });
      if (method === "GET" && url.endsWith("/api/coach/readiness/memory")) {
        if (hangRefresh) {
          const body = await hangRefresh.promise;
          hangRefresh = null;
          return response(body);
        }
        return response(current);
      }
      if (method === "DELETE" && failDelete) {
        return { ok: false, json: async () => ({}), text: async () => "boom" } as Response;
      }
      if (method === "DELETE" && url.includes("/api/coach/readiness/memory/debriefs")) {
        current = allZero();
        return response({ kind: "debriefs", removed: 4 });
      }
      if (method === "DELETE" && url.includes("/api/coach/readiness/memory/briefs")) {
        current = { ...current, kinds: current.kinds.map((item) => item.kind === "briefs" ? { ...item, count: 0 } : item) };
        return response({ kind: "briefs", removed: 1 });
      }
      if (method === "DELETE" && url.endsWith("/api/coach/readiness/memory")) {
        const removed = Object.fromEntries(current.kinds.map((item) => [item.kind, item.count]));
        current = allZero();
        return response({ removed });
      }
      return response({});
    });
  });

  it("lists Patterns as derived and the seven stored kinds with unique delete names", async () => {
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
    // Singular row copy and a timezone abbreviation from the display timezone.
    expect(rows[rows.length - 1]).toContain("1 row");
    expect(rows[rows.length - 1]).toContain("Last updated");
    expect(rows[rows.length - 1]).toMatch(/GMT|BST/);

    for (const kind of KINDS) {
      expect(screen.getByRole("button", { name: `Delete ${LABELS[kind]}` })).toBeVisible();
    }
  });

  it("deletes debriefs with the round-questions option and its effect copy", async () => {
    const user = userEvent.setup();
    render(<RemembersList />);

    await user.click(await screen.findByRole("button", { name: "Delete Debriefs" }));

    expect(await screen.findByText("Delete debriefs?")).toBeVisible();
    expect(
      screen.getByText(/clears the whole question list on each round whose debrief is deleted/),
    ).toBeVisible();
    await user.click(screen.getByLabelText("Also clear questions on the round"));
    await user.click(
      within(screen.getByRole("alertdialog")).getByRole("button", { name: "Delete" }),
    );

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
      screen.getByText(/practice sessions, interview rounds, stories and Question Bank entries are untouched/),
    ).toBeVisible();

    await user.click(
      within(screen.getByRole("alertdialog")).getByRole("button", {
        name: "Delete all Coach readiness data",
      }),
    );

    await waitFor(() =>
      expect(calls).toContainEqual(
        expect.objectContaining({ method: "DELETE", url: expect.stringMatching(/\/memory$/) }),
      ),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Removed 13 readiness rows.",
    );
    expect(screen.getAllByText(/0 rows/)).toHaveLength(7);
  });

  it("shows only the error and Try again when the inventory fails", async () => {
    const user = userEvent.setup();
    let first = true;
    vi.mocked(global.fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if ((init?.method ?? "GET") === "GET" && url.endsWith("/api/coach/readiness/memory")) {
        if (first) {
          first = false;
          return { ok: false, json: async () => ({}), text: async () => "offline" } as Response;
        }
        return response(inventory());
      }
      return response({});
    });

    render(<RemembersList />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("What Hatch remembers is unavailable.");
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
    expect(
      screen.queryByRole("button", { name: "Delete all Coach readiness data" }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("Patterns")).toBeVisible();
    expect(screen.getAllByRole("listitem")).toHaveLength(8);
  });

  it("shows delete failures in the open dialog and clears an old success", async () => {
    const user = userEvent.setup();
    render(<RemembersList />);

    await user.click(await screen.findByRole("button", { name: "Delete Briefs" }));
    await user.click(
      within(screen.getByRole("alertdialog")).getByRole("button", { name: "Delete" }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Briefs: removed 1.");

    // Opening a new action clears the previous success line.
    await user.click(screen.getByRole("button", { name: "Delete Explain tips" }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    failDelete = true;
    await user.click(
      within(screen.getByRole("alertdialog")).getByRole("button", { name: "Delete" }),
    );

    const dialog = screen.getByRole("alertdialog");
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Could not delete that. Try again.",
    );
    expect(dialog).toBeVisible();
  });

  it("returns focus to the trigger after cancel, Escape and delete", async () => {
    const user = userEvent.setup();
    render(<RemembersList />);

    const briefs = await screen.findByRole("button", { name: "Delete Briefs" });

    await user.click(briefs);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(briefs).toHaveFocus());

    await user.click(briefs);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(briefs).toHaveFocus());

    // The list stays mounted while the post-delete refresh is in flight.
    const refresh = deferred<MemoryBody>();
    await user.click(briefs);
    await waitFor(() => expect(calls.some((call) => call.method === "GET" && call.url.endsWith("/memory"))).toBe(true));
    hangRefresh = refresh;
    await user.click(
      within(screen.getByRole("alertdialog")).getByRole("button", { name: "Delete" }),
    );
    await waitFor(() =>
      expect(calls.filter((call) => call.method === "GET" && call.url.endsWith("/memory")).length).toBeGreaterThan(1),
    );
    expect(screen.getByText("Briefs")).toBeVisible();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();

    refresh.resolve(inventory());
    await waitFor(() => expect(briefs).toHaveFocus());
  });
});
