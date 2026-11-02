# Coach Phase 2 screen designs

The approved UI reference for the Interview Readiness Loop (spec `docs/implementation-specs/active/2026-10-22-coach-phase2-readiness-loop.md`, §13). Use the screenshots for layout and copy, and this file for how each part maps to existing code. Behaviour, limits and statuses come from the spec; if a screenshot and the spec disagree, the spec wins and the reviewer flags the screenshot.

All names, companies, dates and stories in the designs are invented examples. Do not copy them into fixtures that look like real candidate data.

## Screens

| Screen | Route (proposed) | Dark | Light | Other | PR |
|---|---|---|---|---|---|
| Interview readiness | `/coach/readiness` (new tab beside Sessions and Stories); data from `GET /coach/readiness` | [readiness-dark.png](screens/readiness-dark.png) | [readiness-light.png](screens/readiness-light.png) | [phone width, 390 px](screens/readiness-phone-dark.png) | P4, P5 (P1 for the coverage chips, P7 for the next-interview card) |
| Interview brief | Interview round → Brief tab; data from `GET /coach/readiness/rounds/{round_id}/brief` | [brief-dark.png](screens/brief-dark.png) | [brief-light.png](screens/brief-light.png) | [A4 print view](screens/brief-print-a4.png) | P7 |
| Debrief | Interview round → Debrief tab; `GET/PUT /coach/readiness/rounds/{round_id}/debrief` | [debrief-draft-dark.png](screens/debrief-draft-dark.png) (draft) · [debrief-saved-dark.png](screens/debrief-saved-dark.png) (saved) | [debrief-saved-light.png](screens/debrief-saved-light.png) | — | P2 (form), P8 (suggestions) |

The screenshots were rendered at 1440 px wide with Inter and Roboto Mono from the design source in [source/](source/). The source files use the Claude Design canvas format (`<x-dc>`, `{{holes}}`, `<sc-for>`); read them for exact spacing, sizes and copy, but do not copy the markup into the app. Build with the existing React components.

Every Phase 2 route is under `/coach/readiness` (spec §12); the existing interviews and applications routers do not change. The Today page shows readiness actions by requesting `GET /coach/readiness/next-actions` alongside `/applications/next-actions` and merging the two lists in the frontend.

The design system is in [design-system/](design-system/): [brand-book.md](design-system/brand-book.md) (rules) and [tokens.json](design-system/tokens.json) (values).

## Rules for building these screens

1. **Use existing components first.** `Button`, `StatusBadge`, `Card`, `SectionCard`, `PageHeader`/`PageContainer`, `Skeleton`, `Icon`, `FormField` + `Input`, `Dialog`, `AlertDialog`, `Sheet` from `frontend/src/components/ui/`. Do not use the legacy `Badge`, `Textarea`, `Select` or `Label` styling in new screens: give text areas and selects the `Input` classes (`surface-2` fill, `border`, `radius-control`).
2. **Colours only through tokens** (`var(--surface)`, `var(--text-dim)` …). No hex values and no `brand-*` blues in new code.
3. **Copy is final.** Use the words in the screenshots and the glossary in spec §13.4. Sentence case; no exclamation marks.
4. **Both themes, phone width and keyboard.** Every screen works in dark and light, at 390 px wide without horizontal scroll, and with the keyboard alone (visible 3 px focus ring, real `<button>`/`<a>`/`<label>`).
5. **Instant first paint.** Deterministic content renders immediately; model text arrives later in an `aria-live="polite"` region with skeleton lines.
6. **Times.** Interview times come from the API in UTC (`Z`) and are shown in the display timezone with its abbreviation ("10:00 GMT"): `HATCH_DISPLAY_TIMEZONE` when set, else the browser's zone (spec §7.5).

## Readiness page

| Region | Build from | Data (spec) | Notes |
|---|---|---|---|
| Page title and tabs | `PageHeader`; tabs as links with `aria-current="page"` and a 2 px `accent` underline | — | Tabs: Sessions · Stories · Readiness |
| Next interview card | `Card`; `StatusBadge` (success "Brief ready"; info "Adding tips"; warning "Tips out of date" while re-queued tips are on their way); `Button` default "Open brief", outline "Plan my week" | §7.5, M4 coverage counts | Coverage chips: success "N ready stories", neutral "N could be stronger", warning with `target` icon "N with no story yet". No round: card says "Add your interview date to get a brief" |
| This week's plan | `SectionCard`; list rows with checkbox, title, sub-line, minutes in `font-mono` 12.5 px, optional outline `sm` button | §7.3, §8.3 | Auto-ticked practice items show a `checkCircle` in `success`, struck-through title and "Ticked automatically when you finished a session on {date}". Badge `info` "N of M done" |
| Patterns | `SectionCard`; one group per role family · interview type; each pattern a bordered block | §7.1, §8.1, §13.4 | Expanded pattern on `surface-2` shows **Why?** (dates, difficulty, level, report quote) and **Tips** (live region + 3 skeleton lines). Kinds: warning + `target` "Focus area suggestion", success + `checkCircle` "Strength", neutral "Mixed results", neutral "Needs more practice" (dashed border). Trend wording follows the difficulty guard (spec §7.1.4): badge `info` + `trending` "Improving", or text "Changed at an easier difficulty"; text "Getting weaker", or "Lower at a harder difficulty" (as on the Specificity pattern). Stable or mixed trends show no trend wording. Dismiss is an icon button with `aria-label="Dismiss this pattern"`. Stale patterns collapse under "Older patterns (N)" |
| Not enough practice | Group heading + one line + outline `sm` "Practise this role" | §7.1.2 forming | No empty state component here |
| Focus areas | `SectionCard`, "N of 3 in use", outline `sm` "Add" | §7.2, §8.2 | Each on `surface-2`; criteria rows with a 6 px bar (`surface-3` track, `accent` fill; `success` when met) plus "N of M" in `font-mono`, `role="progressbar"`. When all criteria are met: "Every criterion is met." + success `sm` "Mark achieved" |
| From your real interviews | `SectionCard` | §7.1.5 | Ships in P8; hidden until then. Kept visually separate from practice; icon `mic` for "asked in N", warning `target` for low self-rating, link "Draft a story". A signal needs N ≥ 2 |
| Footer line | text + link "What Hatch remembers" | §7.8 | |

States not drawn, to build from the same parts: cancelled round (brief "Archived", no debrief prompt), no sessions at all (one line and "Start a practice session"), tips unavailable ("Tips unavailable — try again" replacing the skeleton), AI off ("Turn on local AI for tips"), 409 on a focus-area edit (keep the draft, show "Reload and re-apply").

## Interview brief

| Region | Build from | Data (spec) | Notes |
|---|---|---|---|
| Breadcrumb, title, sub-line | links + `h1` 28 px | §7.5 header | Title: "{Round type} interview with {company}" |
| Actions | outline `Button` with `fileText` icon "Print brief". **No Refresh button**: the brief is assembled from current data on every open (spec D13) | S3 | Print uses a print stylesheet that matches [brief-print-a4.png](screens/brief-print-a4.png): one A4 page, black on white, no navigation |
| Round tabs | Brief · Debrief ("after the interview") | | |
| Status line | `StatusBadge` + one line; when tips exist, the time they were added | §8.4 | Enhancement state → badge: `none` or AI off → neutral "Ready"; `enhancing` → info "Adding tips"; `current` → success "Ready · tips added"; `outdated` → warning "Tips out of date" (old tips hidden; new ones are already queued, no user action); `unavailable` → neutral "Tips unavailable" with ghost `sm` "Try again"; `archived` → neutral "Archived" (read-only) |
| Likely questions | `SectionCard`, numbered rows, source sub-line, link "Open answer" / "Draft answer" | §7.5 §2 | Max 5 |
| Your best stories | `SectionCard`; each story on `surface-2` with success "Ready story", competency chips on `surface-3`, talking point, provenance line | §7.5 §3, §10 | Without enhancement the talking point line is absent and the provenance line is hidden |
| Watch-outs | `SectionCard`; warning icon, title, source line ("From your practice" / "From your real interviews"), one sentence | §7.5 §4 | Max 2. Real-interview watch-outs appear only after P8; before that, practice only. No linked practice session → "Practise for this role to get watch-outs" |
| Gaps | `SectionCard`; warning "No story yet" + outline `sm` "Draft a story" | §7.5 §5 | Max 2 |
| Questions to ask them | `SectionCard`, bulleted list | §7.5 §6 | Source line names CompanyResearch or "Suggested for this round type" |
| Logistics | `SectionCard`, definition list | §7.5 §7 | |

## Debrief

| Region | Build from | Data (spec) | Notes |
|---|---|---|---|
| Title and intro | `h1` "How did it go?" + one line | §7.6 | Says only the overall rating is needed |
| Overall and expectation | `fieldset`/`legend`; 44 px buttons with `aria-pressed`; selected = `accent` fill + `on-accent` text | §7.6 | Label beside the rating: Poor · Weak · Okay · Good · Great |
| Questions you were asked | checklist from the brief's likely questions; ticking reveals rating (36 px pressed buttons), "Story you used" select, one-line note on `surface-2` | §7.6 | Plus "Another question" input with outline "Add"; added questions show "Added by you" and have no `source_ref`. Link "Paste rough notes instead" (P8; notes ≤ 2,500 characters are saved with the debrief) |
| Went well / do differently | two text areas with Input styling | §7.6 | ≤ 1,000 characters each |
| Actions | default "Save debrief", ghost "Skip this one", polite status line | §8.5 | After save: "Saved. N questions added to this round." |
| Side panel, before save | `SectionCard` "When you save", three bullets | | |
| Side panel, after save | `SectionCard` "Suggestions from this debrief" with success "Saved"; each suggestion on `surface-2` with its own accept and "Not now" | §7.6 S2 | Only questions you added yourself that are not already in the Question Bank are suggested (questions ticked from the brief already come from it). Accept writes through Question Bank and story services (P8) |

## Known contrast issues in the design system

These come from the current tokens and are flagged in the brand book. Do not make them worse, and do not use the affected colours for small text that someone must read to act:

- `text-muted` is 3.9:1 on dark `surface`. The designs use `text-dim` for all secondary text.
- In light mode `accent`, `success` and `warning` are about 3:1 on white. Status badges always carry a word, and an icon where the colour carries meaning.
- `EmptyState`'s action button uses white on `accent` (2.2:1 in dark). New empty states use `on-accent`.
