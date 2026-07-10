---
title: Hatch UX Audit
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

# Hatch UX Audit

## Context

This audit establishes the Release 4 baseline for Hatch before page-level changes begin. It reviews the current Today implementation, shared navigation, theme tokens, and the checked-in desktop and mobile Today reference screenshots in `docs/design_handoff_hatch_directionA/screenshots/`.

The screenshots are design-handoff references rather than a claim about live production data. Findings were cross-checked against `TodayScreen`, `TodayPageClient`, `AgentActivityPanel`, `HatchSidebar`, and the mobile navigation components.

Hatch's intended experience is a private job-search command centre: calm, competent, evidence-led, and clear about the user's next action.

## Current Strengths

- The dark interface is restrained and appropriately private for sensitive career data.
- Desktop and mobile preserve the same primary destinations and core task order.
- Match and CV ATS scores are visually compact and remain distinct.
- The Today screen already brings review, application, interview, and follow-up tasks together.
- Agent identity is consistent through icons and fixed semantic colours.
- Theme-aware semantic tokens support both dark and light modes.
- Existing empty-state and skeleton components provide a good foundation for recovery and loading states.
- Cards use spacing and grouping effectively to separate workflow stages.

## Key UX Problems

1. Today reads as an agent report before it reads as a user action queue.
2. “Agent output,” “Needs you,” and “Packages” expose internal language rather than user intent.
3. Pipeline totals are visually prominent but lack recency and clear next actions.
4. The primary action competes with several similar card-level actions.
5. Interactive cards and rows do not consistently expose keyboard focus or semantics.
6. “Agents running” and pulsing status can imply live activity without verified running state.
7. Mobile packs dense score, status, and action information into a narrow column.
8. Error and retry states are not consistently represented on Today.
9. Responsive behavior relies heavily on hiding and relocating panels rather than explicitly reprioritising content.
10. Shared motion and focus behavior is not yet enforced globally.

## Detailed Findings

### Today prioritises system output over user intent

**Observation:** The first major card is labelled “Agent output” and presents all-time pipeline totals. In the reference desktop screenshot, the pipeline also receives the full-width hero position.

**Impact:** Users must interpret what the agents did before learning what needs attention now. All-time totals can appear fresh even when they are not.

**Suggestion:** Lead with a dated, plain-language status summary and one primary action. Move agent progress below it and label totals with a meaningful time range or last-run timestamp.

### The action hierarchy is fragmented

**Observation:** Review, application, interview preparation, follow-up, and agent activity actions are presented with similar card weight. The desktop reference gives the review queue prominence, but the implemented page lacks a single hero CTA.

**Impact:** A user with several pending tasks has to choose without a clear recommendation.

**Suggestion:** Rank actions by urgency and readiness. Show one primary CTA such as “Review CV packs,” with secondary actions visually subordinate.

### Internal terminology increases translation effort

**Observation:** Current copy includes “Agent output,” “Needs you,” “Packages ready,” “Stream,” and “Tracker.”

**Impact:** These labels describe system concepts rather than the outcome the user wants.

**Suggestion:** Prefer “Agent progress,” “Ready for you,” “CV packs ready,” “Pipeline,” and “Applications” in visible labels while preserving routes.

### Status can overstate live activity

**Observation:** A pulsing green dot appears beside “Agent output,” and the sidebar says “Agents running” for the entire pipeline. Neither presentation is tied to a verified active state in the reviewed components.

**Impact:** Users may believe work is currently running when the UI is only showing capability or historical totals. That weakens trust.

**Suggestion:** Animate only confirmed running work. Otherwise use “Your agents,” “Last activity,” or a static status with a timestamp.

### Pipeline counts lack decision context

**Observation:** Scout, Scorer, Tailor, and Coach totals show volume and transit counts, but not failure, freshness, or the user's next step.

**Impact:** High counts can look positive without explaining whether jobs are relevant, stalled, or ready.

**Suggestion:** Pair each agent count with a human-readable state, last-run time, and an existing destination where useful.

### Review rows need stronger interaction semantics

**Observation:** Job rows are buttons, which is good, but their inline styling provides no guaranteed hover or `focus-visible` treatment. The interview card uses a clickable `div` wrapping another button.

**Impact:** Keyboard users may lose their location, and nested or ambiguous click targets make expected behavior less clear.

**Suggestion:** Use one semantic interactive element per action, provide a visible 2–3px focus ring, and ensure a minimum 44px target on touch screens.

### Mobile information density is high

**Observation:** The mobile reference compresses pipeline counts, three review rows, scores, ATS badges, and a CTA into the opening viewport. The implementation also moves the full activity panel below the primary content.

**Impact:** Scan effort rises and secondary activity can make the page feel long.

**Suggestion:** Show the highest-priority item first, collapse or summarise the remainder, and make agent activity progressively disclosed on small screens.

### Empty states are positive but incomplete

**Observation:** The approval queue has a reassuring success state, and generic shared empty states exist elsewhere.

**Impact:** Today still lacks equally clear first-run, delayed, partial-data, and load-failure states.

**Suggestion:** Define explicit loading, empty, stale, partial, and error states with one recovery action each.

### Responsive hierarchy needs explicit rules

**Observation:** Desktop uses a two-column layout at `lg`; mobile places the activity panel below the main content. Several action rows use inline flex layouts without an explicit small-screen wrapping contract.

**Impact:** Long job titles, translated text, larger type, or narrow landscape layouts may crowd controls or cause truncation.

**Suggestion:** Make primary content order explicit at each breakpoint, allow action groups to stack, and test at 375px, 768px, 1024px, and 1440px.

### Motion and focus are not systematised

**Observation:** A global 160ms transition token exists, but Hatch primitives use mixed or absent transitions. No global reduced-motion rule or baseline interactive focus rule was found.

**Impact:** Feedback varies between controls, while pulsing and skeleton animations may continue for people who request reduced motion.

**Suggestion:** Adopt the motion and focus rules in `HATCH_MICROINTERACTIONS.md` before adding page-level animation.

## Navigation Critique

- The four-destination structure is compact and learnable.
- Desktop and mobile placement is appropriate to their viewport.
- Active state is clear through colour and background, but focus state must be equally clear.
- Visible labels should move toward “Pipeline,” “Applications,” and “Interview Prep”; URLs may remain `/stream`, `/tracker`, and `/prep`.
- Notification badges should only appear when their meaning and clearing behavior are defined.
- The sidebar agent panel should describe capability or real state accurately rather than defaulting to “running.”

## Information Hierarchy Critique

- User decisions should precede agent telemetry.
- Readiness, urgency, and deadline should determine card order.
- Match score and CV ATS score should remain separate and explicitly labelled.
- Historical totals belong in a secondary progress section.
- Activity feeds and weekly statistics are supporting evidence, not the primary task.

## Visual Hierarchy Critique

- The existing surface, border, radius, and accent system feels cohesive.
- Accent borders should be reserved for the current primary action or selected state.
- Small muted labels meet measured token contrast, but dense 9–11px labels are harder to read and should not carry essential meaning.
- Repeated pills can create visual noise; use them only for status or data that changes a decision.
- Desktop whitespace is effective, while mobile needs more aggressive prioritisation rather than simple compression.

## Copy and Tone Critique

- Existing copy is concise but sometimes system-centred.
- “Your application workspace at a glance” is generic and does not identify the next action.
- “Everything you approved is on its way” may imply submission when Hatch may only have prepared material.
- Errors and delayed agent work need cause-and-recovery language.
- Use direct, supportive wording without celebration, blame, or technical extraction terminology.

## Accessibility Concerns

- Shared Hatch buttons, clickable rows, and navigation links need guaranteed `focus-visible` styling.
- Clickable non-semantic containers should become links or buttons.
- Icon-only controls require accessible names.
- Touch targets should be at least 44×44px with at least 8px separation.
- Status must not rely on colour or pulse alone.
- Motion must respect `prefers-reduced-motion`.
- Heading order and route-change focus should be verified page by page.
- Text and control contrast must be checked independently in both themes.
- Loading and result changes should use appropriate, non-disruptive live regions.

## Responsive Concerns

- Test long titles and company names without hiding essential actions.
- Stack multi-action rows below 640px.
- Keep bottom navigation from covering the last action.
- Avoid horizontal scrolling at 375px and in mobile landscape.
- Preserve useful content with 200% text zoom.
- Defer secondary activity on mobile instead of duplicating the full desktop rail.

## Top 10 Improvement Opportunities

1. Introduce a Today hero with one recommended action.
2. Rename user-facing internal terminology without changing routes.
3. Reframe the pipeline as timestamped agent progress.
4. Make “Ready for you” the dominant action area.
5. Add consistent focus, hover, pressed, and disabled states.
6. Tie animated agent status to real running state.
7. Add explicit loading, stale, partial, error, and recovery states.
8. Simplify mobile cards and progressively disclose secondary content.
9. Replace ambiguous clickable containers with semantic controls.
10. Validate light/dark contrast, reduced motion, keyboard flow, and 200% zoom in final QA.

## Priority Fixes

### P0 — Trust and access

- Do not claim agents are running unless runtime state confirms it.
- Guarantee keyboard focus visibility and semantic controls.
- Provide cause-and-recovery error messages.
- Respect reduced-motion preferences.

### P1 — Task clarity

- Put one recommended action at the top of Today.
- Rename “Needs you” to “Ready for you.”
- Add time context to agent progress.
- Keep match and CV ATS scores visibly distinct.

### P2 — Polish

- Reduce pill and metadata density.
- Harmonise hover, pressed, loading, and completion feedback.
- Reprioritise mobile supporting content.

## Acceptance Criteria for Future UI PRs

- Each page has one visually dominant primary action.
- User-facing copy follows `HATCH_COPY_GUIDE.md`.
- Components follow `HATCH_DESIGN_SYSTEM.md`.
- Motion follows `HATCH_MICROINTERACTIONS.md`.
- All interactive controls are semantic, keyboard operable, and visibly focused.
- Status is conveyed with text or icons in addition to colour.
- Loading, empty, error, and success states have clear user outcomes.
- No essential action depends on hover or animation.
- Layouts pass at 375px, 768px, 1024px, 1440px, mobile landscape, and 200% zoom.
- Dark and light themes are checked separately.
- Existing business logic, routes, and score meanings remain intact unless a PR explicitly changes them.
