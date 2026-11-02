# Hatch design system — brand book

Recorded from `frontend/src/app/globals.css`, `frontend/tailwind.config.ts` and `frontend/src/components/ui/` at commit b7274a6. The code is the source of truth; if this file and the code disagree, the code wins and this file is updated. Values for every token are in [tokens.json](tokens.json); [tokens.css](tokens.css) is the same set as CSS variables, for reference only (the app already defines them in `globals.css`).

Hatch is a self-hosted, human-in-the-loop workspace for job search, applications and interview preparation. The interface is a calm, dense, dark-first tool: one teal accent for action, four fixed agent colours for identity, and everything else in neutral surfaces. Build every new screen from the tokens and components here; do not add colours, radii or type sizes the system does not define.

## Voice and copy

- Write to the candidate as "you"; Hatch refers to itself by name ("Hatch needs your target roles…"). Never "we".
- Sentence case everywhere: titles, buttons, badges ("Set up your profile first", "Clear filters").
- Lead with what to do next. Empty states say why the page is empty and the one action that fixes it: "Run Job Scout to fetch roles that match your profile."
- Be precise about certainty. Evidence copy says what Hatch checked and what it did not: "Hatch source matching, not independent verification."
- Buttons are short verb phrases: "Go to Settings", "Refresh", "Build brief". No exclamation marks, no emoji.
- Coach uses named levels, never numeric scores: Needs work · Developing · Interview ready · Strong · Not assessed. Write "Interview ready" without a hyphen (one older screen hyphenates it; do not copy that).
- Coach readiness screens use these words, never the engineering terms: Focus area suggestion, Strength, Mixed results, Needs more practice, Older, From your real interviews, Ready story, Could be stronger, No story yet, Tips unavailable.

## Colour

- Page canvas is `bg`. Cards, panels, dialogs and sheets are `surface`. Inputs, nested blocks, neutral badges and empty states are `surface-2`; `surface-3` is a third level for hover and skeletons. Floating tooltips use `bg-elevated`.
- Text is `text` for titles and anything the user must read to act, `text-dim` for body and descriptions, `text-muted` only for captions and hints at 12px or larger (it is below 4.5:1 on dark surfaces).
- `accent` (teal) marks the primary action, links, the active nav item and focus. Use at most one `accent`-filled button per view. Text on an accent fill is `on-accent`, never white.
- Status colours are `success`, `warning`, `danger`, with `-soft` backgrounds for badges; text on a soft background is the matching strong colour. Always pair a status colour with a word or icon: in the light theme `success` and `warning` are about 3:1.
- `border` is a decorative hairline (1.2:1). Never let it be the only edge that tells someone a control exists; inputs also differ by fill (`surface-2` on `surface`).
- The `brand-*` blue scale is legacy Tailwind config. Do not use it in new work.

## Themes

- Dark is the default and the first theme. Light is opt-in from the user menu. Both are set by `data-theme` on `<html>`; dark also adds the `dark` class.
- Design every screen in both. The light theme's accent, success and warning are close to 3:1; check any small coloured text there.
- The two onboarding themes are a scoped override (`data-onboarding="true"`) with an indigo accent. Use them only inside the first-run wizard, never in the app shell.

## Type

- One family, Inter (`font-sans`), for everything; Roboto Mono (`font-mono`, weights 500 and 700) only for scores and figures that line up.
- Page titles use `page-title` (28px, `page-title-mobile` 24px below 640px), one per page via PageHeader. Section headings in SectionCard use `section-title`; card headings `card-title`; dialog headings `dialog-title`.
- Body text is `body` (14px, 1.5). Descriptions under titles are `description` in `text-dim`, kept under 65 characters wide.
- Control text: `label` for field labels, `button` for buttons, `badge` for status pills, `chip` for shell chips. `stage-label` (9.5px) is for StageTrack only.

## Spacing and layout

- Spacing follows the Tailwind 4px scale; use `space-2` between related controls, `space-4`/`space-5` for section padding (16px on phones, 20px from 640px), `space-6` inside Card.
- Pages sit in PageContainer (narrow 768px, default 1024px, wide 1280px) with `page-gutter` side padding. The desktop sidebar is `sidebar-width`.
- Every interactive control is at least `control-min-height` (44px) on touch; buttons may be 40px from 640px up.
- Page header actions stack under the title below 640px.

## Shape and depth

- `radius-control` (8px) for buttons and inputs, `radius-card` (12px) for cards, dialogs and popovers, `radius-compact` (6px) for chips, `radius-pill` for status badges. Do not use the compatibility aliases (`radius-xs`…`radius-lg`, `r-*`) in new work.
- Depth comes from surface steps and a hairline border first. Shadows are light: `shadow-sm` on cards and primary buttons, `shadow-md` on popovers, `shadow-lg` on dialogs and sheets. No gradients; page titles never use gradient text.

## Motion and states

- Transitions are 160ms with `cubic-bezier(.4,0,.2,1)` (`--transition`); 120ms for small feedback. Pressed controls scale to 0.98. All motion stops under `prefers-reduced-motion`.
- Hover darkens fills (`accent-hover`) or adds `surface-2` behind ghost and outline controls. Disabled controls drop to 50% opacity and show a not-allowed cursor.
- Loading uses Skeleton shapes that match the content, or the Button `loading` spinner. Never a full-page spinner for content that has a deterministic part ready.

## Focus and accessibility

- Every focusable element shows a 3px solid `focus-ring` outline with a 3px offset. Do not remove it or replace it with a shadow.
- Dialogs are labelled by their title and description; icon-only buttons carry an `aria-label` (the dialog close button is "Close dialog").
- Empty and status regions announce politely (`role="status"`, `aria-live="polite"`). Form errors use `role="alert"` and are linked with `aria-describedby` through FormField.

## Iconography

- Icons are Lucide (lucide-react 0.441), drawn as 2px strokes at 18px by default, through the `Icon` component's short names (`calendar`, `target`, `mic`, `fileText`, `checkCircle`…). Unknown names render a question-mark circle, so add new glyphs to the Icon map rather than importing ad hoc.
- Icons inherit `currentColor`; status icons take the status colour. Decorative icons are `aria-hidden`.
- The app mark is the egg-and-pulse logo in Logos. The sidebar shows a 28px `accent` tile with the Lucide layers glyph beside the wordmark set in `brand-wordmark`.

## Agents

- Scout, Scorer, Tailor and Coach each have one fixed colour (`agent-scout`, `agent-scorer`, `agent-tailor`, `agent-coach`, with `-soft` tints) that never follows the theme. Use them only as identity marks beside the agent name (StageTrack nodes, agent badges), never as text: they fall below 3:1 on light surfaces.
- Coach is amber (`agent-coach`). Coach screens use the amber mark for identity and `accent` for actions, like every other screen.

## Components

- Prefer the token-based components: Button, StatusBadge, Card, SectionCard, PageHeader, EmptyState, FormField with Input, Dialog, AlertDialog, Sheet, Popover, Skeleton, Icon.
- Badge, Textarea, Select and Label are legacy: they hard-code Tailwind light palettes and rely on dark-mode catch-all overrides. Use StatusBadge instead of Badge; when a new screen needs a textarea or select, give it the Input styling (`surface-2` fill, `border`, `radius-control`).
- Destructive confirmations use AlertDialog with a `destructive` action; everything else that needs a modal uses Dialog, and long side panels use Sheet.

## Not synced

- Inter and Roboto Mono are Google-hosted, so no font files are stored here. In the app, Inter loads through next/font as `--font-inter`, but the stacks name `'Inter'` literally; check in the browser that Inter actually renders and not system-ui.
- Motion values (`--duration-fast`, `--duration-standard`, `--ease-standard`, `--transition`) stay in `components/bundle.css`; the token format has no motion family.
- The onboarding scope's `--bg-elev` alias was not carried over; it equals `bg-elevated`.
- Shell components in `components/hatch/` (Sidebar, TopBar, Chip, Dot, ScorePill, StageTrack, AgentBadge) are not in this system yet; components here are built from `components/ui/` at commit b7274a6.
- Known source issues kept as they are: `text-muted` is 3.9:1 on dark `surface`; light `on-accent` on `accent` is 3.4:1; EmptyState's action button uses white text on `accent` (2.2:1 in dark) instead of `on-accent`.
