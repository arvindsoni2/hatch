# Hatch Microinteractions

## Purpose

Motion and feedback in Hatch should confirm cause and effect. It should never decorate idle screens, exaggerate activity, or delay work.

## Timing Tokens

| Interaction | Duration | Easing |
|---|---:|---|
| Hover, focus, press | 120–180ms | ease-out |
| Inline state change | 160–200ms | ease-out |
| Panel or modal enter | 180–240ms | ease-out |
| Panel or modal exit | 120–180ms | ease-in |

Prefer opacity and transform. Do not animate layout properties such as width, height, top, or left when a transform can express the change.

## Allowed Patterns

### Cards and rows

- Hover: subtle border emphasis or up to 1–2px visual lift.
- Press: small opacity or scale response, never below 0.97.
- Focus: immediate visible ring; focus must not depend on animation.
- Non-interactive cards do not lift on hover.

### Buttons

- Hover: accent or surface emphasis.
- Press: small scale or brightness response.
- Async action: replace or pair the label with clear progress text; disable repeat submission.
- Success: brief checkmark or toast after the state is confirmed.

### Agent activity

- Pulse only while backend state confirms active work.
- Completed, idle, delayed, and failed states remain static.
- Never animate all agents continuously.
- Always pair activity with text and, where available, a timestamp.

### New items

- One short fade and 4–8px slide when an item enters an already-visible list.
- Do not stagger large lists.
- Do not replay entry motion after ordinary rerenders.

### Count changes

- Prefer an immediate value update.
- A gentle count-up is allowed only when already available without a new dependency and when the final value is announced correctly.
- Use tabular figures to prevent horizontal shift.

### Loading

- Use a stable skeleton when loading is expected to exceed 300ms.
- Reserve the final content's approximate space to avoid layout shift.
- Skeleton shimmer or pulse stops under reduced motion.
- Do not show empty content before loading resolves.

### Errors

- Reveal the message inline next to the affected region.
- Use a static icon, plain-language cause, and recovery action.
- Do not shake fields or flash the screen.
- Move focus to the error summary only when submission cannot continue.

### Completion

- Confirm review, save, apply, or generation only after success.
- Use a brief toast or inline state transition.
- Toasts use `aria-live="polite"`, do not steal focus, and dismiss after 3–5 seconds when no action is required.

### Panels and modals

- Enter with opacity plus a small scale or directional translation.
- Exit faster than entry.
- Focus moves into the panel on open and returns to the trigger on close.
- Escape and a visible close control must work.

## Reduced Motion

Under `prefers-reduced-motion: reduce`:

- Disable smooth scrolling.
- Remove pulse, shimmer, count-up, lift, slide, and scale effects.
- Reduce remaining transition durations to near-instant.
- Keep focus, loading text, state icons, and completion messages visible.
- Do not remove information together with animation.

Recommended baseline:

```css
@media (prefers-reduced-motion: reduce) {
  html {
    scroll-behavior: auto;
  }

  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
  }
}
```

Apply this only after checking controls whose visibility currently depends on transition events.

## Focus and Input Feedback

- Keyboard focus uses `:focus-visible`, not a permanent focus reset.
- The ring is 2–3px and contrasts against both the control and surrounding surface.
- Hover is supplementary; every hover-revealed action is also reachable by keyboard and touch.
- Touch targets are at least 44×44px with 8px separation.
- Disabled elements use native semantics, reduced emphasis, and no pointer behavior.
- Loading feedback begins promptly and does not block unrelated navigation.

## Prohibited Patterns

- Constant ambient movement.
- Animation that implies unverified agent activity.
- Bouncy or playful spring motion.
- Decorative parallax, glowing blobs, or random gradients.
- Layout-shifting hover effects.
- Motion longer than 500ms.
- Animation required to understand state.
- A new motion library without explicit approval.
- Confetti or celebratory effects for routine workflow completion.

## QA Checklist

- Verify keyboard focus at every interactive element.
- Verify reduced-motion behavior at operating-system level.
- Confirm no motion repeats while the page is idle.
- Confirm running animation is tied to real state.
- Confirm loading reserves space and has a text alternative where needed.
- Confirm async feedback is announced once.
- Test touch behavior at 375px and mobile landscape.
- Check that rapid repeated input cannot submit an action twice.
