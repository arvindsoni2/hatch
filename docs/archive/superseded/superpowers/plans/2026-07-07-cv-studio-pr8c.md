---
title: CV Studio PR 8C Implementation Plan
document_type: historical
status: historical
implementation_status: not-applicable
applies_to: main
last_verified: 2026-07-10
supersedes: []
superseded_by: []
---

> [!WARNING]
> This document is retained for historical context. It does not describe the current Hatch implementation on `main`.

# CV Studio PR 8C Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align CV Studio with the PR 8 core-screen UX foundation without changing tailoring APIs or Master CV settings.

**Architecture:** Keep `/tailor` as the canonical CV Studio route. Add a small Tailor-specific progress component for the named stages, replace route spinner/error fallback with semantic states, and update the page copy/action hierarchy in place. Tests cover route states and the stage component before production changes.

**Tech Stack:** Next.js App Router, React, Vitest, Testing Library, existing Hatch CSS tokens and shared Button.

## Global Constraints

- Work from the latest merged target branch.
- Scope is PR 8C only: CV Studio.
- Do not change Prep, Coach, Analytics, Agents, Settings Master CV internals, scoring, tailoring APIs, or backend behaviour.
- Preserve `/tailor` route and existing `jobUrl` query behaviour.
- Use canonical vocabulary: CV Studio for `/tailor`, Master CV for `/settings/resume`, Applications for `/tracker`.
- Dense layouts must work at 375px, 768px, 1024px, and 1440px.
- Status animation appears only for confirmed active work.
- Run targeted tests, type-check, production build, and `git diff --check`.

---

### Task 1: Add Tested CV Studio Route States

**Files:**
- Modify: `frontend/src/__tests__/components/CoreRouteStates.test.tsx`
- Modify: `frontend/src/app/tailor/loading.tsx`
- Modify: `frontend/src/app/tailor/error.tsx`

**Interfaces:**
- Produces: `Loading` exposes `role="status"` with accessible name `Loading CV Studio` and three `cv-studio-loading-skeleton` blocks.
- Produces: `Error` exposes `role="alert"`, a `Retry` button, and an `Open Diagnostics` link.

- [ ] **Step 1: Write failing route-state tests**

Add two tests to `frontend/src/__tests__/components/CoreRouteStates.test.tsx`:

```tsx
  it("renders a named CV Studio loading skeleton", async () => {
    const { default: Loading } = await import("@/app/tailor/loading");

    render(<Loading />);

    expect(screen.getByRole("status", { name: "Loading CV Studio" })).toBeVisible();
    expect(screen.getAllByTestId("cv-studio-loading-skeleton")).toHaveLength(3);
  });

  it("renders a recoverable CV Studio error with Diagnostics", async () => {
    const { default: ErrorState } = await import("@/app/tailor/error");
    const reset = vi.fn();

    render(<ErrorState error={new Error("tailoring unavailable")} reset={reset} />);

    expect(screen.getByRole("alert")).toHaveTextContent("CV Studio could not load");
    expect(screen.getByText("tailoring unavailable")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(reset).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: "Open Diagnostics" })).toHaveAttribute("href", "/settings/system");
  });
```

- [ ] **Step 2: Verify tests fail**

Run: `cd frontend && npm test -- CoreRouteStates.test.tsx`

Expected: FAIL because CV Studio loading has no named status/skeletons and error has no alert/diagnostics link.

- [ ] **Step 3: Implement route states**

Update `frontend/src/app/tailor/loading.tsx` to render a tokenised skeleton with the expected role/name and three content blocks.

Update `frontend/src/app/tailor/error.tsx` to match the recoverable Pipeline/Applications pattern, using CV Studio wording and `/settings/system`.

- [ ] **Step 4: Verify tests pass**

Run: `cd frontend && npm test -- CoreRouteStates.test.tsx`

Expected: PASS.

### Task 2: Add a Tested Named Stage Rail

**Files:**
- Create: `frontend/src/components/tailor/CVStudioProgress.tsx`
- Create: `frontend/src/__tests__/components/CVStudioProgress.test.tsx`
- Modify: `frontend/src/app/tailor/page.tsx`

**Interfaces:**
- Produces: `CVStudioProgress({ stage }: { stage: "idle" | "analysing" | "analysed" | "generating" | "complete" | "error" })`.
- Produces: Accessible list named `CV Studio progress`.

- [ ] **Step 1: Write failing component tests**

Create `frontend/src/__tests__/components/CVStudioProgress.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CVStudioProgress } from "@/components/tailor/CVStudioProgress";

describe("CVStudioProgress", () => {
  it("names the CV Studio stages without decorative numbering", () => {
    render(<CVStudioProgress stage="idle" />);

    expect(screen.getByRole("list", { name: "CV Studio progress" })).toBeVisible();
    expect(screen.getByText("Add job")).toBeVisible();
    expect(screen.getByText("Analyse fit")).toBeVisible();
    expect(screen.getByText("Choose CV")).toBeVisible();
    expect(screen.getByText("Create pack")).toBeVisible();
    expect(screen.queryByText(/1\\./)).not.toBeInTheDocument();
  });

  it("marks active and complete stages from current work state", () => {
    render(<CVStudioProgress stage="generating" />);

    expect(screen.getByText("Add job").closest("li")).toHaveAttribute("data-state", "complete");
    expect(screen.getByText("Analyse fit").closest("li")).toHaveAttribute("data-state", "complete");
    expect(screen.getByText("Choose CV").closest("li")).toHaveAttribute("data-state", "complete");
    expect(screen.getByText("Create pack").closest("li")).toHaveAttribute("data-state", "active");
  });
});
```

- [ ] **Step 2: Verify tests fail**

Run: `cd frontend && npm test -- CVStudioProgress.test.tsx`

Expected: FAIL because `CVStudioProgress` does not exist.

- [ ] **Step 3: Implement the component**

Create a compact responsive stage rail using Hatch semantic tokens, `CheckCircle2`, `Clock`, and `XCircle`. Use a pulsing indicator only for `analysing` and `generating`.

- [ ] **Step 4: Integrate it into `/tailor`**

Import `CVStudioProgress` in `frontend/src/app/tailor/page.tsx` and render it below `ProfileSummaryCard`.

- [ ] **Step 5: Verify component tests pass**

Run: `cd frontend && npm test -- CVStudioProgress.test.tsx`

Expected: PASS.

### Task 3: Replace CV Studio Numbered Headings and Improve States

**Files:**
- Modify: `frontend/src/app/tailor/page.tsx`
- Modify: `frontend/src/__tests__/components/CVStudioProgress.test.tsx` if needed for copy guarantees

**Interfaces:**
- Consumes: `CVStudioProgress` from Task 2.
- Preserves: `handleAnalyse`, `handleGenerate`, `jobUrl`, analysis restore, document history, and generation flow.

- [ ] **Step 1: Write failing page-copy test if route component is testable**

If route-level rendering can be isolated without brittle API mocking, add a focused test that numbered headings are absent and stage names are present. If route rendering would require broad unrelated mocks, rely on the component test from Task 2 and do not add brittle coverage.

- [ ] **Step 2: Update visible copy and action context**

In `frontend/src/app/tailor/page.tsx`:

- Replace `1. Add the job` with `Add job`.
- Replace `2. Choose your CV` with `Choose CV`.
- Replace `3. Review and create` with `Review evidence`.
- Keep the primary action as `Create application pack`.
- Make the empty state explain the one next action and link to Master CV only as secondary context.
- Keep the generating message as the only animated/pulsing work state.
- Use `role="alert"` for the inline error panel.
- Use `role="status"` for complete/success panel.

- [ ] **Step 3: Run targeted tests**

Run:

```bash
cd frontend && npm test -- CoreRouteStates.test.tsx CVStudioProgress.test.tsx ResumeStudio.test.tsx
```

Expected: PASS.

### Task 4: PR Handoff and Validation

**Files:**
- Modify: `docs/hatch_ux_gap_review_codex_spec.md`
- Add: `docs/visual-evidence/pr8c-cv-studio/` screenshots if Playwright visual capture is available in the environment.

**Interfaces:**
- Updates PR 8 ledger/handoff with PR 8B merged and PR 8C implementation branch.

- [ ] **Step 1: Run broader validation**

Run:

```bash
cd frontend && npm run type-check
cd frontend && npm test -- CoreRouteStates.test.tsx CVStudioProgress.test.tsx ResumeStudio.test.tsx
cd frontend && npm run build
git diff --check
```

Expected: PASS, except known pre-existing warnings must be recorded.

- [ ] **Step 2: Capture visual evidence when feasible**

Use the local app to capture CV Studio at 375px and 1440px in light and dark themes. Save under `docs/visual-evidence/pr8c-cv-studio/`.

- [ ] **Step 3: Update spec handoff**

Update the PR 8 ledger entry to mention PR 8B merged as GitHub PR #16 and PR 8C branch `ux/12-cv-studio-states`. Add a concise PR 8C handoff note with validation and visual evidence status.

- [ ] **Step 4: Final status**

Report branch, changed files, validation, and any skipped visual evidence.
