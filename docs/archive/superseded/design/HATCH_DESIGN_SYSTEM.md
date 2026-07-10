---
title: Hatch Design System
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

# Hatch Design System

## Product Personality

Hatch is a private job-search command centre. It should feel calm, competent, premium, and trustworthy.

Design principles:

- Calm over flashy.
- Clear over clever.
- Trustworthy over playful.
- Actionable over decorative.
- Evidence-first over hype-first.

Avoid ambient animation, decorative gradients, excessive glass effects, gamification, and unsupported claims about agent activity.

## Foundations

Use the existing semantic CSS variables in `frontend/src/app/globals.css`. Do not introduce raw theme colours inside components when a semantic token exists.

### Colour roles

| Role | Token | Use |
|---|---|---|
| Canvas | `--bg` | App background |
| Elevated canvas | `--bg-elevated` | Shell and raised regions |
| Surface | `--surface` | Cards and panels |
| Nested surface | `--surface-2` | Rows, fields, grouped content |
| Strong nested surface | `--surface-3` | Selected/loading layers |
| Border | `--border` | Default separation |
| Strong border | `--border-strong` | Focus-adjacent or prominent separation |
| Primary text | `--text` | Headings and essential values |
| Body text | `--text-dim` | Descriptions |
| Muted text | `--text-muted` | Timestamps and non-essential metadata |
| Primary action | `--accent` | One primary CTA and current selection |

Semantic success, warning, danger, and agent colours must include a text label or icon; colour alone never communicates state.

Check WCAG AA contrast in dark and light themes independently: 4.5:1 for normal text and 3:1 for large text and meaningful UI graphics.

## Typography

- Use Inter/system sans through `--font-sans` for interface copy.
- Use `--font-mono` only for compact scores, counts, timestamps, and aligned numeric data.
- Use sentence case for headings, labels, and buttons.
- Keep body text at 14–16px desktop and at least 16px for mobile form controls.
- Do not use essential labels below 12px.
- Body line height: 1.5–1.65.
- Limit long-form copy to roughly 65–75 characters per line.
- Use tabular figures for changing counts where layout shift would be distracting.

Suggested scale:

| Role | Size | Weight |
|---|---:|---:|
| Page title | 28–32px | 700–800 |
| Section title | 18–22px | 650–700 |
| Card title | 14–16px | 600–700 |
| Body | 14–16px | 400–500 |
| Label | 12–13px | 550–650 |
| Metadata | 12px minimum | 400–500 |

## Spacing

Use a 4px base rhythm:

- 4px: icon/text optical adjustment only.
- 8px: tightly related inline elements.
- 12px: compact control or row spacing.
- 16px: standard card padding and component gap.
- 24px: section separation.
- 32px: major page grouping.
- 48px: large desktop separation.

Interactive targets must be at least 44×44px with at least 8px between adjacent targets.

## Layout

- Use a consistent centred content width; do not introduce page-specific arbitrary maxima.
- Desktop: primary work in the main column, evidence/activity in a narrower supporting rail.
- Tablet: preserve the primary content first; supporting panels move below.
- Mobile: prioritise the next action, then ready work, then agent progress and history.
- Breakpoints to verify: 375px, 768px, 1024px, and 1440px.
- Avoid nested scrolling and horizontal overflow.
- Reserve space for fixed mobile navigation and safe-area insets.

## Card System

### Standard card

- `--surface` background.
- 1px `--border`.
- `--radius-lg`.
- No shadow by default in dark mode; `--shadow-sm` is acceptable when light-mode separation needs it.

### Action card

- Standard card plus a clear title, outcome, and one leading action.
- Use accent border or ring only for the highest-priority actionable card.
- Do not make the whole card clickable when it also contains separate controls.

### Supporting card

- Lower visual weight than action cards.
- Use for metrics, activity, context, and historical evidence.

### Interactive row

- Semantic link or button.
- Minimum 44px height.
- Stable hover, pressed, and focus-visible states.
- Never rely on a chevron alone to communicate clickability.

## Badge and Status System

Use badges for concise state, not general decoration.

| Variant | Meaning | Treatment |
|---|---|---|
| Neutral | Metadata, draft, inactive | Muted surface and text |
| Accent | Current selection or primary queue | Accent-soft background and label |
| Success | Completed or verified ready | Success-soft background plus icon/text |
| Warning | Time-sensitive or incomplete | Warning-soft background plus icon/text |
| Danger | Failed, blocked, overdue | Danger-soft background plus icon/text |

- Keep match score and CV ATS score separate.
- Label ambiguous values (`Match 86%`, `CV ATS 88%`).
- Do not use success styling for a merely high match score if no completion occurred.
- Animated status is reserved for confirmed active processing.

## Buttons

### Primary

- One per view or decision region.
- Solid `--accent` with `--on-accent`.
- Direct outcome copy: “Review CV packs,” “Save job,” “Generate CV pack.”

### Secondary

- Surface background with visible border.
- Used for useful alternatives that do not compete with the primary action.

### Ghost

- Used for low-risk tertiary actions in a contained region.
- Must still have hover and focus-visible feedback.

### Destructive

- Danger treatment, spatially separated from the primary action.
- Confirm irreversible actions or provide undo where practical.

All buttons require hover, pressed, focus-visible, disabled, and asynchronous loading states. Disabled controls use the native `disabled` attribute and must not appear interactive.

## Icons

- Use the existing Hatch SVG icon system or Lucide; do not use emoji as structural icons.
- Keep stroke style and weight consistent within a navigation or action group.
- Standard sizes: 16px inline, 20px control, 24px feature, 32px empty state.
- Icon-only buttons need an accessible name and a 44×44px target.
- Decorative icons are hidden from assistive technology.

## Agent Identity

| Agent | Colour token | User-facing role |
|---|---|---|
| Scout | `--scout` | Finds roles |
| Scorer | `--purple` | Ranks matches |
| Tailor | `--success` | Prepares CV packs |
| Coach | `--warning` | Prepares interviews |

Agent colours identify the source, not health or success. Pair every colour with the agent name and an icon. Show running, completed, delayed, or failed as separate textual status.

## Navigation

- Use the same four primary destinations across desktop and mobile.
- Preferred visible labels: Today, Pipeline, Applications, Interview Prep.
- Preserve existing route paths unless a scoped PR changes them.
- Active navigation uses icon, label weight, and background—not colour alone.
- Navigation links require a visible focus ring.
- Badges need defined meaning and clearing behavior.

## Forms and Feedback

- Always show a persistent label.
- Put helper text and errors next to the relevant field.
- Validate after blur or submit, not on every keystroke.
- On failure, state what happened and how to recover.
- Async buttons show a progress label and remain disabled until completion.
- Success confirmation should be brief and announced politely without stealing focus.

## Responsive Rules

- Content priority, not simple compression, determines mobile order.
- Action groups stack when controls would fall below 44px or labels would truncate.
- Long job titles and company names wrap where the full value matters.
- Secondary metadata may collapse behind a labelled disclosure.
- Fixed bars must not cover content at the end of the page.
- Support mobile landscape and 200% text zoom without horizontal scrolling.

## Accessibility Rules

- Use native links, buttons, headings, lists, and form controls.
- Provide a visible 2–3px `focus-visible` ring with sufficient contrast.
- Keep DOM order aligned with visual and keyboard order.
- Do not nest interactive controls.
- Provide accessible names for icon-only controls.
- Do not communicate status through colour, position, or motion alone.
- Respect `prefers-reduced-motion`.
- Use live regions only for meaningful async updates; avoid repeated announcements.
- Move focus appropriately after route changes, modal opens/closes, and validation failures.
- Verify keyboard-only use, screen-reader labels, theme contrast, and zoom before release.

## Implementation Boundary

This document guides Release 4 presentation. It does not authorise business-logic changes, route renames, new animation dependencies, or agent architecture changes.
