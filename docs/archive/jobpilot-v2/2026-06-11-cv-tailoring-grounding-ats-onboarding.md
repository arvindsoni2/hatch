---
title: Hatch — CV Tailoring Grounding, ATS Alignment, Onboarding Data-Flow & Scout/Scorer Criteria
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

# Hatch — CV Tailoring Grounding, ATS Alignment, Onboarding Data-Flow & Scout/Scorer Criteria

**Date:** 2026-06-11
**Repo:** https://github.com/arvindsoni2/hatch (commit `4d208ab`)
**Status:** Ready for Claude Code implementation
**Trigger:** Tailored CV generated with qwen3.5:4b contained fabricated employers ("PLACEHOLDER — Company A/B/C"),
an invented "SC Cleared Technical Architect" identity, and achievements that do not exist in the
candidate's real CV. This spec fixes the root causes, not the symptom.

---

## How to use this spec

Five parts. **Part 1 (grounding) is the fix for the garbage CV — do it first and in order; G-1 → G-3
are each independently shippable but G-1 is the root cause.** Parts 2–5 follow. Repo TDD convention
throughout: failing test → implement → pass → commit.

**Product rule this spec encodes (from the maintainer, verbatim intent):**
> Onboarding answers (domains, proof points, skills, preferences) exist to improve **job search and
> scoring**. The **uploaded master CV is the only source of truth for tailoring**. Tailoring =
> rewording/rephrasing/reordering the master CV against the JD for ATS alignment. Nothing may be
> added to a tailored CV that cannot be traced to the master CV.

---

## Root-cause chain (read before coding)

The fabricated docx was not primarily a model-quality problem. Five compounding defects, in causal order:

1. **The user's CV never reaches the tailor.** `routers/resume.py` `/upload` parses the uploaded
   .docx/.pdf and writes it to `data/master_cv.json` (matching `profile.master_cv_path`,
   `schemas/profile.py:164`). But `cv_tailor.py:21`, `tailor_service.py:34`,
   `question_generator.py:16`, and `feedback_generator.py:22` all read a **hardcoded**
   `backend/app/templates/master_cv.json` — a different file that, in a real deployment, contains a
   placeholder skeleton ("PLACEHOLDER — Company A", "your.email@domain.com"). The tailor literally
   tailored the template.
2. **Even on the right path, the shapes don't match.** The upload parser emits
   `{_raw_sections, <loose section text>, skills.extracted}` — but `CVTailor` consumes
   `experience[{role, company, period, achievements:[{text}]}]`, `summary_variants`,
   `certifications`. There is no structured-parse step, so there is nothing for the
   fabrication validator to ground against.
3. **"Blocking" issues don't block.** `CVTailor._validate_no_fabrication()` sets
   `result.blocking_issues` and logs "document withheld" — but `TailorService.generate_cv()`
   never reads `blocking_issues`; it builds and persists the .docx unconditionally. No frontend
   component consumes `blocking_issues` either (grep: only the schema and the setter).
4. **The prompt seeds fabrication.** `prompts/cv_tailoring.j2` contains (a) a WORKED EXAMPLE with
   the maintainer's real £500K / 2,000-engineer bullet — which the model copied verbatim into the
   output — and (b) a fixed skill-category list ("Security & Compliance", "Architecture & Design")
   that nudges the model toward an architect/security identity. The "SC Cleared" framing came from
   the seeded demo job in `seed.py:80` ("Security Architect — SC Cleared") interacting with rule 7
   / sector-transfer guidance under a 4B model.
5. **The ATS retry loop amplifies invention.** `generate_cv()` re-tailors when ATS < 75 by feeding
   `suggest_improvements()` (which includes *missing keywords*) back as instructions — for a small
   model this reads as "add these keywords", i.e. an instruction to fabricate skills.

A 4B model given a placeholder CV, a realistic worked example, a keyword-stuffing retry loop, and
no enforced validation will reliably produce exactly the document that was produced.

---

# Part 1 — Grounding: the master CV becomes the single source of truth

### G-1 — [CRITICAL] One master CV path, resolved from profile, everywhere

**Files:** `services/cv_tailor.py:21`, `services/tailor_service.py:34`,
`services/question_generator.py:16`, `services/feedback_generator.py:22`, `routers/resume.py`

- [ ] Test first (`tests/test_services/test_master_cv_path.py`): patch `load_profile()` to return
      `master_cv_path="/tmp/xyz/master_cv.json"`; assert `CVTailor._load_master_cv()` and
      `tailor_service._load_master_cv()` read that path. Watch fail (they read `templates/`).
- [ ] Add `services/master_cv_store.py` with a single `resolve_master_cv_path() -> Path` (from
      `profile.master_cv_path`, default `./data/master_cv.json`, env-overridable via `DATA_DIR`)
      and `load_master_cv() -> dict` (no `lru_cache` keyed on nothing — cache with mtime check so a
      re-upload takes effect without restart; the current `@lru_cache(maxsize=1)` in `cv_tailor.py`
      serves stale CVs for the process lifetime).
- [ ] Replace all four hardcoded `_MASTER_CV_PATH` constants with calls into `master_cv_store`.
      Delete `templates/master_cv.json` handling entirely; if the file is absent, raise a typed
      `MasterCVMissingError` whose message tells the user to upload a CV in Settings → Resume
      (surface as HTTP 409 with that detail, not 500).
- [ ] Test: with no CV uploaded, `POST /tailor/cv` returns 409 + actionable message; after upload,
      tailoring reads the uploaded content. All existing tailor tests updated to fixture the new
      store.

**Commit:** `fix(tailor): resolve master CV from profile.master_cv_path — stop reading template skeleton`

### G-2 — [CRITICAL] Structured CV parsing with user review (parse → confirm → store)

The current `/upload` parse is shallow (raw section text). Tailoring needs structured entries the
validator can diff against. **Do not let the LLM invent structure silently — parse, then show the
user what was extracted, let them correct it, then persist.**

**Files:** `routers/resume.py`, new `services/cv_parser.py`, new prompt `prompts/cv_parsing.j2`,
`frontend/src/app/settings/resume/page.tsx`

- [ ] New `services/cv_parser.py`: `parse_cv_text(text) -> MasterCV` using the primary model via
      `get_json_model()` with a strict extraction prompt: *extract only what is present; never
      infer, never fill gaps; unknown → empty string; copy company names, dates, metrics, and
      certification names verbatim*. Output schema = the master CV schema `CVTailor` already
      consumes (`personal`, `summary_variants` — seed with the CV's own summary as variant
      "default", `experience[{role, company, period, achievements:[{text}]}]`, `skills`,
      `certifications`, `education`).
- [ ] Post-parse verbatim check (cheap, deterministic): every extracted `company`, `role`,
      certification string, and every number/£-figure in every achievement must appear as a
      substring (case/whitespace-normalised) of the raw CV text. Violations → drop the field to
      empty + add to a `parse_warnings` list returned to the UI. This makes the parser itself
      hallucination-proof.
- [ ] `/upload` pipeline becomes: extract text (existing) → `parse_cv_text` → return parsed JSON +
      warnings to the frontend **without persisting**. New `POST /resume/confirm` persists the
      (possibly user-edited) structured JSON to `master_cv_path`, runs `validate_master_cv`, and
      invalidates the store cache. Keep `save_resume_text(text)` (raw text still feeds semantic
      scoring — correct separation).
- [ ] Frontend Settings → Resume: render the parsed structure in an editable review form
      (experience entries, bullets, skills, certs) with warnings highlighted; "Confirm & Save"
      calls `/resume/confirm`. This is the human-in-the-loop gate the product principle requires.
- [ ] Tests: parser drops a company name not present in source text; round-trip upload→confirm
      yields a CV that passes `validate_master_cv`; tailor consumes it.

**Commit:** `feat(resume): structured CV parsing with verbatim grounding check and user confirmation`

### G-3 — [CRITICAL] Blocking issues actually block, and the user sees why

**Files:** `services/tailor_service.py` (`generate_cv`, `generate_cover_letter`), tailor router,
frontend tailor/review components

- [ ] Test first: tailored result with non-empty `blocking_issues` → `generate_cv` raises
      `HTTPException(422)` carrying the issues; **no .docx is written, no document row created**.
- [ ] Implement the gate in both `generate_cv` and `generate_cover_letter` (the CL path calls
      `tailor()` too). Error payload: `{detail: "Tailored CV failed grounding checks",
      issues: [...]}`.
- [ ] Frontend: render the 422 issues in the tailor/review UI with a "what to do" hint (usually:
      fix master CV or re-run). Never show a silent failure or a generic toast.
- [ ] Also write `blocking_issues`/`fabrication_warnings` into `ats_details` (or a new
      `grounding_report` column) on the document row for the advisory case, so the Review gate can
      display warnings on documents that did generate.

**Commit:** `fix(tailor): enforce blocking grounding issues — withhold document and surface reasons`

### G-4 — [HIGH] Rebuild the tailoring prompt as reword-only, per-section, seed-free

**Files:** `prompts/cv_tailoring.j2`, `services/cv_tailor.py`

The single "generate the whole CV as JSON" call is the wrong shape for a 4B model. Constrain the
degrees of freedom: the model rewords *given* text; it never authors structure.

- [ ] Remove the worked example containing the maintainer's real achievement (this is also
      HC-2-adjacent PII leakage). Replace with a fully generic pair:
      *Master: "Improved deployment process at AcmeCo, saving time" → Tailored: "Streamlined CI/CD
      deployment pipeline at AcmeCo, cutting release time 30%"* — **and** an explicit anti-example:
      *"If the master bullet has no metric, do NOT invent one — reword without a number."* Delete
      current rule 6 ("Every achievement must include a quantified metric") — it is a direct
      fabrication instruction whenever the master bullet lacks a metric.
- [ ] Make skill-category labels conditional: derive candidate categories from the master CV's own
      skill groups; the fixed five-label list (incl. "Security & Compliance") goes, or becomes
      "use the candidate's existing category names".
- [ ] Restructure generation as **per-section calls** (summary; then each selected experience
      entry; then skills ordering; certifications are pass-through, reordered only):
      - Each experience call receives ONLY that entry's master bullets and the compact JD, and must
        return the same number (or fewer) bullets, each tagged with the index of the master bullet
        it rewords (`source_index`). `role`, `company`, `period` are **copied by code, not
        generated** — remove them from the model's output surface entirely.
      - Summary call: rewrite the selected `summary_variant` (existing
        `_select_best_summary_variant`) embedding 2–3 JD keywords **that already appear in the
        master CV skills/experience**; keywords not present in the master go to `keyword_misses`,
        never into the text.
      - Skills call: reorder/select from master skill items only; output must be a subset
        (validated in code — anything not in master is dropped, logged as advisory).
- [ ] Keep `_select_relevant_cv_slices` (top-3 experience selection) but make `personal` and
      header fields code-copied into the final `TailoredCVResult`, never round-tripped through the
      LLM. Note for the docx builder: `_load_personal()` moves to `master_cv_store` (G-1).
- [ ] Tests: per-section calls receive only their slice; a bullet output without a valid
      `source_index` is rejected; role/company/period in the result byte-match the master CV.

**Commit:** `refactor(tailor): per-section reword-only generation; structural fields copied by code`

### G-5 — [HIGH] Entity-level grounding validator (replace fuzzy-only check)

**Files:** `services/cv_tailor.py` (`_validate_no_fabrication`), new
`services/grounding_validator.py`

`fuzz.partial_ratio < 70` is advisory-only and misses exactly what happened (whole invented
employers score "fine" against nothing). Replace with deterministic entity checks:

- [ ] **Blocking** checks against the master CV:
      - every `experience.company` and `experience.role` must exist verbatim in master (post-G-4
        these are code-copied, so this is a regression tripwire);
      - every numeric/currency token in any tailored bullet or summary (`£3M`, `99.99%`, `10M+`,
        `2,000+`) must appear in the *source* master bullet (per `source_index`) — numbers are
        where small models fabricate hardest;
      - every certification string must exist in master certifications;
      - clearance/eligibility claims ("SC Cleared", "DV", "security clearance") may appear **only
        if** present in the master CV text;
      - placeholder patterns (existing `_PLACEHOLDER_PATTERNS`) — keep, stays blocking.
- [ ] **Advisory**: keep the fuzzy similarity pass per bullet (against its `source_index` bullet
      specifically, not max-over-all — much sharper signal), threshold configurable.
- [ ] Unit tests using the real failure as a fixture: a tailored result containing "SC Cleared
      Technical Architect", "Company B (Aviation Sector)", and a "£3M programme" bullet against a
      master CV without them → 3+ blocking issues, document withheld (integration with G-3).

**Commit:** `feat(tailor): deterministic entity-grounding validator — numbers, employers, certs, clearances`

### G-6 — [MEDIUM] ATS retry loop must not instruct fabrication

**Files:** `services/tailor_service.py`, `services/ats_optimiser.py`

- [ ] Partition `suggest_improvements()` output: keyword suggestions are filtered to those
      **present in the master CV** (skills items + experience text) before being fed to the
      re-tailor pass; unmatched JD keywords are reported to the user as genuine gaps ("the JD wants
      Terraform; your master CV doesn't mention it — add it to your master CV only if true").
- [ ] Re-tailor instruction template: "Increase coverage of these keywords *which the candidate
      already has*: [...]. Do not introduce any other new terms."
- [ ] Surface the final ATS report in the UI with three buckets: embedded, available-but-unused
      (actionable), and not-in-master (honest gap). This is the ATS-compliance feature the product
      actually needs — coverage you can truthfully claim.
- [ ] Test: a JD keyword absent from master never appears in the re-tailor instructions.

**Commit:** `fix(ats): retry loop only reinforces keywords grounded in the master CV`

---

# Part 2 — ATS scoring refinements (current: 40% algorithmic keyword match + 60% LLM semantic)

### ATS-1 — [MEDIUM] Trust the deterministic component more on small models

`ats_optimiser.score()` weights the LLM semantic judgment at 60%. With qwen3.5:4b as judge, the
semantic score is noisy and the *deterministic* keyword/format checks are the reliable part.

- [ ] Make the weights config-driven (`profile.scoring.ats_weights`, default unchanged for cloud
      providers) and flip to 70% algorithmic / 30% semantic when `provider == "ollama"` and the
      primary model matches the tiny/small patterns in `llm_factory`.
- [ ] Extend the algorithmic side (all deterministic, no LLM): must-have keyword coverage weighted
      2× over nice-to-have; exact-section presence checks (summary, skills, experience,
      certifications); date-format consistency; bullet length bounds; contact-block completeness
      from `personal`. These mirror what real ATS parsers actually reward.
- [ ] Test: scores reproducible without any LLM call when semantic fails (existing fallback keeps
      working).

**Commit:** `feat(ats): deterministic ATS checks weighted up for small local models`

---

# Part 3 — Onboarding flow: collect for search, gate tailoring on the CV

Current wizard steps (`frontend/src/app/onboarding/page.tsx`): AboutYou → Market → Pay →
Eligibility → Skills (+domains, proof points) → AI Provider → Review. **There is no CV upload step**
— upload lives only in Settings → Resume — so a user completes onboarding and can reach tailoring
with no master CV at all (which, combined with the Part-1 bugs, produced the placeholder docx).

### OB-1 — [HIGH] Data-use contract — encode and display it

- [ ] Add a `docs/data-flow.md` table and a short per-step caption in the wizard:

      | Onboarding input | Used by |
      |---|---|
      | Target roles, locations, eligibility, rate range | Scout search params, Scorer triage + rate/location dims |
      | Skills (primary/secondary), preferred domains | Scorer skill/experience dims, local scorer keywords |
      | Proof points | Scorer context + semantic-scoring fallback text (`resume_store` synthesis) — **never tailoring** |
      | Master CV upload | **Sole source for tailoring**; full text also feeds semantic scoring |

- [ ] Code-level enforcement of the bolded rule: grep-test (pytest collecting the prompt render)
      asserting profile `proof_points` and `domains` are not interpolated into `cv_tailoring.j2`
      or per-section prompts (they currently aren't — this is a tripwire so they never are).
- [ ] Wizard copy on the Skills/proof-points step: "These improve how jobs are found and scored.
      Your CV — uploaded next — is the only source for generated documents."

**Commit:** `docs+test(onboarding): encode search-vs-tailoring data boundaries`

### OB-2 — [HIGH] Add the CV upload step to onboarding; gate tailoring until confirmed

- [ ] New `StepResume` between Skills and AI Provider, reusing the Settings → Resume
      upload+review component from G-2 (parse → review → confirm). Skippable with an explicit
      "Skip — search only" choice that records `cv_confirmed=false`.
- [ ] Backend gate: tailor endpoints return 409 (`MasterCVMissingError` from G-1) until a confirmed
      master CV exists. Frontend: tailor buttons disabled with tooltip "Upload your CV in Settings
      → Resume to enable tailoring" when status says no CV.
- [ ] Reorder rationale: skills entered in Step 5 can be pre-filled from the parsed CV if the user
      uploads first — optional enhancement: offer "import skills from CV" on StepSkills when a
      parsed CV exists.
- [ ] Tests: wizard completes via skip path; tailoring blocked until `/resume/confirm`;
      onboarding completion with upload yields tailorable state.

**Commit:** `feat(onboarding): CV upload+review step; tailoring gated on confirmed master CV`

### OB-3 — [MEDIUM] Trim/clarify questions that don't serve search or tailoring

- [ ] Review each wizard field against the OB-1 table; any field consumed by nothing (audit:
      `culture` style questions, unused free-text) is either wired into the scorer prompt or cut.
      Keep the wizard ≤ 7 steps including the new resume step.
- [ ] Per-question helper text states which agent uses the answer (one line, e.g. "Used by the
      Scorer to weight seniority fit").

**Commit:** `refactor(onboarding): every question maps to a consumer; inline data-use captions`

---

# Part 4 — Scout & Scorer criteria: current state and improvements

## What the code does today (for the record)

**Scout** (`agents/scout_agent.py`) applies **no relevance criteria of its own**: it runs the
scrapers enabled in `profile.job_boards[]` (each with its own `search_params` — keywords/filters
per board), deduplicates via `DedupService`, and emits `job_discovered` events. All filtering is
the Scorer's job.

**Scorer** (`agents/scorer_agent.py`) — two tiers, four methods (`auto|llm|local|hybrid`):
- **Triage** (your qwen3.5:0.8b): prompt gives candidate title, years, target roles, target
  locations + job title/company/location/first 500 chars of description → boolean
  `relevant`. Reject rule: junior roles, unrelated domains, clearly out-of-location. Pass:
  "anything plausibly matching".
- **LLM scoring** (your qwen3.5:4b... actually primary model): four weighted dimensions from
  profile — skill_match, experience_match, rate_match, location_match → weighted overall;
  context = primary/secondary skills, preferred domains, proof-point summaries, rate range,
  locale context, JD first 3,000 chars; returns keyword_matches/misses.
- **LLM-judge variant**: holistic recruiter-style prompt with the **full resume text**
  (`resume_store` — uploaded CV text, or synthesized from proof points when no CV exists) +
  JD; explicitly credits transferable titles.
- **Local scorer** (`tools/local_scorer.py`): zero-LLM keyword matching with a synonym map +
  word-boundary matching, same four dimensions.
- **Semantic scorer** (`tools/semantic_scorer.py`): all-MiniLM embeddings, resume text vs JD.

## SC-1 — [HIGH] Triage hardening for a 0.8B model

A 0.8B triage model is the cheapest component and the most error-prone. Reduce what it must decide:

- [ ] **Deterministic pre-triage before any LLM call** (new `tools/pre_triage.py`): title-level
      synonym match against target_roles (reusing the SC-2 synonym map) and location allowlist
      check. Clear title match + location OK → skip LLM triage, mark relevant. Clear mismatch on
      both → skip LLM, mark irrelevant with reason. Only the ambiguous middle goes to the 0.8B
      model. Saves CPU and removes the model from easy cases.
- [ ] Constrain the LLM triage to the smallest possible output: keep `_TriageResult` but add 2
      few-shot examples (one pass, one reject) to the prompt — few-shot matters far more at 0.8B
      than instructions do. Ensure `think=False` on this call (LLM-2 in the 2026-06-10 audit spec).
- [ ] **Log every rejection** with reason to a reviewable `triage_rejections` view (UI: simple list
      under Jobs → Filtered out, with a "rescore" button). False negatives are invisible today —
      this is the safety valve for a tiny model silently discarding good jobs.
- [ ] Test: pre-triage passes/rejects without LLM; ambiguous goes to LLM; rejection rows visible
      via API.

**Commit:** `feat(scorer): deterministic pre-triage + few-shot 0.8B triage + reviewable rejections`

## SC-2 — [HIGH] Synonym map is developer-biased — extend to delivery/PM/architecture

`_SKILL_SYNONYMS` covers k8s/react/node — none of the vocabulary of this product's actual first
user (delivery lead) or the locales claimed:

- [ ] Add delivery/PM/architecture families: project manager ↔ programme/program manager ↔
      delivery manager/lead; product owner ↔ PO; scrum master ↔ SM; agile coach; solutions
      architect ↔ solution architect ↔ technical architect; programme ↔ program (UK/US);
      PRINCE2, SAFe, scaled agile; CI/CD already present; stakeholder management; PMO.
- [ ] Move the map from a Python literal to a data file (`skills/synonyms.yaml`) merged with
      optional per-locale extensions in `locales/*.yaml` — aligns with HC-pattern from the
      2026-06-10 audit (config over code) and lets users extend it.
- [ ] Test: "Programme Manager" JD matches "Project Manager" target; map loads from YAML.

**Commit:** `feat(scorer): delivery/architecture synonym families; synonyms move to data file`

## SC-3 — [MEDIUM] Rate parsing and dimension honesty

- [ ] `rate_match` currently leans on the LLM reading `rate_text`. Add deterministic parsing first
      (per-locale currency symbols/`per day|annum|hour` patterns; reuse the locale currency data
      from audit HC-1); pass the parsed normalised rate into the prompt, and score rate_match in
      code when parsing succeeds (LLM only when ambiguous). For "rate not stated" return a neutral
      0.5 with `reasoning` flag, never a hallucinated judgment.
- [ ] Surface per-dimension scores + keyword_misses on the job card (the data already exists in
      `JobScore`) so the user can see *why* a job ranked where it did — this is the
      criteria-transparency the product is missing.
- [ ] Test: "£550–650/day outside IR35" parses; "competitive salary" → 0.5 + flag.

**Commit:** `feat(scorer): deterministic rate parsing; per-dimension transparency on job cards`

## SC-4 — [MEDIUM] Default pipeline for CPU-only: semantic recall → judge top-N

Consistent with the Phase-0 redesign direction: with local models, make the default `hybrid` path
**embeddings-first** — semantic-score everything (cheap, deterministic, already implemented),
LLM-judge only the top `hybrid_llm_top_pct`. Confirm `auto` resolves to this when
`provider == "ollama"`; add a profile comment documenting the flow. Test: ollama profile + auto →
hybrid with semantic pre-rank.

**Commit:** `feat(scorer): embeddings-first hybrid as the CPU default scoring path`

---

# Part 5 — Seed data hygiene

- [ ] `seed.py` demo jobs ("Security Architect — SC Cleared", etc.) must be clearly marked demo
      (`is_demo=True` on JobPosting or a `[DEMO]` title prefix) and excluded from tailoring
      (tailor endpoint refuses demo jobs with a clear message) — a user tailoring against seed
      data is how an invented identity leaks into a real document.
- [ ] Provide a "Clear demo data" action in Settings.
- [ ] Test: tailoring a demo job → 409.

**Commit:** `fix(seed): demo jobs flagged and excluded from document generation`

---

## Suggested execution order

1. **G-1** (path fix — root cause; smallest diff, biggest effect)
2. **G-3** (blocking gate — safety net while the rest lands)
3. **G-2** (structured parse + confirm — unblocks real grounding)
4. **G-4 + G-5** (reword-only prompt + entity validator — do together)
5. **G-6, ATS-1** (honest ATS loop)
6. **OB-1, OB-2** (data contract + wizard step)
7. **SC-1 → SC-4** (scout/scorer criteria)
8. **Part 5, OB-3** (hygiene/polish)

## Interactions with the 2026-06-10 audit spec

- G-4's worked-example removal supersedes/extends **HC-2** (maintainer PII in placeholders).
- SC-1's `think=False` depends on **LLM-2** (model-aware thinking handling).
- SC-2's YAML synonym move follows the **HC-3** config-over-code pattern.
- Per-locale rate parsing in SC-3 reuses **HC-1** currency data.

## Open questions

1. **Parser model for G-2** — use the primary model (qwen3.5:4b) for extraction, or is extraction
   important enough to recommend a one-off cloud call when a key is configured? Recommending:
   local by default with the verbatim check as the guarantee; the check is what makes it safe.
2. **Per-section calls (G-4) latency** — 4–6 small calls instead of 1 big one. On CPU this is
   roughly latency-neutral (output tokens dominate) and fits the 202+poll pattern, but confirm
   acceptable wall-clock in testing.
3. **`summary_variants`** — keep the multi-variant concept (parsed CV yields one summary) or let
   users author variants in the master CV editor? Recommending: single "default" variant from
   parse; editor allows adding more later.
4. **Triage rejection retention** (SC-1) — how long to keep rejection rows? Suggest 30 days,
   configurable.
