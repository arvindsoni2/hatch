---
title: Hatch — Tailor prompts & skills review (CV/CL quality fix) — v2
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

# Hatch — Tailor prompts & skills review (CV/CL quality fix) — v2

> **Supersedes the 2026-06-08 v1 review.** Five items were corrected after verifying the code and reading the `gemma4:e2b` model card. Corrections are tagged **[CORRECTED v2]**.
> **For Claude Code:** implement P0 → P1 → P2. Use the project TDD loop (failing test → implement → green → commit). Paths and exact edits are given. This is a correctness/robustness job, not a restyle.

**Date:** 8 June 2026 · **Repo:** `arvindsoni2/hatch`
**Trigger:** `cv_v1_A.docx` + `cl_v1_A.docx` for *Enterprise Architect (Business Systems), Mace* — leaked placeholders, missing company name, `\textsterling` artefacts, blank skill labels, weak sector alignment.

---

## 0. The model is a deliberate edge choice — tune for it, don't replace it

The user's `primary_model` is **`gemma4:e2b`** (Gemma 4, "Effective 2B"): 2.3B effective params (5.1B with embeddings), 128K context, **512-token sliding window**, native `system` role, **configurable thinking** (`<|think|>`), native function-calling, Apache-2.0. It is a capable on-device reasoner — the goal is to make the pipeline robust enough to get good output from it, while offering an in-family upgrade path for users with spare hardware.

Current config (`llm_factory.py`): `num_ctx=16384` (good — input is not truncated), `format="json"` on JSON calls (good — constrained decoding), `request_timeout=300`, **`reasoning=False`** (thinking off), `temperature` default `0.3`. Two of these interact badly with the failures below — see **[CORRECTED v2] Task 5**.

---

## 1. Why prompt edits alone will not fix this

| Layer | Failure | Fixed by |
|---|---|---|
| **Plumbing** | JD-analysis prompt keys ≠ Pydantic schema → company name, rate, contract type, sector signals silently dropped | Task 1 |
| **Plumbing** | `SKILL.md` `instructions()` exists but is never injected into CV/CL/ATS prompts — skills are dead documentation | Task 2 |
| **Plumbing** | CV docx skill label reads `display_name`/`name`; data carries `category` → blank `:` labels | Task 10 |
| **Data** | `master_cv.json` is an unfilled, LaTeX-converted template (`PLACEHOLDER`, `XXXX`, `your.email`, `\textsterling`); nothing validates it pre-tailor | Tasks 3–4 |
| **Model** | A small reasoner is run with reasoning **off**, fed a huge JSON dump that overruns its 512-token attention locality | Task 5 |
| **Prompts** | Prompts permit bracketed placeholders, don't ground on company/sector, don't bridge transferable sector experience | Tasks 6–9 |

---

## 2. Defect → root-cause map (every visible flaw)

| Symptom | Root cause | Location |
|---|---|---|
| `[Company Name]` in body; `at the Company` in footer | JD prompt emits `company_context.name`; schema field is `company_name` → dropped → fallback | `jd_analysis.j2`, `schemas/tailor.py:24`, `docx_cl_builder.py:95` |
| `$\textsterling 500K` not `£500K` | LaTeX markup in `master_cv.json`; never normalised | user data + ingest |
| `PLACEHOLDER – Company A` printed | Unfilled master CV reproduced; validator ignores headers | user data + `cv_tailor.py` validator scope |
| `your.email@domain.com` / `+44 XXXX XXXXXX` | Placeholder personal block; no pre-flight validation | `tailor_service.py:_load_personal` |
| `CORE SKILLS` lines render `**:  **AWS…` | docx JS reads `display_name`/`name`; data has `category` | `templates/generate_cv_docx.js` + `docx_cv_builder.py` |
| Footer `… — CV     of` (blank numbers) | Word page-number **field codes** — don't evaluate in text extraction | `templates/generate_cv_docx.js` (likely **non-bug**, verify in Word) |
| Summary says "energy, aviation, finance"; job is **construction** | No sector-transfer guidance; JD `sector` partly dropped (Task 1) and unused | `cv_tailoring.j2`, `summary_rewrite.j2` |
| Generic, low-precision tailoring | Reasoning off + over-stuffed prompt vs 512-tok window | Task 5 + Tasks 6–9 |

---

## P0 — Plumbing (do first; model-independent, highest impact)

### Task 1 — Align `jd_analysis.j2` keys with the schema **[CORRECTED v2: split contract_type / education]**

Prompt and `schemas/tailor.py` diverge on six fields; Pydantic drops unknown keys, discarding the model's correct extractions.

Prompt key → required schema field:
- `company_context.name` → **`company_name`**
- `company_context.size_signals` → **`size`**
- `company_context.culture_signals` → **`culture_indicators`**
- `contract_details.rate` → **`rate_range`**
- `contract_details.type` → **add `contract_type: str | None = None` to `ContractDetails`** *(decision: preserve it — both CV and CL prompts hardcode "UK technology **contractors**", which is wrong framing for a permanent role like this Mace one; the value should drive that framing)*
- `requirements.education` → **drop from the prompt** *(decision: unused downstream — the CV's education comes from the master CV, not the JD; adding a schema field would be dead weight)*

- [ ] **Test (red):** `test_jd_analysis_schema.py` validates a blob using the prompt's documented keys and asserts `company_name == "Mace"`, `rate_range`, `sector`, and `contract_type` populate.
- [ ] **Implement:** rename the prompt keys to the real field names; add `contract_type` to `ContractDetails`; remove `education` from `jd_analysis.j2`. Add near `company_name`: *"the hiring organisation's name exactly as written (e.g. 'Mace'). If genuinely absent, use null — never a placeholder."*
- [ ] **Commit:** `fix(jd-analysis): align prompt keys with schema; add contract_type, drop unused education`

### Task 2 — Inject `SKILL.md` instructions into the generation prompts **[confirmed: injection gap]**

`instructions()` **exists** (`skill_loader.py:91`, `wrappers.py:25`) but has **zero callers** in `services/`, `agents/`, `routers/`. You're wiring an existing method, not writing one.

**Files:** `cv_tailoring.j2`, `cl_generation.j2`, `ats_keywords.j2`; `services/cv_tailor.py`, `services/cl_generator.py`, the ATS service.

- [ ] **Test (red):** the rendered CV prompt contains a distinctive `cv-tailoring/SKILL.md` sentence (e.g. "flag it as a gap rather than inserting it") when the loader is present.
- [ ] **Implement:** add optional `skill_instructions: str = ""` to each prompt, rendered in a `## SKILL GUIDANCE` block; in each service load `SkillLoader(...).instructions("cv-tailoring" | "cover-letter" | "ats-optimization")` and pass it in. Loader returns `""` for missing skills — keep it defensive. **Place the block immediately before the JSON schema at the end of the prompt** (see Task 5 — sliding-window locality).
- [ ] **Commit:** `feat(skills): inject SKILL.md guidance into CV/CL/ATS generation prompts`

### Task 3 — Pre-flight master-CV validation + markup normalisation

**Files:** `services/cv_tailor.py` (or new `services/master_cv_validator.py`), `services/resume_store.py`.

- [ ] **Test (red):** a master CV containing `PLACEHOLDER`, `XXXX`, `your.email`, `[...]`, or `\textsterling` returns a blocking validation error naming the offending fields.
- [ ] **Implement `validate_master_cv(cv) -> list[str]`:** scan personal block, summary, experience headers, achievements for placeholder tokens (`PLACEHOLDER`, `XXXX`, `TODO`, `[…]`, `your.email`, `your-profile`) and markup (`\textsterling`, `$…$`, `\&`). Call at the start of `CVTailor.tailor()`; if blocking, raise a typed error the router surfaces to the Review gate.
- [ ] **Implement `normalise_master_cv(cv)`:** `\textsterling`→`£`, strip `$…$`, `\&`→`&`, trim stray `**`. Run on resume ingest and as a safety net before tailoring.
- [ ] **Commit:** `feat(tailor): block tailoring on unfilled master CV; normalise LaTeX/markup`

### Task 4 — Make validation block, broaden scope, surface to UI

`_validate_no_fabrication` only fuzzy-checks achievement bullets, ignores summary/skills/personal, can't see placeholders, and only logs.

**Files:** `services/cv_tailor.py`, `routers/tailor.py`, frontend Review view.

- [ ] **Test (red):** a result whose `summary` contains `[Company Name]`, or any field a placeholder token, yields a **blocking** issue (not just a log); a fabricated achievement is flagged.
- [ ] **Implement:** scan `summary`, `skills[].items`, `certifications`, experience headers for placeholder tokens; keep the fuzzy achievement check but include the summary; return `{blocking: [...], advisory: [...]}`; surface `blocking` in the API + Review gate so the user sees why a document was withheld.
- [ ] **Commit:** `fix(tailor): broaden + surface fabrication/placeholder validation in the Review gate`

### Task 5 — Tune the pipeline for `gemma4:e2b` **[CORRECTED v2: was "switch to primary model" — that premise was wrong]**

**Correction:** the tailor already runs on the primary model. `ClaudeClient.complete()` → `get_primary_model()`; `complete_json()` → `get_json_model()` (Ollama: `primary_model` + `format=json`; other providers delegate to primary). It is *explicitly* primary — primary is simply set to `gemma4:e2b`. So **no routing change.** Instead, make the small reasoner succeed:

- [ ] **5a — Enable thinking for structured tasks (highest-value lever).** `llm_factory.py` sets `reasoning=False`; e2b is a reasoner and its schema adherence/grounding improve with reasoning on. Enable thinking for JD-analysis and tailoring calls (Gemma 4: prepend `<|think|>` to the system prompt, or pass the provider's reasoning flag). **You must update the thought-stripping** — `claude_client.py` strips `<think>…</think>`, but Gemma 4 emits a channel form (`<|channel>thought … <channel|>`). Extend the regex/strip before JSON parsing. Gate behind a profile flag (`llm.reasoning: true`) and keep it **off for latency-sensitive triage**. Test that thoughts are stripped and JSON still parses.
- [ ] **5b — Respect the 512-token sliding window: stop dumping giant JSON.** Even with 16K context, attention locality is ~512 tokens, so a full `master_cv | tojson` + `jd_analysis | tojson` dump dilutes the rules. (i) Inject only the **relevant** master-CV slices (the roles/skills being tailored), not the whole document. (ii) Pass a **compact** JD summary (must-haves, company, sector, top keywords) rather than the full analysis JSON. (iii) Keep the **rules + JSON schema at the very end** of the prompt, closest to generation (also reorder per Task 6).
- [ ] **5c — Decompose the big single-shot call.** `cl_generator.py` already multi-steps; do the same for the CV (summary → per-role bullets → skills) so each output is small and reliable on a 2B model. Smaller, focused completions beat one large schema on edge models.
- [ ] **5d — Sampling.** Google's card recommends `temperature=1.0, top_p=0.95, top_k=64`; the code uses `0.3`. For constrained JSON extraction a lower temperature is usually safer, and `format=json` already constrains structure — so keep tailoring temperature low/moderate, but expose `top_p`/`top_k` so users can match the card. Don't over-tune; 5a–5c matter more.
- [ ] **5e — Optional in-family upgrade (offer, don't force).** Add a soft note in docs/example profiles: `gemma4:e4b` (~9.6 GB, still on-device) roughly doubles structured/agentic accuracy over e2b — MMLU-Pro 60.0→69.4, Tau2 24.5→42.2, GPQA 43.4→58.6, BigBench-Extra-Hard 21.9→33.1. Suggest e4b as `primary_model` for document generation where hardware allows, keeping e2b for triage. Add a soft warning in `llm_factory` when `primary_model` matches a tiny pattern *and* reasoning is disabled.
- [ ] **Commit:** `fix(llm): enable reasoning + trim context for gemma4:e2b; decompose CV gen; document e4b upgrade`

---

## P1 — Prompt hardening

### Task 6 — `cv_tailoring.j2`
- [ ] **Placeholder/markup ban** in CRITICAL RULES: never emit bracketed placeholders or LaTeX (`\textsterling`, `$…$`); if a value is unknown, omit the clause; write `£` for GBP.
- [ ] **Explicit grounding vars:** pass `target_company`, `target_sector`, `contract_type`, `top_requirements` as first-class template vars (don't make the model mine the JSON). Replace hardcoded "contractor" framing with `contract_type`.
- [ ] **Sector-transfer guidance** (fixes energy/aviation/finance → construction): when the candidate's sectors differ from the target, do **not** claim target-sector experience — surface transferable proof points (regulated-industry delivery, large-programme governance, data-platform consolidation) in the target sector's language.
- [ ] **Skill categories:** require non-empty `category`; give concrete labels ("Cloud & Infrastructure", "Data & AI", "Architecture & Design", "Delivery & Leadership").
- [ ] **Small-model structure (ties to 5b):** one-line task statement first; short imperative bullets; **JSON schema + rules last**; one tiny worked example of a tailored bullet.

### Task 7 — `cl_generation.j2` + `docx_cl_builder.py`
- [ ] Pass `company_name` + `sector` as explicit vars. Rule: use `{{ company_name }}` verbatim in paragraph 1; if empty, open with role + sector — never "[Company Name]" or "the Company".
- [ ] Same placeholder/markup ban as Task 6.
- [ ] Keep `docx_cl_builder.py:95` `"the Company"` only as last resort (Task 1 makes it rare); test that a populated `company_name` reaches the docx payload.

### Task 8 — `summary_rewrite.j2`
- [ ] Add sector-transfer guidance + placeholder ban; ensure it receives `target_sector`/`target_company`.

### Task 9 — `ats_keywords.j2`
- [ ] `missing_critical` must be a subset of JD must-haves; suggestions must reference real master-CV content (no "add X" where X isn't in the master CV). Wire `instructions()` from `ats-optimization/SKILL.md` (Task 2).

### Task 10 — CV docx builder **[CORRECTED v2: skill label is a field mismatch; footer likely a non-bug]**
`generate_cv_docx.js` is a **Node script** at `backend/app/templates/generate_cv_docx.js`, run via `subprocess.run(["node", …])` from `docx_cv_builder.py`.
- [ ] **Skill label (real bug):** the JS reads `skillGroup.display_name || skillGroup.name`, but the data carries **`category`** → label is always `""`, printing `":  "`. Fix: in `docx_cv_builder.py._build_spec` map skills to `{"display_name": s["category"], "items": s["items"]}` (or have the JS also read `skillGroup.category`), **and** guard the JS so an empty label never prints a bare `:`.
- [ ] **Footer (verify first):** the JS uses real Word field codes (`PageNumber.CURRENT … PageNumber.TOTAL_PAGES`); these don't evaluate in plain-text extraction (which is what the uploaded doc showed) but **do** render in Word/LibreOffice. Open the file in a real Word client before changing anything; only add a static fallback if it genuinely renders blank there.

---

## P2 — Skill file content (now that Task 2 injects it)

### Task 11 — `cv-tailoring/SKILL.md`
- [ ] Add a "never emit placeholders or markup" rule and a **sector-transfer** subsection; state the skill-category label convention from Task 6.

### Task 12 — `cover-letter/SKILL.md` + wire tone variant **[CORRECTED v2: variant B is defined; selection is the gap]**
Variant B exists in `cover-letter/resources/tone_examples.md`; `cl_generator.py` accepts `variant` but defaults to `"A"` and nothing maps sector → variant.
- [ ] Implement `select_tone_variant(jd_analysis) -> "A" | "B"` and pass it into `cl_generator.generate(...)` instead of hardcoded `"A"`:
  - **A (formal):** finance, insurance, legal, government/public sector, healthcare, energy/utilities, defence, **construction/infrastructure/engineering** → Mace = A (correct).
  - **B (conversational):** tech, startups, scale-ups, creative/media/agency; or `tone_analysis.formality == "informal"`, or `culture_indicators` like "fast-paced"/"casual"/"startup". Default **A** when ambiguous.
- [ ] Variant B shape (from `tone_examples.md`): hook tied to a recent company initiative ("When I saw the {role} at {company} … your work on {recent_initiative} …"); informal close ("I'd love to talk about how I could help {company} {goal} — reach me at {email}"); still bans "utilise"/"leverage"/"synergy" and salary mentions.
- [ ] Add company-name handling + placeholder ban to the SKILL.

### Task 13 — `ats-optimization/SKILL.md`
- [ ] Clarify suggested keywords must be grounded in existing master-CV evidence (surface a real skill, never invent one); reference `scripts/ats_lint.py` as the deterministic check.

---

## Data hygiene (user action; document in onboarding/README)
The leaked `PLACEHOLDER` / `XXXX` / `your.email@domain.com` / `$\textsterling` originate in the **user's `master_cv.json`** (an unfilled, LaTeX-converted template). Tasks 3–4 stop the system shipping such output, but the master CV must still be completed — ensure onboarding/resume-upload parses a real CV into `master_cv.json` and runs `normalise_master_cv` on save.

---

## Acceptance tests (use the Mace case as the fixture)
- [ ] With a JD naming "Mace" and a complete master CV, the cover letter contains "Mace" in paragraph 1 and the footer — never "[Company Name]"/"the Company".
- [ ] No generated document contains `PLACEHOLDER`, `XXXX`, `your.email`, `[...]`, or `\textsterling`; currency renders `£`.
- [ ] CV `CORE SKILLS` lines have non-empty category labels and no stray `:`.
- [ ] Incomplete master CV → tailoring **blocked** with field-level message in the Review gate (no broken docx).
- [ ] JD analysis populates `company_name`, `sector`, `rate_range`, `contract_type`; a schema-vs-prompt key test guards against drift.
- [ ] Rendered CV/CL prompts contain injected SKILL.md guidance.
- [ ] With reasoning enabled, Gemma 4 thought channels are stripped and JSON still parses; tailoring output is grounded in the (trimmed) injected master-CV slices.
- [ ] `select_tone_variant` returns "A" for Mace (construction); a tech-sector fixture returns "B".

## Suggested commit order
1. `fix(jd-analysis): align prompt keys; add contract_type, drop education` (T1)
2. `feat(skills): inject SKILL.md guidance into generation prompts` (T2)
3. `feat(tailor): block on unfilled master CV; normalise markup` (T3)
4. `fix(tailor): broaden + surface fabrication/placeholder validation` (T4)
5. `fix(llm): enable reasoning + trim context for gemma4:e2b; decompose CV gen; document e4b` (T5)
6. `fix(prompts): placeholder ban, company/sector/contract grounding, sector-transfer, skill categories` (T6–T9)
7. `fix(docx): map skill category label; verify footer fields` (T10)
8. `feat(cover-letter): wire select_tone_variant (A/B by sector)` (T12)
9. `docs(skills): strengthen cv-tailoring / cover-letter / ats SKILL.md` (T11, T13)
