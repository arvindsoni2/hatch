---
title: Onboarding Editorial Redesign — Implementation Plan
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

# Onboarding Editorial Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the first-run onboarding wizard (`/onboarding`) in the Editorial visual direction — dark-first, Newsreader serif headings, 6 focused form steps + Welcome + Success screen, per-field helper text, localStorage save/resume.

**Architecture:** The onboarding route uses a `fixed inset-0 z-50` full-viewport overlay to sit on top of the existing Sidebar/BottomNav without restructuring the app layout. Editorial tokens are scoped to `[data-onboarding="true"]` so they never bleed into the dashboard. Newsreader is self-hosted via `@fontsource/newsreader`. All shadcn primitives (`button`, `input`, `card`) are made token-aware so they work in both themes.

**Tech Stack:** Next.js 14 App Router, TypeScript, Tailwind CSS, `cva`, Vitest, Playwright. Backend: FastAPI, locale YAML packs. Font: `@fontsource/newsreader`.

**Reference files:** `design_handoff_onboarding/reference/onboarding/` (screens.jsx, fields.jsx, onboarding.css, app.jsx) — build Editorial direction only.

---

## File Map

**New files:**
- `frontend/src/components/onboarding/OnboardingPrimitives.tsx` — Field, Help, Why, TagInput, Choice, Seg, ToggleRow, ChipInfo
- `frontend/src/components/onboarding/ScreenWelcome.tsx` — Welcome screen (value pipeline, trust chips)
- `frontend/src/components/onboarding/ScreenSuccess.tsx` — Done screen (pulsing check, scout indicator, summary)
- `frontend/src/components/onboarding/StepMarket.tsx` — Locale cards + target roles + employment type
- `frontend/src/components/onboarding/StepPay.tsx` — City + remote + rate min/max + locale-derived currency chip
- `frontend/src/components/onboarding/StepEligibility.tsx` — Why callout + legal fields as Choice cards
- `frontend/src/app/onboarding/onboarding.css` — editorial token scope + component styles
- `frontend/src/__tests__/components/OnboardingPrimitives.test.tsx` — unit tests for primitives

**Modified files:**
- `locales/uk.yaml`, `locales/us.yaml`, `locales/de.yaml`, `locales/in.yaml`, `locales/_template.yaml` — add `help` to each `legal_fields` entry
- `backend/app/services/locale_service.py` — extend `list_locales()` to include `currency`, `currency_symbol`, `default_rate_type`
- `frontend/src/lib/api.ts` — extend `LocaleSummary` + `LocaleLegalField` types; add `fetchLocaleDetails`
- `frontend/src/components/ui/button.tsx` — token-aware variants
- `frontend/src/components/ui/input.tsx` — token-aware classes
- `frontend/src/components/ui/card.tsx` — token-aware classes
- `frontend/src/app/globals.css` — add `[data-onboarding]` token scope + Newsreader `@font-face`
- `frontend/src/components/onboarding/OnboardingProgress.tsx` — numeral style, 6 steps
- `frontend/src/components/onboarding/StepAboutYou.tsx` — add Field+Help wrapper, per-field helper text
- `frontend/src/components/onboarding/StepSkills.tsx` — use new TagInput with suggestions, add helper text
- `frontend/src/components/onboarding/StepAIProvider.tsx` — use Choice + ToggleRow + Field+Help, dark tokens
- `frontend/src/app/onboarding/page.tsx` — rewrite controller (6 steps, Welcome, Success, localStorage, currency auto-derive, `_tried` inline validation)
- `frontend/package.json` — add `@fontsource/newsreader`

**Kept as reference (do not delete):**
- `frontend/src/components/onboarding/StepJobSearch.tsx`
- `frontend/src/components/onboarding/StepReview.tsx`

---

## Task 1: Install Newsreader font + add @font-face

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/src/app/globals.css`

- [ ] **Step 1: Install @fontsource/newsreader**

```bash
cd frontend && npm install @fontsource/newsreader
```

- [ ] **Step 2: Verify the package installed**

```bash
ls frontend/node_modules/@fontsource/newsreader/
```
Expected: directory exists with `500.css` and font files.

- [ ] **Step 3: Add @font-face declaration to globals.css**

Add after the existing `:root` block in `frontend/src/app/globals.css`:

```css
/* ── Newsreader — self-hosted via @fontsource, scoped to onboarding headings ── */
@import "@fontsource/newsreader/500.css";
@import "@fontsource/newsreader/500-italic.css";
```

Add this at the **top** of `globals.css`, before `@tailwind base;`:

```css
@import "@fontsource/newsreader/500.css";
@import "@fontsource/newsreader/500-italic.css";
```

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/app/globals.css
git commit -m "feat: self-host Newsreader font via @fontsource for onboarding headings"
```

---

## Task 2: Add editorial token scope to globals.css

**Files:**
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/tailwind.config.ts`

- [ ] **Step 1: Add the `[data-onboarding]` token scope at the bottom of globals.css**

Append to `frontend/src/app/globals.css`:

```css
/* ── Editorial onboarding token scope ─────────────────────────────────────────
   Scoped to [data-onboarding="true"] — never bleeds into the app shell.
   Matches design_handoff_onboarding/reference/onboarding/onboarding.css editorial block.
   ──────────────────────────────────────────────────────────────────────────── */
[data-onboarding="true"] {
  --bg:               #08090b;
  --bg-elevated:      #0d0f13;
  --bg-elev:          #0d0f13;       /* alias used in onboarding components */
  --surface:          #111318;
  --surface-2:        #181b22;
  --surface-3:        #20242c;
  --border:           #20242c;
  --border-strong:    #2d323d;
  --text:             #f5f7fa;
  --text-dim:         #aab2bf;
  --text-muted:       #6f7886;
  --accent:           #7c83ff;
  --accent-hover:     #969cff;
  --accent-soft:      rgba(124, 131, 255, 0.14);
  --accent-soft-strong: rgba(124, 131, 255, 0.24);
  --on-accent:        #0a0a1a;
  --success:          #45d6a4;
  --success-soft:     rgba(69, 214, 164, 0.13);
  --danger:           #ff6f7d;
  --danger-soft:      rgba(255, 111, 125, 0.13);
  --warning:          #f4bd55;
  --warning-soft:     rgba(244, 189, 85, 0.13);
  --font-hero:        'Newsreader', Georgia, serif;
  --r-field:          8px;
  --r-card:           10px;
  --r-btn:            8px;
  --r-chip:           6px;
  color-scheme: dark;
}

/* Fade-in animation used by onboarding screens */
@keyframes ob-fadein {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: none; }
}
.ob-fadein { animation: ob-fadein 0.3s ease both; }

/* Pulse animation used by success screen */
@keyframes ob-pulse {
  0%, 100% { box-shadow: 0 0 0 0 var(--success-soft); }
  50%       { box-shadow: 0 0 0 12px transparent; }
}
.ob-pulse { animation: ob-pulse 2s ease infinite; }

/* Blink animation for live dot */
@keyframes ob-blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.3; }
}
.ob-blink { animation: ob-blink 1.4s ease-in-out infinite; }
```

- [ ] **Step 2: Add `font-hero` to tailwind.config.ts**

In `frontend/tailwind.config.ts`, inside `theme.extend`, add to `fontFamily`:

```ts
fontFamily: {
  sans: ["Inter", "system-ui", "sans-serif"],
  hero: ["var(--font-hero)", "Georgia", "serif"],
},
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/globals.css frontend/tailwind.config.ts
git commit -m "feat: add editorial token scope and onboarding animation classes to globals"
```

---

## Task 3: Make shadcn primitives token-aware

**Files:**
- Modify: `frontend/src/components/ui/button.tsx`
- Modify: `frontend/src/components/ui/input.tsx`
- Modify: `frontend/src/components/ui/card.tsx`

- [ ] **Step 1: Update button.tsx**

Replace the full content of `frontend/src/components/ui/button.tsx` with:

```tsx
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:     "bg-[var(--accent)] text-[var(--on-accent)] hover:bg-[var(--accent-hover)] shadow-sm",
        destructive: "bg-[var(--danger)] text-white hover:opacity-90",
        outline:     "border border-[var(--border)] bg-[var(--surface)] hover:bg-[var(--surface-2)] text-[var(--text)]",
        secondary:   "bg-[var(--surface-2)] text-[var(--text)] hover:bg-[var(--surface-3)]",
        ghost:       "hover:bg-[var(--surface-2)] text-[var(--text)]",
        link:        "text-[var(--accent)] underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm:      "h-9 rounded-md px-3",
        lg:      "h-11 rounded-md px-8",
        icon:    "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
  ),
);
Button.displayName = "Button";

export { Button, buttonVariants };
```

- [ ] **Step 2: Update input.tsx**

Replace the full content of `frontend/src/components/ui/input.tsx` with:

```tsx
import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        "flex h-10 w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)] placeholder:text-[var(--text-muted)]",
        "ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      ref={ref}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export { Input };
```

- [ ] **Step 3: Update card.tsx**

Replace the full content of `frontend/src/components/ui/card.tsx` with:

```tsx
import * as React from "react";
import { cn } from "@/lib/utils";

const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-sm", className)} {...props} />
  ),
);
Card.displayName = "Card";

const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col space-y-1.5 p-6", className)} {...props} />
  ),
);
CardHeader.displayName = "CardHeader";

const CardTitle = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3 ref={ref} className={cn("text-lg font-semibold leading-none tracking-tight text-[var(--text)]", className)} {...props} />
  ),
);
CardTitle.displayName = "CardTitle";

const CardDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p ref={ref} className={cn("text-sm text-[var(--text-dim)]", className)} {...props} />
  ),
);
CardDescription.displayName = "CardDescription";

const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
  ),
);
CardContent.displayName = "CardContent";

const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex items-center p-6 pt-0", className)} {...props} />
  ),
);
CardFooter.displayName = "CardFooter";

export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent };
```

- [ ] **Step 4: Run frontend unit tests to confirm no regression**

```bash
cd frontend && npm test -- --run
```
Expected: All 102 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/button.tsx frontend/src/components/ui/input.tsx frontend/src/components/ui/card.tsx
git commit -m "refactor: make shadcn button/input/card use CSS-variable tokens (theme-aware)"
```

---

## Task 4: Add `help` strings to locale YAMLs + extend backend + API types

**Files:**
- Modify: `locales/uk.yaml`, `locales/us.yaml`, `locales/de.yaml`, `locales/in.yaml`, `locales/_template.yaml`
- Modify: `backend/app/services/locale_service.py`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add `help` field to each legal_field in uk.yaml**

In `locales/uk.yaml`, add `help:` under each legal field:

```yaml
legal_fields:
  - id: "ir35_preference"
    label: "IR35 preference"
    help: "Determines whether roles are inside or outside IR35 — affects your take-home pay and which roles you'll see."
    type: "select"
    options:
      - value: "outside"
        label: "Outside IR35 (preferred)"
      - value: "inside"
        label: "Inside IR35"
      - value: "any"
        label: "Either / not specified"
    default: "any"
  - id: "right_to_work"
    label: "UK right to work"
    help: "UK employers must verify your right to work — this filters out roles that can't sponsor you."
    type: "select"
    options:
      - value: "citizen"
        label: "British citizen / settled status"
      - value: "visa"
        label: "Skilled Worker / other visa"
      - value: "requires_sponsorship"
        label: "Requires sponsorship"
    default: "citizen"
```

- [ ] **Step 2: Add `help` field to each legal_field in us.yaml**

```yaml
legal_fields:
  - id: "work_auth"
    label: "Work authorisation"
    help: "US employers typically cannot hire candidates who require sponsorship unless the role explicitly offers it — used to filter mismatches early."
    type: "select"
    options:
      - value: "us_citizen"
        label: "US Citizen"
      - value: "green_card"
        label: "Green Card / Permanent Resident"
      - value: "h1b"
        label: "H-1B (sponsored)"
      - value: "opt_cpt"
        label: "OPT / CPT"
      - value: "requires_sponsorship"
        label: "Requires sponsorship"
    default: "us_citizen"
  - id: "clearance"
    label: "Security clearance"
    help: "Many US federal and defence roles require a clearance — this avoids surfacing roles you're not eligible for."
    type: "select"
    options:
      - value: "none"
        label: "None"
      - value: "public_trust"
        label: "Public Trust"
      - value: "secret"
        label: "Secret"
      - value: "top_secret"
        label: "Top Secret / SCI"
    default: "none"
```

- [ ] **Step 3: Add `help` field to each legal_field in de.yaml**

```yaml
legal_fields:
  - id: "work_permit"
    label: "Work permit"
    help: "German employers must confirm your right to work in the EU — used to avoid surfacing roles you legally can't take."
    type: "select"
    options:
      - value: "eu_citizen"
        label: "EU / EEA citizen"
      - value: "blue_card"
        label: "EU Blue Card holder"
      - value: "work_permit"
        label: "German work permit"
      - value: "requires_sponsorship"
        label: "Requires visa sponsorship"
    default: "eu_citizen"
  - id: "language"
    label: "German language level"
    help: "Most German employers require at least B2 German even for tech roles — this filters jobs where language would block you."
    type: "select"
    options:
      - value: "native"
        label: "Native / C2"
      - value: "professional"
        label: "Professional / C1"
      - value: "conversational"
        label: "Conversational / B2"
      - value: "basic"
        label: "Basic / A2–B1"
      - value: "none"
        label: "None (English only)"
    default: "none"
```

- [ ] **Step 4: Add `help` field to each legal_field in in.yaml**

```yaml
legal_fields:
  - id: "notice_period"
    label: "Notice period"
    help: "Recruiters filter on availability — this is matched against job requirements during scoring."
    type: "select"
    options:
      - value: "immediate"
        label: "Immediate joiner"
      - value: "15_days"
        label: "15 days"
      - value: "30_days"
        label: "30 days"
      - value: "60_days"
        label: "60 days"
      - value: "90_days"
        label: "90 days"
    default: "30_days"
  - id: "work_preference"
    label: "Work preference"
    help: "Filters matches to the arrangement you actually want, avoiding roles that can't accommodate your preference."
    type: "select"
    options:
      - value: "remote"
        label: "Remote only"
      - value: "hybrid"
        label: "Hybrid"
      - value: "onsite"
        label: "On-site"
    default: "hybrid"
```

- [ ] **Step 5: Add `help` example to _template.yaml**

In `locales/_template.yaml`, add `help:` to the example legal field:

```yaml
legal_fields:
  - id: "work_auth"
    label: "Work authorisation"
    help: "Describes why this field matters and how it affects job matching."
    type: "select"
    options:
      - value: "citizen"
        label: "Citizen / Permanent resident"
      - value: "visa_required"
        label: "Requires visa sponsorship"
    default: "citizen"
```

- [ ] **Step 6: Extend `list_locales()` in locale_service.py to include currency fields**

In `backend/app/services/locale_service.py`, replace the `list_locales()` function:

```python
def list_locales() -> list[dict[str, Any]]:
    """Return a summary list of all available locales (id, name, flag, currency, default_rate_type)."""
    return [
        {
            "id": pack["id"],
            "name": pack["name"],
            "flag": pack.get("flag", ""),
            "currency": pack.get("currency", ""),
            "currency_symbol": pack.get("currency_symbol", ""),
            "default_rate_type": pack.get("default_rate_type", "annual"),
        }
        for pack in _load_all().values()
    ]
```

- [ ] **Step 7: Extend TypeScript types in api.ts**

In `frontend/src/lib/api.ts`, replace the `LocaleSummary` and `LocaleLegalField` interfaces:

```ts
export interface LocaleSummary {
  id: string;
  name: string;
  flag: string;
  currency: string;
  currency_symbol: string;
  default_rate_type: string;
}

export interface LocaleLegalField {
  id: string;
  label: string;
  help?: string;
  type: "select" | "text";
  options?: Array<{ value: string; label: string }>;
  default: string;
}
```

- [ ] **Step 8: Run backend tests**

```bash
python -m pytest backend/tests/ -q --tb=short -k "locale"
```
Expected: All locale tests pass.

- [ ] **Step 9: Commit**

```bash
git add locales/ backend/app/services/locale_service.py frontend/src/lib/api.ts
git commit -m "feat: add help strings to locale legal fields, expose currency in locale list"
```

---

## Task 5: Create OnboardingPrimitives.tsx

**Files:**
- Create: `frontend/src/components/onboarding/OnboardingPrimitives.tsx`
- Create: `frontend/src/__tests__/components/OnboardingPrimitives.test.tsx`

- [ ] **Step 1: Write the failing tests first**

Create `frontend/src/__tests__/components/OnboardingPrimitives.test.tsx`:

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Field, Help, Why, TagInput, Choice, Seg, ToggleRow, ChipInfo } from "@/components/onboarding/OnboardingPrimitives";

describe("Field", () => {
  it("renders label and children", () => {
    render(<Field label="Test label"><input data-testid="child" /></Field>);
    expect(screen.getByText("Test label")).toBeTruthy();
    expect(screen.getByTestId("child")).toBeTruthy();
  });

  it("shows required asterisk when req=true", () => {
    render(<Field label="Name" req><input /></Field>);
    expect(screen.getByText("*")).toBeTruthy();
  });

  it("shows Optional badge when optional=true", () => {
    render(<Field label="Summary" optional><input /></Field>);
    expect(screen.getByText("Optional")).toBeTruthy();
  });

  it("renders hint text", () => {
    render(<Field label="Field" hint="Helper text here"><input /></Field>);
    expect(screen.getByText("Helper text here")).toBeTruthy();
  });
});

describe("Help", () => {
  it("renders helper text", () => {
    render(<Help>Some hint</Help>);
    expect(screen.getByText("Some hint")).toBeTruthy();
  });
});

describe("Why", () => {
  it("renders callout text", () => {
    render(<Why>Why we ask this.</Why>);
    expect(screen.getByText("Why we ask this.")).toBeTruthy();
  });
});

describe("TagInput", () => {
  it("renders existing tags", () => {
    const onChange = vi.fn();
    render(<TagInput tags={["React", "TypeScript"]} onChange={onChange} placeholder="Add skill" />);
    expect(screen.getByText("React")).toBeTruthy();
    expect(screen.getByText("TypeScript")).toBeTruthy();
  });

  it("adds a tag on Enter", () => {
    const onChange = vi.fn();
    render(<TagInput tags={[]} onChange={onChange} placeholder="Add skill" />);
    const input = screen.getByPlaceholderText("Add skill");
    fireEvent.change(input, { target: { value: "Python" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith(["Python"]);
  });

  it("removes a tag when × clicked", () => {
    const onChange = vi.fn();
    render(<TagInput tags={["React"]} onChange={onChange} placeholder="Add" />);
    fireEvent.click(screen.getByLabelText("Remove React"));
    expect(onChange).toHaveBeenCalledWith([]);
  });
});

describe("Choice", () => {
  it("shows selected state", () => {
    render(<Choice on title="Option A" onClick={() => {}} />);
    const btn = screen.getByRole("button");
    expect(btn.className).toContain("on");
  });

  it("calls onClick", () => {
    const onClick = vi.fn();
    render(<Choice on={false} title="Option B" onClick={onClick} />);
    fireEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalled();
  });
});

describe("Seg", () => {
  it("marks the active segment", () => {
    render(
      <Seg value="b" onChange={() => {}} options={[{ v: "a", l: "A" }, { v: "b", l: "B" }]} />
    );
    const bBtn = screen.getByText("B").closest("button")!;
    expect(bBtn.className).toContain("on");
  });

  it("calls onChange when non-active segment clicked", () => {
    const onChange = vi.fn();
    render(
      <Seg value="b" onChange={onChange} options={[{ v: "a", l: "A" }, { v: "b", l: "B" }]} />
    );
    fireEvent.click(screen.getByText("A"));
    expect(onChange).toHaveBeenCalledWith("a");
  });
});

describe("ToggleRow", () => {
  it("renders title and sub", () => {
    render(<ToggleRow on title="Reed" sub="Active" onToggle={() => {}} />);
    expect(screen.getByText("Reed")).toBeTruthy();
    expect(screen.getByText("Active")).toBeTruthy();
  });

  it("calls onToggle", () => {
    const onToggle = vi.fn();
    render(<ToggleRow on={false} title="LinkedIn" onToggle={onToggle} />);
    fireEvent.click(screen.getByRole("switch"));
    expect(onToggle).toHaveBeenCalled();
  });
});

describe("ChipInfo", () => {
  it("renders label", () => {
    render(<ChipInfo>GBP · daily</ChipInfo>);
    expect(screen.getByText("GBP · daily")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run tests to confirm they fail (primitives don't exist yet)**

```bash
cd frontend && npm test -- --run src/__tests__/components/OnboardingPrimitives.test.tsx
```
Expected: Fail — module not found.

- [ ] **Step 3: Create OnboardingPrimitives.tsx**

Create `frontend/src/components/onboarding/OnboardingPrimitives.tsx`:

```tsx
"use client";

import { useState } from "react";
import { Info, Check } from "lucide-react";

/* ─── Field ─────────────────────────────────────────────────────────────── */
interface FieldProps {
  label?: string;
  req?: boolean;
  optional?: boolean;
  hint?: string;
  hintTone?: "err" | "ok" | "";
  children: React.ReactNode;
}

export function Field({ label, req, optional, hint, hintTone = "", children }: FieldProps) {
  return (
    <div className="mb-4">
      {label && (
        <div className="flex items-center gap-1.5 mb-1.5 text-[13px] font-[550] text-[var(--text)]">
          {label}
          {req && <span className="text-[var(--accent)]">*</span>}
          {optional && (
            <span className="ml-auto text-[11px] font-[500] text-[var(--text-muted)]">Optional</span>
          )}
        </div>
      )}
      {children}
      {hint && <Help tone={hintTone}>{hint}</Help>}
    </div>
  );
}

/* ─── Help ──────────────────────────────────────────────────────────────── */
interface HelpProps {
  children: React.ReactNode;
  tone?: "err" | "ok" | "";
}

export function Help({ children, tone = "" }: HelpProps) {
  const colorClass =
    tone === "err" ? "text-[var(--danger)]" :
    tone === "ok"  ? "text-[var(--success)]" :
    "text-[var(--text-muted)]";
  const Icon = tone === "ok" ? Check : Info;
  return (
    <div className={`flex gap-1.5 mt-1.5 text-[12px] leading-[1.45] ${colorClass}`}>
      <Icon size={13} className="flex-shrink-0 mt-[1px] opacity-80" />
      <span>{children}</span>
    </div>
  );
}

/* ─── Why callout ───────────────────────────────────────────────────────── */
export function Why({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2.5 p-[11px_13px] mb-4 rounded-[var(--r-card,10px)] text-[12.5px] leading-[1.5] text-[var(--text-dim)]"
      style={{ background: "var(--accent-soft)", border: "1px solid var(--accent-soft-strong)" }}>
      <Info size={15} className="flex-shrink-0 mt-[1px] text-[var(--accent)]" />
      <span>{children}</span>
    </div>
  );
}

/* ─── TagInput ──────────────────────────────────────────────────────────── */
interface TagInputProps {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
  suggestions?: string[];
  invalid?: boolean;
}

export function TagInput({ tags, onChange, placeholder, suggestions = [], invalid }: TagInputProps) {
  const [input, setInput] = useState("");
  const add = (t: string) => {
    const v = t.trim();
    if (v && !tags.includes(v)) onChange([...tags, v]);
    setInput("");
  };
  const remove = (i: number) => onChange(tags.filter((_, idx) => idx !== i));
  const avail = suggestions.filter((s) => !tags.includes(s));

  return (
    <div>
      <div
        className={`flex flex-wrap gap-1.5 p-2 min-h-[44px] rounded-[var(--r-field,8px)] transition-[border-color,box-shadow] ${
          invalid
            ? "border border-[var(--danger)]"
            : "border border-[var(--border)] focus-within:border-[var(--accent)] focus-within:shadow-[0_0_0_3px_var(--accent-soft)]"
        }`}
        style={{ background: "var(--surface-2)" }}
      >
        {tags.map((t, i) => (
          <span
            key={t}
            className="inline-flex items-center gap-1.5 px-2 py-1 rounded-[var(--r-chip,6px)] text-[12.5px] font-[550] text-[var(--text)]"
            style={{ background: "var(--accent-soft)" }}
          >
            {t}
            <button
              type="button"
              aria-label={`Remove ${t}`}
              onClick={() => remove(i)}
              className="opacity-65 hover:opacity-100 text-[14px] leading-none"
            >
              ×
            </button>
          </span>
        ))}
        <input
          className="flex-1 min-w-[100px] bg-transparent border-0 outline-none text-[14px] text-[var(--text)] placeholder:text-[var(--text-muted)] px-1 py-1"
          value={input}
          placeholder={tags.length ? "" : placeholder}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if ((e.key === "Enter" || e.key === ",") && input.trim()) {
              e.preventDefault();
              add(input);
            }
            if (e.key === "Backspace" && !input && tags.length) remove(tags.length - 1);
          }}
        />
      </div>
      {avail.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {avail.slice(0, 5).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => add(s)}
              className="text-[12px] font-[500] text-[var(--text-dim)] px-2.5 py-1 rounded-[var(--r-chip,6px)] border border-dashed border-[var(--border-strong)] hover:text-[var(--text)] hover:border-[var(--accent)] hover:border-solid transition-all"
              style={{ background: "var(--surface)" }}
            >
              + {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Choice card ───────────────────────────────────────────────────────── */
interface ChoiceProps {
  on: boolean;
  onClick: () => void;
  flag?: string;
  title: string;
  sub?: string;
}

export function Choice({ on, onClick, flag, title, sub }: ChoiceProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`choice flex items-center gap-2.5 text-left px-3 py-3 rounded-[var(--r-card,10px)] border transition-all font-inherit w-full cursor-pointer ${
        on
          ? "border-[var(--accent)] text-[var(--text)]"
          : "border-[var(--border)] text-[var(--text)] hover:border-[var(--border-strong)]"
      }`}
      style={{
        background: on ? "var(--accent-soft)" : "var(--surface)",
      }}
    >
      {flag && <span className="text-[22px] leading-none flex-shrink-0">{flag}</span>}
      <span className="flex flex-col gap-0.5 flex-1 min-w-0">
        <span className="block text-[14px] font-[600]">{title}</span>
        {sub && <span className="block text-[11.5px] text-[var(--text-muted)]">{sub}</span>}
      </span>
      <span className={`w-[18px] h-[18px] flex-shrink-0 text-[var(--accent)] transition-opacity ${on ? "opacity-100" : "opacity-0"}`}>
        <Check size={16} strokeWidth={2.4} />
      </span>
    </button>
  );
}

/* ─── Segmented control ─────────────────────────────────────────────────── */
interface SegOption { v: string; l: string; }

interface SegProps {
  value: string;
  onChange: (v: string) => void;
  options: SegOption[];
}

export function Seg({ value, onChange, options }: SegProps) {
  return (
    <div
      className="flex gap-1 p-1 rounded-[var(--r-field,8px)] border border-[var(--border)]"
      style={{ background: "var(--surface-2)" }}
    >
      {options.map((o) => (
        <button
          key={o.v}
          type="button"
          onClick={() => onChange(o.v)}
          className={`flex-1 text-[12.5px] font-[550] px-2 py-2 rounded-[calc(var(--r-field,8px)-4px)] transition-all whitespace-nowrap ${
            value === o.v
              ? "on text-[var(--text)] shadow-[0_1px_3px_rgba(0,0,0,.3)]"
              : "text-[var(--text-muted)] hover:text-[var(--text)]"
          }`}
          style={value === o.v ? { background: "var(--bg-elevated, var(--bg-elev, var(--bg)))" } : { background: "transparent" }}
        >
          {o.l}
        </button>
      ))}
    </div>
  );
}

/* ─── ToggleRow ─────────────────────────────────────────────────────────── */
interface ToggleRowProps {
  on: boolean;
  onToggle: () => void;
  title: string;
  sub?: string;
}

export function ToggleRow({ on, onToggle, title, sub }: ToggleRowProps) {
  return (
    <div
      className="flex items-center gap-3 px-3 py-3 rounded-[var(--r-card,10px)] border border-[var(--border)] mb-2"
      style={{ background: "var(--surface)" }}
    >
      <div className="flex-1 min-w-0">
        <div className="text-[13.5px] font-[550] text-[var(--text)]">{title}</div>
        {sub && <div className="text-[11.5px] text-[var(--text-muted)] mt-0.5">{sub}</div>}
      </div>
      <button
        type="button"
        role="switch"
        aria-pressed={on}
        onClick={onToggle}
        className={`relative w-10 h-6 rounded-full border-0 flex-shrink-0 cursor-pointer transition-colors ${
          on ? "bg-[var(--accent)]" : "bg-[var(--surface-3)]"
        }`}
      >
        <span
          className={`absolute top-[3px] w-[18px] h-[18px] rounded-full bg-white transition-transform ${
            on ? "left-[3px] translate-x-4" : "left-[3px]"
          }`}
        />
      </button>
    </div>
  );
}

/* ─── ChipInfo — read-only info chip ────────────────────────────────────── */
export function ChipInfo({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-[var(--r-field,8px)] border border-[var(--border)] text-[13px] font-[600] text-[var(--text)]"
      style={{ background: "var(--surface-2)" }}
    >
      {children}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd frontend && npm test -- --run src/__tests__/components/OnboardingPrimitives.test.tsx
```
Expected: All 14 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/onboarding/OnboardingPrimitives.tsx frontend/src/__tests__/components/OnboardingPrimitives.test.tsx
git commit -m "feat: add OnboardingPrimitives (Field, Help, Why, TagInput, Choice, Seg, ToggleRow, ChipInfo)"
```

---

## Task 6: Rewrite OnboardingProgress.tsx (numeral style, 6 steps)

**Files:**
- Modify: `frontend/src/components/onboarding/OnboardingProgress.tsx`

- [ ] **Step 1: Replace OnboardingProgress.tsx**

```tsx
"use client";

const STEP_LABELS = [
  "About you",
  "Your market",
  "Location & pay",
  "Eligibility",
  "Skills",
  "AI & launch",
];

interface OnboardingProgressProps {
  formStep: number;  // 1–6; 0 on Welcome/Success (no progress shown)
}

export function OnboardingProgress({ formStep }: OnboardingProgressProps) {
  if (formStep === 0) return null;

  const label = STEP_LABELS[formStep - 1] ?? "";

  return (
    <div
      className="flex items-baseline gap-2 px-5 pt-3.5 pb-1.5"
      role="progressbar"
      aria-valuenow={formStep}
      aria-valuemax={6}
      aria-label={`Step ${formStep} of 6: ${label}`}
    >
      <span
        className="text-[40px] leading-[0.9] font-[500] tracking-[-0.015em] text-[var(--text)]"
        style={{ fontFamily: "var(--font-hero, 'Newsreader', Georgia, serif)" }}
      >
        {String(formStep).padStart(2, "0")}
      </span>
      <span className="text-[15px] text-[var(--text-muted)]">/ 06</span>
      <span className="ml-auto text-[12px] text-[var(--text-dim)] uppercase tracking-[0.08em]">
        {label}
      </span>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/onboarding/OnboardingProgress.tsx
git commit -m "feat: rewrite OnboardingProgress to numeral style (01/06 + step name)"
```

---

## Task 7: Create ScreenWelcome.tsx

**Files:**
- Create: `frontend/src/components/onboarding/ScreenWelcome.tsx`

- [ ] **Step 1: Create ScreenWelcome.tsx**

```tsx
"use client";

import { Search, Scale, FileText, Kanban, MessageSquare, ShieldCheck, Check } from "lucide-react";

const VALUE_STEPS = [
  { Icon: Search,       title: "Discover",  sub: "Scans your job boards every few hours" },
  { Icon: Scale,        title: "Score",     sub: "Ranks each role against your profile" },
  { Icon: FileText,     title: "Tailor",    sub: "Drafts a tuned CV + cover letter" },
  { Icon: Kanban,       title: "Track",     sub: "You approve — it never applies on its own" },
  { Icon: MessageSquare,title: "Coach",     sub: "Preps you when an interview lands" },
];

interface ScreenWelcomeProps {
  hasSaved: boolean;
  onStart: () => void;
}

export function ScreenWelcome({ hasSaved, onStart }: ScreenWelcomeProps) {
  return (
    <div className="ob-fadein flex flex-col min-h-full px-5 pt-6 pb-2">
      {/* Hero mark */}
      <div
        className="w-14 h-14 rounded-[16px] grid place-items-center font-[800] text-[28px] text-white mb-5 shadow-[0_10px_30px_-8px_var(--accent-soft-strong)]"
        style={{ background: "linear-gradient(135deg, var(--accent), var(--success))" }}
      >
        H
      </div>

      <p className="text-[11px] font-[600] tracking-[0.1em] uppercase text-[var(--text-dim)] mb-2.5">
        Welcome to Hatch
      </p>

      <h1
        className="text-[31px] font-[500] leading-[1.16] tracking-[-0.015em] text-[var(--text)] mb-3"
        style={{ fontFamily: "var(--font-hero, 'Newsreader', Georgia, serif)" }}
      >
        Your job search,<br />on autopilot.
      </h1>

      <p className="text-[14px] leading-[1.5] text-[var(--text-dim)] mb-5">
        Hatch finds, scores and tailors applications for roles that fit you — then hands you the
        decisions that matter. You stay in control; it never applies on its own. Setup takes about
        3 minutes.
      </p>

      {/* Pipeline */}
      <div className="flex flex-col gap-0.5 mb-5">
        {VALUE_STEPS.map(({ Icon, title, sub }, i) => (
          <div key={title}>
            <div className="flex gap-3 py-2">
              <div
                className="w-[30px] h-[30px] rounded-[9px] flex-shrink-0 grid place-items-center text-[var(--accent)]"
                style={{ background: "var(--surface-2)" }}
              >
                <Icon size={16} />
              </div>
              <span className="flex flex-col">
                <span className="text-[13.5px] font-[600] text-[var(--text)]">{title}</span>
                <span className="text-[12px] text-[var(--text-muted)] mt-0.5 leading-[1.4]">{sub}</span>
              </span>
            </div>
            {i < VALUE_STEPS.length - 1 && (
              <div className="w-px ml-[14px] h-1.5" style={{ background: "var(--border)" }} />
            )}
          </div>
        ))}
      </div>

      {/* Trust chips */}
      <div className="flex flex-wrap gap-2 mb-6">
        <span className="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--text-dim)] px-2.5 py-1.5 rounded-full border border-[var(--border)]"
          style={{ background: "var(--surface)" }}>
          <ShieldCheck size={13} className="text-[var(--success)]" />
          Self-hosted — data stays on your machine
        </span>
        <span className="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--text-dim)] px-2.5 py-1.5 rounded-full border border-[var(--border)]"
          style={{ background: "var(--surface)" }}>
          <Check size={13} className="text-[var(--success)]" />
          Never auto-applies
        </span>
      </div>

      {/* CTA */}
      <button
        type="button"
        onClick={onStart}
        className="w-full py-3 rounded-[var(--r-btn,8px)] text-[14px] font-[600] text-[var(--on-accent)] flex items-center justify-center gap-2 transition-colors"
        style={{ background: "var(--accent)" }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--accent-hover)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "var(--accent)")}
      >
        {hasSaved ? "Resume setup" : "Get started"} →
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/onboarding/ScreenWelcome.tsx
git commit -m "feat: add ScreenWelcome with value pipeline and trust chips"
```

---

## Task 8: Create ScreenSuccess.tsx

**Files:**
- Create: `frontend/src/components/onboarding/ScreenSuccess.tsx`

- [ ] **Step 1: Create ScreenSuccess.tsx**

```tsx
"use client";

import { Check } from "lucide-react";
import type { CandidateData } from "./StepAboutYou";
import type { LocaleSummary } from "@/lib/api";

interface ScreenSuccessProps {
  candidate: CandidateData;
  selectedLocale: string;
  locales: LocaleSummary[];
  targetRolesCount: number;
  minRate: number;
  providerName: string;
  enabledBoardsCount: number;
  onDashboard: () => void;
}

export function ScreenSuccess({
  candidate, selectedLocale, locales, targetRolesCount,
  minRate, providerName, enabledBoardsCount, onDashboard,
}: ScreenSuccessProps) {
  const locale = locales.find((l) => l.id === selectedLocale);
  const localeName = locale?.name ?? selectedLocale;
  const localeFlag = locale?.flag ?? "";
  const currency = locale?.currency ?? "";
  const rateType = locale?.default_rate_type ?? "annual";

  return (
    <div className="ob-fadein flex flex-col min-h-full px-5 pt-6 pb-2">
      {/* Pulsing check */}
      <div className="flex flex-col items-center text-center mb-6">
        <div
          className="w-[72px] h-[72px] rounded-full grid place-items-center mb-5 ob-pulse"
          style={{ background: "var(--success-soft)", color: "var(--success)" }}
        >
          <Check size={34} strokeWidth={2.4} />
        </div>

        <h1
          className="text-[31px] font-[500] leading-[1.16] tracking-[-0.015em] text-[var(--text)] mb-2"
          style={{ fontFamily: "var(--font-hero, 'Newsreader', Georgia, serif)" }}
        >
          Your search is hatching.
        </h1>

        <p className="text-[14px] leading-[1.5] text-[var(--text-dim)] mb-4">
          Scout is scanning {enabledBoardsCount} {localeName} board{enabledBoardsCount !== 1 ? "s" : ""} right now.
          Matches will land in your inbox — you approve before anything goes out.
        </p>

        {/* Live indicator */}
        <span className="inline-flex items-center gap-1.5 text-[12px] text-[var(--success)] px-3 py-1.5 rounded-full"
          style={{ background: "var(--success-soft)" }}>
          <span className="w-[7px] h-[7px] rounded-full ob-blink" style={{ background: "var(--success)" }} />
          Scout agent running
        </span>
      </div>

      {/* Summary */}
      <div
        className="border border-[var(--border)] rounded-[var(--r-card,10px)] overflow-hidden mb-6"
      >
        {[
          { k: "Profile",  v: `${candidate.name || "—"} · ${candidate.title || "—"}` },
          { k: "Market",   v: `${localeFlag} ${localeName} · ${targetRolesCount} title${targetRolesCount !== 1 ? "s" : ""}` },
          { k: "Pay",      v: minRate ? `${currency} ${minRate}+ ${rateType}` : "—" },
          { k: "Engine",   v: providerName },
        ].map(({ k, v }) => (
          <div key={k} className="flex items-start gap-3 px-3.5 py-3 border-b border-[var(--border)] last:border-b-0">
            <span className="text-[12px] text-[var(--text-muted)] w-[88px] flex-shrink-0 pt-px">{k}</span>
            <span className="text-[13px] font-[500] text-[var(--text)] flex-1">{v}</span>
          </div>
        ))}
      </div>

      {/* CTA */}
      <button
        type="button"
        onClick={onDashboard}
        className="w-full py-3 rounded-[var(--r-btn,8px)] text-[14px] font-[600] text-[var(--on-accent)] flex items-center justify-center gap-2 transition-colors"
        style={{ background: "var(--accent)" }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--accent-hover)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "var(--accent)")}
      >
        Go to dashboard →
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/onboarding/ScreenSuccess.tsx
git commit -m "feat: add ScreenSuccess with pulsing check, live scout indicator, and summary"
```

---

## Task 9: Create StepMarket.tsx

**Files:**
- Create: `frontend/src/components/onboarding/StepMarket.tsx`

- [ ] **Step 1: Create StepMarket.tsx**

```tsx
"use client";

import type { LocaleSummary } from "@/lib/api";
import { Field, Why, TagInput, Choice, Seg } from "./OnboardingPrimitives";
import type { SearchData } from "./StepJobSearch";

interface StepMarketProps {
  selectedLocale: string;
  locales: LocaleSummary[];
  loadingLocales: boolean;
  onLocaleChange: (locale: string) => void;
  search: SearchData;
  onSearchChange: (search: SearchData) => void;
  tried: boolean;
}

const ROLE_SUGGESTIONS = [
  "Delivery Lead", "Programme Manager", "Scrum Master",
  "Agile Coach", "Project Manager",
];

export function StepMarket({
  selectedLocale, locales, loadingLocales, onLocaleChange,
  search, onSearchChange, tried,
}: StepMarketProps) {
  return (
    <div className="ob-fadein px-5 pb-4">
      <p className="text-[11px] font-[600] tracking-[0.1em] uppercase text-[var(--text-dim)] mb-2">
        Step 2 · Your market
      </p>
      <h1
        className="text-[31px] font-[500] leading-[1.16] tracking-[-0.015em] text-[var(--text)] mb-3"
        style={{ fontFamily: "var(--font-hero, 'Newsreader', Georgia, serif)" }}
      >
        Where are you looking?
      </h1>

      <Why>
        <b>Your market sets your boards.</b> It controls which job sites Hatch scrapes and which
        local compliance details we'll ask for next.
      </Why>

      <Field label="Job market" req>
        {loadingLocales ? (
          <p className="text-sm text-[var(--text-muted)] py-2">Loading markets…</p>
        ) : (
          <div className="grid grid-cols-2 gap-2.5">
            {locales.map((l) => (
              <Choice
                key={l.id}
                on={selectedLocale === l.id}
                onClick={() => onLocaleChange(l.id)}
                flag={l.flag}
                title={l.name}
              />
            ))}
          </div>
        )}
      </Field>

      <Field
        label="Target job titles"
        req
        hint={
          tried && search.target_roles.length === 0
            ? "Add at least one target job title."
            : search.target_roles.length
            ? "Add a few variations — more titles, more matches."
            : "Press Enter to add each title. Tap a suggestion to start."
        }
        hintTone={tried && search.target_roles.length === 0 ? "err" : ""}
      >
        <TagInput
          tags={search.target_roles}
          onChange={(roles) => onSearchChange({ ...search, target_roles: roles })}
          placeholder="Delivery Lead"
          suggestions={ROLE_SUGGESTIONS}
          invalid={tried && search.target_roles.length === 0}
        />
      </Field>

      <Field label="Employment type" hint="Filters matches to the kind of work you actually want.">
        <Seg
          value={search.contract_type}
          onChange={(v) => onSearchChange({ ...search, contract_type: v })}
          options={[
            { v: "contract",  l: "Contract"  },
            { v: "permanent", l: "Permanent" },
            { v: "any",       l: "Either"    },
          ]}
        />
      </Field>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/onboarding/StepMarket.tsx
git commit -m "feat: add StepMarket (locale cards, target roles, employment type)"
```

---

## Task 10: Create StepPay.tsx

**Files:**
- Create: `frontend/src/components/onboarding/StepPay.tsx`

- [ ] **Step 1: Create StepPay.tsx**

```tsx
"use client";

import { Field, Help, Seg, ChipInfo } from "./OnboardingPrimitives";
import { Input } from "@/components/ui/input";
import type { LocationData, CompensationData } from "./StepJobSearch";
import type { LocaleSummary } from "@/lib/api";

interface StepPayProps {
  locale: LocaleSummary | undefined;
  locations: LocationData[];
  onLocationsChange: (locations: LocationData[]) => void;
  compensation: CompensationData;
  onCompensationChange: (compensation: CompensationData) => void;
  tried: boolean;
}

export function StepPay({
  locale, locations, onLocationsChange, compensation, onCompensationChange, tried,
}: StepPayProps) {
  const loc = locations[0];
  const currency = locale?.currency ?? compensation.currency;
  const rateType = locale?.default_rate_type ?? compensation.rate_type;

  return (
    <div className="ob-fadein px-5 pb-4">
      <p className="text-[11px] font-[600] tracking-[0.1em] uppercase text-[var(--text-dim)] mb-2">
        Step 3 · Location &amp; pay
      </p>
      <h1
        className="text-[31px] font-[500] leading-[1.16] tracking-[-0.015em] text-[var(--text)] mb-3"
        style={{ fontFamily: "var(--font-hero, 'Newsreader', Georgia, serif)" }}
      >
        What are you worth, and where?
      </h1>
      <p className="text-[14px] leading-[1.5] text-[var(--text-dim)] mb-4">
        Pay weighs into every match score — be realistic and Hatch surfaces better-fitting roles.
      </p>

      <div className="grid grid-cols-2 gap-3">
        <Field
          label="City"
          req
          hint={tried && !loc.city.trim() ? "City is required." : undefined}
          hintTone={tried && !loc.city.trim() ? "err" : ""}
        >
          <Input
            value={loc.city}
            onChange={(e) => onLocationsChange([{ ...loc, city: e.target.value }])}
            placeholder="London"
            className={tried && !loc.city.trim() ? "border-[var(--danger)]" : ""}
          />
        </Field>

        <Field label="Remote preference">
          <Seg
            value={loc.remote_preference}
            onChange={(v) => onLocationsChange([{ ...loc, remote_preference: v }])}
            options={[
              { v: "remote", l: "Remote"  },
              { v: "hybrid", l: "Hybrid"  },
              { v: "onsite", l: "On-site" },
            ]}
          />
        </Field>
      </div>

      <Field
        label={`Expected rate (${currency})`}
        req
        hint={`Set by your ${locale?.name ?? ""} market — rates are ${rateType}. Leave max blank if you're flexible.`}
        hintTone={tried && compensation.min_rate <= 0 ? "err" : ""}
      >
        <div className="grid grid-cols-3 gap-2.5">
          <Input
            type="number"
            value={compensation.min_rate || ""}
            onChange={(e) => onCompensationChange({ ...compensation, min_rate: parseFloat(e.target.value) || 0 })}
            placeholder="Min"
            className={tried && compensation.min_rate <= 0 ? "border-[var(--danger)]" : ""}
          />
          <Input
            type="number"
            value={compensation.max_rate || ""}
            onChange={(e) => onCompensationChange({ ...compensation, max_rate: parseFloat(e.target.value) || 0 })}
            placeholder="Max"
          />
          <ChipInfo>{currency} · {rateType}</ChipInfo>
        </div>
        {tried && compensation.min_rate <= 0 && (
          <Help tone="err">Minimum rate is required.</Help>
        )}
      </Field>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/onboarding/StepPay.tsx
git commit -m "feat: add StepPay (city, remote preference, rate with locale-derived currency chip)"
```

---

## Task 11: Create StepEligibility.tsx

**Files:**
- Create: `frontend/src/components/onboarding/StepEligibility.tsx`

- [ ] **Step 1: Create StepEligibility.tsx**

```tsx
"use client";

import type { LocaleLegalField, LocaleSummary } from "@/lib/api";
import { Field, Why, Choice } from "./OnboardingPrimitives";
import type { CompensationData } from "./StepJobSearch";

interface StepEligibilityProps {
  locale: LocaleSummary | undefined;
  legalFields: LocaleLegalField[];
  compensation: CompensationData;
  onCompensationChange: (compensation: CompensationData) => void;
}

export function StepEligibility({
  locale, legalFields, compensation, onCompensationChange,
}: StepEligibilityProps) {
  if (legalFields.length === 0) {
    return (
      <div className="ob-fadein px-5 pb-4">
        <p className="text-[11px] font-[600] tracking-[0.1em] uppercase text-[var(--text-dim)] mb-2">
          Step 4 · Eligibility
        </p>
        <h1
          className="text-[31px] font-[500] leading-[1.16] tracking-[-0.015em] text-[var(--text)] mb-3"
          style={{ fontFamily: "var(--font-hero, 'Newsreader', Georgia, serif)" }}
        >
          No eligibility questions for this market.
        </h1>
        <p className="text-sm text-[var(--text-dim)]">Continue to the next step.</p>
      </div>
    );
  }

  return (
    <div className="ob-fadein px-5 pb-4">
      <p className="text-[11px] font-[600] tracking-[0.1em] uppercase text-[var(--text-dim)] mb-2">
        Step 4 · Eligibility
      </p>
      <h1
        className="text-[31px] font-[500] leading-[1.16] tracking-[-0.015em] text-[var(--text)] mb-3"
        style={{ fontFamily: "var(--font-hero, 'Newsreader', Georgia, serif)" }}
      >
        A couple of {locale?.name ?? ""} specifics.
      </h1>

      <Why>
        <b>These are hard filters.</b>{" "}
        {locale?.flag} {locale?.name} employers screen on them first, so Hatch uses them to avoid
        wasting your time on roles you can't take.
      </Why>

      {legalFields.map((field) => (
        <Field
          key={field.id}
          label={field.label}
          hint={field.help}
        >
          {field.type === "select" && field.options ? (
            <div className="grid grid-cols-1 gap-2">
              {field.options.map((opt) => (
                <Choice
                  key={opt.value}
                  on={(compensation.legal_preferences[field.id] ?? field.default) === opt.value}
                  title={opt.label}
                  onClick={() =>
                    onCompensationChange({
                      ...compensation,
                      legal_preferences: { ...compensation.legal_preferences, [field.id]: opt.value },
                    })
                  }
                />
              ))}
            </div>
          ) : (
            <input
              className="flex h-10 w-full rounded-[var(--r-field,8px)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
              value={compensation.legal_preferences[field.id] ?? ""}
              onChange={(e) =>
                onCompensationChange({
                  ...compensation,
                  legal_preferences: { ...compensation.legal_preferences, [field.id]: e.target.value },
                })
              }
            />
          )}
        </Field>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/onboarding/StepEligibility.tsx
git commit -m "feat: add StepEligibility with Why callout, locale legal fields as Choice cards"
```

---

## Task 12: Update StepAboutYou.tsx (helper text, Editorial style)

**Files:**
- Modify: `frontend/src/components/onboarding/StepAboutYou.tsx`

- [ ] **Step 1: Replace StepAboutYou.tsx**

```tsx
"use client";

import { Input } from "@/components/ui/input";
import { Field } from "./OnboardingPrimitives";

export interface CandidateData {
  name: string;
  title: string;
  years_experience: number;
  summary: string;
}

interface StepAboutYouProps {
  candidate: CandidateData;
  onChange: (candidate: CandidateData) => void;
  tried: boolean;
}

export function StepAboutYou({ candidate, onChange, tried }: StepAboutYouProps) {
  return (
    <div className="ob-fadein px-5 pb-4">
      <p className="text-[11px] font-[600] tracking-[0.1em] uppercase text-[var(--text-dim)] mb-2">
        Step 1 · About you
      </p>
      <h1
        className="text-[31px] font-[500] leading-[1.16] tracking-[-0.015em] text-[var(--text)] mb-3"
        style={{ fontFamily: "var(--font-hero, 'Newsreader', Georgia, serif)" }}
      >
        Who are we writing for?
      </h1>
      <p className="text-[14px] leading-[1.5] text-[var(--text-dim)] mb-4">
        These details go straight into your tailored CVs and cover letters.
      </p>

      <div className="grid grid-cols-1 gap-0 sm:grid-cols-2 sm:gap-3">
        <Field
          label="Full name"
          req
          hint={tried && !candidate.name.trim() ? "Name is required." : "As it should appear on your CV."}
          hintTone={tried && !candidate.name.trim() ? "err" : ""}
        >
          <Input
            id="name"
            value={candidate.name}
            onChange={(e) => onChange({ ...candidate, name: e.target.value })}
            placeholder="Arvind Soni"
            className={tried && !candidate.name.trim() ? "border-[var(--danger)]" : ""}
          />
        </Field>

        <Field
          label="Current or target title"
          req
          hint={tried && !candidate.title.trim() ? "Title is required." : "The role you're aiming for — Hatch matches and writes toward this."}
          hintTone={tried && !candidate.title.trim() ? "err" : ""}
        >
          <Input
            id="title"
            value={candidate.title}
            onChange={(e) => onChange({ ...candidate, title: e.target.value })}
            placeholder="Delivery Lead"
            className={tried && !candidate.title.trim() ? "border-[var(--danger)]" : ""}
          />
        </Field>
      </div>

      <Field label="Years of experience" hint="Used to calibrate how senior the matched roles are.">
        <Input
          id="years"
          type="number"
          min={0}
          value={candidate.years_experience || ""}
          onChange={(e) => onChange({ ...candidate, years_experience: parseInt(e.target.value) || 0 })}
          placeholder="12"
        />
      </Field>

      <Field label="Professional summary" optional hint="2–3 sentences in your voice. Hatch adapts — not copies — this per application.">
        <textarea
          id="summary"
          rows={3}
          value={candidate.summary}
          onChange={(e) => onChange({ ...candidate, summary: e.target.value })}
          placeholder="Senior delivery lead with 12 years running complex transformation programmes across financial services…"
          className="flex w-full rounded-[var(--r-field,8px)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] resize-none leading-[1.5]"
        />
      </Field>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/onboarding/StepAboutYou.tsx
git commit -m "feat: update StepAboutYou with editorial headings, per-field helper text, inline validation"
```

---

## Task 13: Update StepSkills.tsx

**Files:**
- Modify: `frontend/src/components/onboarding/StepSkills.tsx`

- [ ] **Step 1: Replace StepSkills.tsx**

```tsx
"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Field, TagInput } from "./OnboardingPrimitives";

export interface SkillsData {
  primary: string[];
  secondary: string[];
  certifications: string[];
}

export interface DomainsData {
  preferred: string[];
  excluded: string[];
}

export interface ProofPoint {
  id: string;
  summary: string;
  context: string;
  metrics: string;
  tags: string[];
}

const SKILL_SUGGESTIONS = ["Agile delivery", "Stakeholder management", "Budget ownership", "Risk management", "Roadmapping"];

interface StepSkillsProps {
  skills: SkillsData;
  onSkillsChange: (skills: SkillsData) => void;
  domains: DomainsData;
  onDomainsChange: (domains: DomainsData) => void;
  proofPoints: ProofPoint[];
  onProofPointsChange: (points: ProofPoint[]) => void;
}

function ProofPointForm({ point, index, onChange, onRemove }: {
  point: ProofPoint; index: number;
  onChange: (p: ProofPoint) => void; onRemove: () => void;
}) {
  const [tagInput, setTagInput] = useState("");
  return (
    <div
      className="rounded-[var(--r-card,10px)] p-4 space-y-3 border border-[var(--border)]"
      style={{ background: "var(--surface-2)" }}
    >
      <div className="flex items-center justify-between">
        <p className="text-sm font-[550] text-[var(--text)]">Achievement {index + 1}</p>
        <button type="button" onClick={onRemove} className="text-xs text-[var(--danger)] hover:underline">Remove</button>
      </div>
      <Field label="One-line summary" req hint="E.g. Led migration of 3 legacy systems to AWS, cutting infra costs 40%.">
        <Input value={point.summary} onChange={(e) => onChange({ ...point, summary: e.target.value })}
          placeholder="Led migration of 3 legacy systems to AWS, cutting infra costs 40%" />
      </Field>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Context (Situation / Task)" hint="The challenge you inherited or were set.">
          <textarea rows={2} value={point.context} onChange={(e) => onChange({ ...point, context: e.target.value })}
            placeholder="Inherited a fragile on-prem estate…"
            className="flex w-full rounded-[var(--r-field,8px)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] resize-none" />
        </Field>
        <Field label="Metrics / Result" hint="Concrete numbers make tailored CVs much stronger.">
          <textarea rows={2} value={point.metrics} onChange={(e) => onChange({ ...point, metrics: e.target.value })}
            placeholder="£1.2M annual saving, 99.9% uptime"
            className="flex w-full rounded-[var(--r-field,8px)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] resize-none" />
        </Field>
      </div>
      <div className="space-y-1">
        <label className="text-[13px] font-[550] text-[var(--text)]">Tags (skills demonstrated)</label>
        <div className="flex flex-wrap gap-1.5 p-2 border border-[var(--border)] rounded-[var(--r-field,8px)] min-h-[34px]"
          style={{ background: "var(--surface)" }}>
          {point.tags.map((t, i) => (
            <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-[550] rounded-[var(--r-chip,6px)] text-[var(--text)]"
              style={{ background: "var(--accent-soft)" }}>
              {t}
              <button type="button" onClick={() => onChange({ ...point, tags: point.tags.filter((_, j) => j !== i) })}
                className="opacity-65 hover:opacity-100">×</button>
            </span>
          ))}
          <input
            className="flex-1 min-w-[80px] outline-none text-xs bg-transparent text-[var(--text)] placeholder:text-[var(--text-muted)]"
            value={tagInput} placeholder="AWS, Cloud…"
            onChange={(e) => setTagInput(e.target.value)}
            onKeyDown={(e) => {
              if ((e.key === "Enter" || e.key === ",") && tagInput.trim()) {
                e.preventDefault();
                onChange({ ...point, tags: [...point.tags, tagInput.trim()] });
                setTagInput("");
              }
            }}
          />
        </div>
      </div>
    </div>
  );
}

export function StepSkills({ skills, onSkillsChange, domains, onDomainsChange, proofPoints, onProofPointsChange }: StepSkillsProps) {
  const addProofPoint = () => {
    onProofPointsChange([...proofPoints, { id: `pp_${Date.now()}`, summary: "", context: "", metrics: "", tags: [] }]);
  };

  return (
    <div className="ob-fadein px-5 pb-4">
      <p className="text-[11px] font-[600] tracking-[0.1em] uppercase text-[var(--text-dim)] mb-2">
        Step 5 · Skills &amp; proof
      </p>
      <h1
        className="text-[31px] font-[500] leading-[1.16] tracking-[-0.015em] text-[var(--text)] mb-3"
        style={{ fontFamily: "var(--font-hero, 'Newsreader', Georgia, serif)" }}
      >
        What makes you the match?
      </h1>
      <p className="text-[14px] leading-[1.5] text-[var(--text-dim)] mb-4">
        Skills drive scoring. Proof points power the tailoring — and the interview coach later.
      </p>

      <Field label="Core skills" req hint="Your strongest, most-relevant skills. These carry the most weight in scoring.">
        <TagInput
          tags={skills.primary}
          onChange={(t) => onSkillsChange({ ...skills, primary: t })}
          placeholder="Agile delivery"
          suggestions={SKILL_SUGGESTIONS}
        />
      </Field>

      <Field label="Supporting skills" optional hint="Good-to-have skills — weighted less than core skills in matching.">
        <TagInput
          tags={skills.secondary}
          onChange={(t) => onSkillsChange({ ...skills, secondary: t })}
          placeholder="Python, Terraform…"
        />
      </Field>

      <Field label="Certifications" optional hint="Listed on your profile and matched against job requirements.">
        <TagInput
          tags={skills.certifications}
          onChange={(t) => onSkillsChange({ ...skills, certifications: t })}
          placeholder="PMP, AWS SA, PSM-I…"
        />
      </Field>

      <Field label="Preferred domains" optional hint="Hatch boosts roles in sectors you've chosen; use exclusions to hide sectors.">
        <TagInput
          tags={domains.preferred}
          onChange={(t) => onDomainsChange({ ...domains, preferred: t })}
          placeholder="FinTech, Energy, Public Sector…"
        />
      </Field>

      <div className="space-y-3 pt-1">
        <div className="flex items-center justify-between">
          <p className="text-sm font-[550] text-[var(--text)]">
            Proof points <span className="text-[11px] font-[500] text-[var(--text-muted)] ml-1">Optional</span>
          </p>
          <button
            type="button"
            onClick={addProofPoint}
            className="text-[13px] font-[550] text-[var(--accent)] hover:text-[var(--accent-hover)]"
          >
            + Add proof point
          </button>
        </div>
        <p className="text-[12px] text-[var(--text-muted)]">
          1–2 wins with numbers. Hatch maps these to job requirements when writing your CV.
        </p>
        {proofPoints.map((p, i) => (
          <ProofPointForm
            key={p.id} point={p} index={i}
            onChange={(updated) => onProofPointsChange(proofPoints.map((x, j) => j === i ? updated : x))}
            onRemove={() => onProofPointsChange(proofPoints.filter((_, j) => j !== i))}
          />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/onboarding/StepSkills.tsx
git commit -m "feat: update StepSkills with editorial style, TagInput with suggestions, helper text"
```

---

## Task 14: Update StepAIProvider.tsx

**Files:**
- Modify: `frontend/src/components/onboarding/StepAIProvider.tsx`

- [ ] **Step 1: Replace StepAIProvider.tsx**

```tsx
"use client";

import { Loader2, CheckCircle, XCircle } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Field, Choice, ToggleRow, Seg, Help } from "./OnboardingPrimitives";
import type { LocaleBoard } from "@/lib/api";

export const LLM_PROVIDERS = [
  { id: "google",    label: "Google Gemini",    sub: "Free tier available — great default",  keyEnv: "GOOGLE_API_KEY",    triageDefault: "gemini-2.5-flash-lite",       primaryDefault: "gemini-2.5-flash" },
  { id: "anthropic", label: "Anthropic Claude",  sub: "Strongest tailoring quality",         keyEnv: "ANTHROPIC_API_KEY", triageDefault: "claude-haiku-4-5-20251001",   primaryDefault: "claude-sonnet-4-20250514" },
  { id: "openai",    label: "OpenAI",            sub: "GPT-4o family",                       keyEnv: "OPENAI_API_KEY",    triageDefault: "gpt-4o-mini",                 primaryDefault: "gpt-4o" },
  { id: "ollama",    label: "Ollama (local)",    sub: "Runs on your machine — $0, no key",   keyEnv: "",                  triageDefault: "gemma3:4b",                   primaryDefault: "qwen3:14b" },
];

export interface LLMData {
  provider: string;
  triage_model: string;
  primary_model: string;
  api_key_env: string;
  base_url: string | null;
  temperature: number;
  max_retries: number;
  track_costs: boolean;
  monthly_budget: number;
  currency: string;
}

interface StepAIProviderProps {
  llm: LLMData;
  onLlmChange: (llm: LLMData) => void;
  testApiKey: string;
  onTestApiKeyChange: (key: string) => void;
  testingConnection: boolean;
  connectionResult: { ok: boolean; error?: string } | null;
  onTestConnection: () => void;
  boards: LocaleBoard[];
  enabledBoards: Set<string>;
  onEnabledBoardsChange: (boards: Set<string>) => void;
  scrapeIntervalHours: number;
  onScrapeIntervalChange: (hours: number) => void;
}

export function StepAIProvider({
  llm, onLlmChange,
  testApiKey, onTestApiKeyChange,
  testingConnection, connectionResult, onTestConnection,
  boards, enabledBoards, onEnabledBoardsChange,
  scrapeIntervalHours, onScrapeIntervalChange,
}: StepAIProviderProps) {
  const handleProviderChange = (providerId: string) => {
    const p = LLM_PROVIDERS.find((x) => x.id === providerId);
    if (p) {
      onLlmChange({ ...llm, provider: providerId, triage_model: p.triageDefault, primary_model: p.primaryDefault, api_key_env: p.keyEnv });
      onTestApiKeyChange("");
    }
  };

  const needsKey = llm.provider !== "ollama";

  return (
    <div className="ob-fadein px-5 pb-4">
      <p className="text-[11px] font-[600] tracking-[0.1em] uppercase text-[var(--text-dim)] mb-2">
        Step 6 · AI &amp; launch
      </p>
      <h1
        className="text-[31px] font-[500] leading-[1.16] tracking-[-0.015em] text-[var(--text)] mb-3"
        style={{ fontFamily: "var(--font-hero, 'Newsreader', Georgia, serif)" }}
      >
        Pick the engine.
      </h1>
      <p className="text-[14px] leading-[1.5] text-[var(--text-dim)] mb-4">
        Hatch uses your own AI provider, so you control cost and privacy. Switch anytime in Settings.
      </p>

      <Field label="AI provider" req>
        <div className="grid grid-cols-1 gap-2">
          {LLM_PROVIDERS.map((p) => (
            <Choice
              key={p.id}
              on={llm.provider === p.id}
              onClick={() => handleProviderChange(p.id)}
              title={p.label}
              sub={p.sub}
            />
          ))}
        </div>
      </Field>

      {needsKey && (
        <Field
          label="API key"
          req
          hint="Validated live, then saved to your local machine only — never committed to the repo."
        >
          <div className="flex gap-2">
            <Input
              type="password"
              className="flex-1 font-mono text-[12.5px]"
              placeholder={llm.api_key_env}
              value={testApiKey}
              onChange={(e) => { onTestApiKeyChange(e.target.value); }}
            />
            <button
              type="button"
              onClick={onTestConnection}
              disabled={!testApiKey || testingConnection}
              className="flex-shrink-0 px-4 rounded-[var(--r-field,8px)] border border-[var(--border-strong)] text-[13px] font-[550] text-[var(--text)] disabled:opacity-40 transition-colors hover:bg-[var(--surface-3)]"
              style={{ background: "var(--surface-2)" }}
            >
              {testingConnection ? <Loader2 className="h-4 w-4 animate-spin" /> : "Test"}
            </button>
          </div>
          {connectionResult && (
            <div className={`flex items-center gap-2 mt-2 text-sm px-3 py-2 rounded-[var(--r-field,8px)] ${
              connectionResult.ok
                ? "text-[var(--success)]"
                : "text-[var(--danger)]"
            }`}
              style={{ background: connectionResult.ok ? "var(--success-soft)" : "var(--danger-soft)" }}>
              {connectionResult.ok
                ? <><CheckCircle className="h-4 w-4" /> Connected — key works.</>
                : <><XCircle className="h-4 w-4" /> {connectionResult.error ?? "Connection failed"}</>}
            </div>
          )}
        </Field>
      )}

      {llm.provider === "ollama" && (
        <Field label="Ollama base URL" hint="Default: http://localhost:11434 — change only if Ollama runs on a custom port.">
          <Input
            value={llm.base_url || ""}
            onChange={(e) => onLlmChange({ ...llm, base_url: e.target.value || null })}
            placeholder="http://localhost:11434"
          />
        </Field>
      )}

      {boards.length > 0 && (
        <Field label="Job boards" hint="Boards for your selected market, enabled by default. Toggle off any you don't want scraped.">
          {boards.map((b) => (
            <ToggleRow
              key={b.id}
              on={enabledBoards.has(b.id)}
              title={b.name}
              sub={enabledBoards.has(b.id) ? "Active" : "Disabled"}
              onToggle={() => {
                const next = new Set(enabledBoards);
                if (next.has(b.id)) next.delete(b.id); else next.add(b.id);
                onEnabledBoardsChange(next);
              }}
            />
          ))}
        </Field>
      )}

      <Field label="How often should Scout run?" hint="More frequent = fresher matches, slightly higher cost. You can change this later.">
        <Seg
          value={String(scrapeIntervalHours)}
          onChange={(v) => onScrapeIntervalChange(Number(v))}
          options={[
            { v: "2", l: "Every 2h" },
            { v: "4", l: "Every 4h" },
            { v: "8", l: "Every 8h" },
          ]}
        />
      </Field>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/onboarding/StepAIProvider.tsx
git commit -m "feat: update StepAIProvider with Choice cards, ToggleRow, field helper text"
```

---

## Task 15: Rewrite app/onboarding/page.tsx (controller)

**Files:**
- Modify: `frontend/src/app/onboarding/page.tsx`

- [ ] **Step 1: Replace page.tsx**

```tsx
"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  fetchLocales, fetchLocaleLegalFields, fetchLocaleBoards,
  testLLMConnection, saveProfile, saveApiKey, triggerAgent,
  type LocaleSummary, type LocaleLegalField, type LocaleBoard,
} from "@/lib/api";
import { OnboardingProgress } from "@/components/onboarding/OnboardingProgress";
import { ScreenWelcome } from "@/components/onboarding/ScreenWelcome";
import { ScreenSuccess } from "@/components/onboarding/ScreenSuccess";
import { StepAboutYou, type CandidateData } from "@/components/onboarding/StepAboutYou";
import { StepMarket } from "@/components/onboarding/StepMarket";
import { StepPay } from "@/components/onboarding/StepPay";
import { StepEligibility } from "@/components/onboarding/StepEligibility";
import { StepSkills, type SkillsData, type DomainsData, type ProofPoint } from "@/components/onboarding/StepSkills";
import { StepAIProvider, LLM_PROVIDERS, type LLMData } from "@/components/onboarding/StepAIProvider";
import type { SearchData, LocationData, CompensationData } from "@/components/onboarding/StepJobSearch";
import { ChevronLeft } from "lucide-react";

const FORM_STEPS = 6;
// step 0 = Welcome, step 1–6 = form, step 7 = Success
const WELCOME = 0;
const SUCCESS = 7;

const STORAGE_KEY = "hatch_onboarding_v1";

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(WELCOME);
  const [hasSaved, setHasSaved] = useState(false);
  const [tried, setTried] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Step 1 — About you
  const [candidate, setCandidate] = useState<CandidateData>({ name: "", title: "", years_experience: 0, summary: "" });

  // Steps 2–4 — Market, Pay, Eligibility
  const [selectedLocale, setSelectedLocale] = useState("uk");
  const [locales, setLocales] = useState<LocaleSummary[]>([]);
  const [loadingLocales, setLoadingLocales] = useState(true);
  const [search, setSearch] = useState<SearchData>({ target_roles: [], contract_type: "contract" });
  const [locations, setLocations] = useState<LocationData[]>([{ city: "", country: "", radius_miles: 30, remote_preference: "hybrid" }]);
  const [compensation, setCompensation] = useState<CompensationData>({ min_rate: 0, max_rate: 0, rate_type: "daily", currency: "GBP", legal_preferences: {} });
  const [legalFields, setLegalFields] = useState<LocaleLegalField[]>([]);

  // Step 5 — Skills
  const [skills, setSkills] = useState<SkillsData>({ primary: [], secondary: [], certifications: [] });
  const [domains, setDomains] = useState<DomainsData>({ preferred: [], excluded: [] });
  const [proofPoints, setProofPoints] = useState<ProofPoint[]>([]);

  // Step 6 — AI provider
  const [llm, setLlm] = useState<LLMData>({
    provider: "google", triage_model: "gemini-2.5-flash-lite", primary_model: "gemini-2.5-flash",
    api_key_env: "GOOGLE_API_KEY", base_url: null, temperature: 0.3, max_retries: 3,
    track_costs: true, monthly_budget: 15, currency: "USD",
  });
  const [testApiKey, setTestApiKey] = useState("");
  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionResult, setConnectionResult] = useState<{ ok: boolean; error?: string } | null>(null);
  const [boards, setBoards] = useState<LocaleBoard[]>([]);
  const [enabledBoards, setEnabledBoards] = useState<Set<string>>(new Set());
  const [scrapeIntervalHours, setScrapeIntervalHours] = useState(4);

  // ── Restore from localStorage ────────────────────────────────────────────
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed.candidate) setCandidate(parsed.candidate);
        if (parsed.search) setSearch(parsed.search);
        if (parsed.locations) setLocations(parsed.locations);
        if (parsed.compensation) setCompensation(parsed.compensation);
        if (parsed.skills) setSkills(parsed.skills);
        if (parsed.domains) setDomains(parsed.domains);
        if (parsed.proofPoints) setProofPoints(parsed.proofPoints);
        if (parsed.selectedLocale) setSelectedLocale(parsed.selectedLocale);
        if (parsed.llm) setLlm(parsed.llm);
        if (typeof parsed.step === "number" && parsed.step > 0 && parsed.step < SUCCESS) {
          setStep(parsed.step);
        }
        setHasSaved(true);
      }
    } catch {}
  }, []);

  // ── Persist to localStorage on every change ──────────────────────────────
  useEffect(() => {
    if (step === SUCCESS) return;  // never persist the success screen
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        step, candidate, search, locations, compensation, skills, domains, proofPoints, selectedLocale, llm,
      }));
    } catch {}
  }, [step, candidate, search, locations, compensation, skills, domains, proofPoints, selectedLocale, llm]);

  // ── Fetch locales ─────────────────────────────────────────────────────────
  useEffect(() => {
    fetchLocales()
      .then((ls) => { setLocales(ls); })
      .catch(() => {})
      .finally(() => setLoadingLocales(false));
  }, []);

  // ── Fetch legal fields + boards when locale changes ───────────────────────
  useEffect(() => {
    fetchLocaleLegalFields(selectedLocale)
      .then((fields) => {
        setLegalFields(fields);
        const defaults: Record<string, string> = {};
        fields.forEach((f) => { defaults[f.id] = f.default; });
        setCompensation((prev) => ({ ...prev, legal_preferences: defaults }));
      })
      .catch(() => setLegalFields([]));

    fetchLocaleBoards(selectedLocale)
      .then((bs) => {
        setBoards(bs);
        setEnabledBoards(new Set(bs.filter((b) => b.enabled).map((b) => b.id)));
      })
      .catch(() => setBoards([]));

    // Auto-derive currency and rate_type from locale pack
    const localePack = locales.find((l) => l.id === selectedLocale);
    if (localePack) {
      setCompensation((prev) => ({
        ...prev,
        currency: localePack.currency || prev.currency,
        rate_type: localePack.default_rate_type || prev.rate_type,
      }));
    }
  }, [selectedLocale, locales]);

  // ── Validation per step ──────────────────────────────────────────────────
  const isStepValid = (s: number): boolean => {
    switch (s) {
      case 1: return !!candidate.name.trim() && !!candidate.title.trim();
      case 2: return search.target_roles.length > 0;
      case 3: return !!locations[0].city.trim() && compensation.min_rate > 0;
      default: return true;
    }
  };

  const advance = () => {
    if (step > WELCOME && step < SUCCESS && !isStepValid(step)) {
      setTried(true);
      return;
    }
    setTried(false);
    setStep((s) => s + 1);
  };

  const back = () => { setTried(false); setStep((s) => Math.max(WELCOME, s - 1)); };

  const handleTestConnection = async () => {
    setTestingConnection(true);
    setConnectionResult(null);
    const result = await testLLMConnection(llm.provider, testApiKey).catch((e: unknown) => ({
      ok: false, error: e instanceof Error ? e.message : "Unknown error",
    }));
    setConnectionResult(result);
    setTestingConnection(false);
  };

  const buildProfile = () => ({
    locale: selectedLocale,
    candidate,
    search: { ...search, locations },
    compensation,
    skills,
    domains,
    proof_points: proofPoints.filter((p) => p.summary.trim()),
    master_cv_path: "./data/master_cv.json",
    job_boards: boards.map((b) => ({
      name: b.name, enabled: enabledBoards.has(b.id), scraper: b.scraper, search_params: {},
    })),
    scoring: {
      weights: { skill_match: 0.35, experience_match: 0.30, rate_match: 0.20, location_match: 0.15 },
      shortlist_threshold: 0.75,
    },
    llm,
    preferences: {
      scrape_interval_hours: scrapeIntervalHours, max_tailor_batch: 5,
      follow_up_days: [5, 10, 15], locale: "en-GB", archive_after_days: 30,
    },
  });

  const handleFinish = async () => {
    setSaving(true);
    setError("");
    try {
      await saveProfile(buildProfile());
      if (testApiKey && llm.provider !== "ollama") {
        await saveApiKey(llm.api_key_env, testApiKey).catch(() => {});
      }
      await triggerAgent("scout").catch(() => {});
      try { localStorage.removeItem(STORAGE_KEY); } catch {}
      setStep(SUCCESS);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setSaving(false);
    }
  };

  const currentLocale = locales.find((l) => l.id === selectedLocale);
  const formStep = step === WELCOME || step === SUCCESS ? 0 : step;

  return (
    <div
      data-onboarding="true"
      className="fixed inset-0 z-50 overflow-y-auto"
      style={{ background: "var(--bg)", color: "var(--text)" }}
    >
      <div className="w-full max-w-lg mx-auto min-h-screen flex flex-col">
        {/* Header row */}
        <div className="flex items-center justify-between px-5 pt-4">
          <div className="flex items-center gap-2">
            <div
              className="w-6 h-6 rounded-[7px] grid place-items-center font-[800] text-[13px] text-[var(--bg)]"
              style={{ background: "var(--text)" }}
            >
              H
            </div>
            <span className="text-[14px] font-[650] tracking-[-0.02em] text-[var(--text)]">Hatch</span>
          </div>
          {step > WELCOME && step < SUCCESS && (
            <span className="text-[12px] text-[var(--text-muted)] tabular-nums">
              <strong className="text-[var(--text)]">{formStep}</strong> of {FORM_STEPS}
            </span>
          )}
        </div>

        {/* Numeral progress (form steps only) */}
        <OnboardingProgress formStep={formStep} />

        {/* Screen content */}
        <div className="flex-1 overflow-y-auto">
          {step === WELCOME && (
            <ScreenWelcome hasSaved={hasSaved} onStart={advance} />
          )}
          {step === 1 && (
            <StepAboutYou candidate={candidate} onChange={setCandidate} tried={tried} />
          )}
          {step === 2 && (
            <StepMarket
              selectedLocale={selectedLocale}
              locales={locales}
              loadingLocales={loadingLocales}
              onLocaleChange={setSelectedLocale}
              search={search}
              onSearchChange={setSearch}
              tried={tried}
            />
          )}
          {step === 3 && (
            <StepPay
              locale={currentLocale}
              locations={locations}
              onLocationsChange={setLocations}
              compensation={compensation}
              onCompensationChange={setCompensation}
              tried={tried}
            />
          )}
          {step === 4 && (
            <StepEligibility
              locale={currentLocale}
              legalFields={legalFields}
              compensation={compensation}
              onCompensationChange={setCompensation}
            />
          )}
          {step === 5 && (
            <StepSkills
              skills={skills} onSkillsChange={setSkills}
              domains={domains} onDomainsChange={setDomains}
              proofPoints={proofPoints} onProofPointsChange={setProofPoints}
            />
          )}
          {step === 6 && (
            <StepAIProvider
              llm={llm} onLlmChange={setLlm}
              testApiKey={testApiKey}
              onTestApiKeyChange={(k) => { setTestApiKey(k); setConnectionResult(null); }}
              testingConnection={testingConnection}
              connectionResult={connectionResult}
              onTestConnection={handleTestConnection}
              boards={boards}
              enabledBoards={enabledBoards}
              onEnabledBoardsChange={setEnabledBoards}
              scrapeIntervalHours={scrapeIntervalHours}
              onScrapeIntervalChange={setScrapeIntervalHours}
            />
          )}
          {step === SUCCESS && (
            <ScreenSuccess
              candidate={candidate}
              selectedLocale={selectedLocale}
              locales={locales}
              targetRolesCount={search.target_roles.length}
              minRate={compensation.min_rate}
              providerName={LLM_PROVIDERS.find((p) => p.id === llm.provider)?.label ?? llm.provider}
              enabledBoardsCount={enabledBoards.size}
              onDashboard={() => router.push("/?firstRun=true")}
            />
          )}
        </div>

        {/* Footer navigation — hidden on Welcome and Success */}
        {step > WELCOME && step < SUCCESS && (
          <div
            className="flex-shrink-0 flex gap-2.5 px-5 py-3.5 border-t border-[var(--border)]"
            style={{ background: "var(--bg)", paddingBottom: "calc(env(safe-area-inset-bottom, 0px) + 14px)" }}
          >
            <button
              type="button"
              onClick={back}
              className="px-3.5 py-3 text-[14px] font-[600] text-[var(--text-dim)] hover:text-[var(--text)] transition-colors"
            >
              <ChevronLeft className="w-4 h-4 inline mr-0.5" />
              Back
            </button>
            {step < FORM_STEPS ? (
              <button
                type="button"
                onClick={advance}
                className="flex-1 py-3 rounded-[var(--r-btn,8px)] text-[14px] font-[600] text-[var(--on-accent)] transition-colors"
                style={{ background: "var(--accent)" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--accent-hover)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "var(--accent)")}
              >
                Continue →
              </button>
            ) : (
              <button
                type="button"
                onClick={handleFinish}
                disabled={saving}
                className="flex-1 py-3 rounded-[var(--r-btn,8px)] text-[14px] font-[600] text-[var(--on-accent)] disabled:opacity-50 transition-colors"
                style={{ background: "var(--accent)" }}
                onMouseEnter={(e) => !saving && (e.currentTarget.style.background = "var(--accent-hover)")}
                onMouseLeave={(e) => !saving && (e.currentTarget.style.background = "var(--accent)")}
              >
                {saving ? "Saving…" : "Start Hatch →"}
              </button>
            )}
          </div>
        )}

        {/* Inline error (step 6 finish only) */}
        {error && step === FORM_STEPS && (
          <p className="mx-5 mb-3 text-sm text-[var(--danger)] px-3 py-2 rounded border border-[var(--danger-soft)]"
            style={{ background: "var(--danger-soft)" }}>
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Run frontend unit tests**

```bash
cd frontend && npm test -- --run
```
Expected: All 102 existing tests pass (onboarding page isn't unit-tested, just confirmed no import errors).

- [ ] **Step 3: Run E2E tests — confirm existing tests still pass**

```bash
cd frontend && npx playwright test --reporter=list
```
Expected: 11/11 pass (dashboard/approvals/analytics tests unaffected by the overlay approach).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/onboarding/page.tsx
git commit -m "feat: rewrite onboarding controller — 6 form steps, Welcome, Success, localStorage resume, inline validation"
```

---

## Task 16: Add E2E test for onboarding route

**Files:**
- Create: `frontend/e2e/onboarding.spec.ts`

- [ ] **Step 1: Create onboarding.spec.ts**

```ts
import { test, expect } from "@playwright/test";

test("onboarding welcome screen renders with Get started button", async ({ page }) => {
  await page.goto("/onboarding");
  await page.waitForLoadState("networkidle");

  // Welcome screen should be visible (full-screen overlay)
  await expect(page.getByText("Your job search, on autopilot.")).toBeVisible();
  await expect(page.getByText("Get started")).toBeVisible();
});

test("onboarding step 1 shows numeral progress 01/06", async ({ page }) => {
  // Clear any saved state so we start fresh
  await page.goto("/onboarding");
  await page.waitForLoadState("networkidle");

  // Dismiss welcome
  await page.getByText("Get started").click();
  await page.waitForTimeout(200);

  // Should show step 1 numeral progress
  await expect(page.getByText("01")).toBeVisible();
  await expect(page.getByText("/ 06")).toBeVisible();
});

test("onboarding step 1 heading is present", async ({ page }) => {
  await page.goto("/onboarding");
  await page.waitForLoadState("networkidle");
  await page.getByText("Get started").click();
  await page.waitForTimeout(200);

  await expect(page.getByText("Who are we writing for?")).toBeVisible();
});

test("onboarding inline validation blocks advance when name is empty", async ({ page }) => {
  await page.goto("/onboarding");
  await page.waitForLoadState("networkidle");
  await page.getByText("Get started").click();
  await page.waitForTimeout(200);

  // Try to advance without filling name
  await page.getByText("Continue").click();
  await page.waitForTimeout(200);

  // Should show inline error, not advance
  await expect(page.getByText("Who are we writing for?")).toBeVisible();
  await expect(page.getByText("Name is required.")).toBeVisible();
});
```

- [ ] **Step 2: Run E2E tests**

```bash
cd frontend && npx playwright test --reporter=list
```
Expected: 15/15 pass (11 existing + 4 new onboarding tests).

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/onboarding.spec.ts
git commit -m "test: add E2E tests for onboarding welcome, step 1 progress, and inline validation"
```

---

## Task 17: Final verification, rebuild pods, push

- [ ] **Step 1: Run all backend tests**

```bash
python -m pytest backend/tests/ -q --tb=short
```
Expected: Same baseline as before (15–16 pre-existing embedding failures, all other tests green).

- [ ] **Step 2: Run all frontend unit tests**

```bash
cd frontend && npm test -- --run
```
Expected: All unit tests pass (102 existing + new primitive tests).

- [ ] **Step 3: Run all E2E tests**

```bash
cd frontend && npx playwright test --reporter=list
```
Expected: 15/15 pass.

- [ ] **Step 4: Rebuild Podman containers (no-cache)**

```bash
cd /home/asoni/Downloads/Assignment/Job_Pilot_v2 && podman-compose down && podman-compose build --no-cache && podman-compose up -d
```

Wait for both to be healthy:
```bash
until podman inspect jobpilot-frontend --format '{{.State.Health.Status}}' 2>/dev/null | grep -q "healthy"; do sleep 3; done
podman-compose ps
```
Expected: Both containers show `(healthy)`.

- [ ] **Step 5: Run E2E tests against running containers**

```bash
cd frontend && npx playwright test --reporter=list
```
Expected: 15/15 pass.

- [ ] **Step 6: Push to GitHub**

```bash
git push origin main
```

---

## Acceptance Checklist (verify before marking complete)

- [ ] `/onboarding` is dark-first, Editorial tokens, no light gradient
- [ ] 6 focused form steps + Welcome + Success
- [ ] Every field has helper text; steps 2 and 4 show Why callout
- [ ] Headings render in Newsreader; multi-line headings don't overlap following text
- [ ] Numeral progress `01 / 06` + step name on form steps; none on Welcome/Success
- [ ] Currency and rate-type are auto-derived from locale, shown as read-only chip
- [ ] Required-field validation shows inline errors on attempted advance
- [ ] Progress persists across reload; Welcome CTA = "Resume setup" when in progress
- [ ] Finish sequence: `saveProfile → saveApiKey → triggerAgent("scout") → /onboarding Success screen → /?firstRun=true`
- [ ] Works at mobile widths (≥44px tap targets, no horizontal scroll)
- [ ] Dashboard, approvals, analytics pages render correctly (no shadcn regression)
- [ ] All E2E tests green (15/15)
