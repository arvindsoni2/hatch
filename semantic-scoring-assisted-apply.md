# Hatch — Semantic Scoring Redesign + Assisted Apply

**Date:** 29 May 2026
**Repo:** https://github.com/arvindsoni2/hatch
**Decisions locked:** Local embeddings (sentence-transformers, offline/free) · Assisted apply (agent prepares, human submits)
**Standard:** TDD-first — write tests, watch them fail, implement, watch them pass.

---

## The problem in one sentence

A PMP-certified AI Project Manager with 20 years of delivery experience scored **0%** against an "IT Project Manager" role because (a) the scraper captured only the job title, and (b) keyword set-intersection can't see that "AI Project Manager / Technical Delivery Lead" means the same thing as "IT Project Manager."

## The fix in three layers

```
Layer 0  Fix scraper        → capture the real JD text (prerequisite)
Layer 1  Semantic recall     → embed full resume + full JD, cosine rank (free, local)
Layer 2  LLM judge           → holistic fit + rationale on the shortlist
```

What we already have to build on:
- `chromadb>=0.5.20` is already a dependency
- `story_matcher.py` already has a `_cosine()` implementation and a two-stage (tag → embedding) retrieval pattern we can mirror
- `resume.py` router and `cv_tailor.py` exist for the assisted-apply layer

---

## Part 1 — Scoring redesign

### Prompt 1: Fix the LinkedIn scraper to capture full JD (TDD)

```
The LinkedIn scraper captures only the job-card text (title + company), not 
the actual job description. This is why scoring sees an almost-empty JD.

WRITE TESTS FIRST — backend/tests/test_scrapers/test_linkedin.py:

1. test_parses_full_description_from_job_page:
   - Given a saved LinkedIn job-page HTML fixture (full posting), 
     verify the scraper extracts the full description text (> 500 chars),
     not just the title.

2. test_card_without_description_triggers_detail_fetch:
   - Given a search-results card with minimal text, verify the scraper 
     flags the job for a detail-page fetch rather than persisting a 
     title-only description.

3. test_description_min_length_guard:
   - A job whose extracted description is < 100 chars should be marked 
     needs_enrichment=True, not scored as-is.

THEN FIX backend/app/scrapers/linkedin.py:
   - Separate two phases: (1) discover job URLs from the search results, 
     (2) fetch each job's detail page and extract the full description 
     from the job-description container (LinkedIn uses 
     .show-more-less-html__markup or .description__text — handle both, 
     with a fallback to the largest text block).
   - Add a needs_enrichment flag to JobPostingCreate when the description 
     is too short, so the scorer can skip/defer rather than score garbage.
   - Respect rate limits and add a small delay between detail fetches.
   - Store description up to 5000 chars (not 1000) — scoring needs the 
     full text.

Apply the same detail-fetch pattern to other scrapers that capture 
truncated descriptions (check reed.py, indeed if present).

Run: cd backend && pytest tests/test_scrapers/test_linkedin.py -v
```

### Prompt 2: Add a master résumé store the scorer can use (TDD)

```
Scoring should match against the candidate's FULL resume text, not a lossy 
list of skill tags. Add a resume text store.

WRITE TESTS FIRST — backend/tests/test_services/test_resume_store.py:

1. test_save_and_load_resume_text:
   - Save parsed resume text, load it back, verify content round-trips.

2. test_resume_embedding_is_cached:
   - Embedding is computed once and cached; second load doesn't recompute.

3. test_resume_text_falls_back_to_profile_when_absent:
   - If no resume uploaded, build a resume-equivalent text block from 
     profile.yaml (summary + experience + skills + proof points + certs).

THEN IMPLEMENT backend/app/services/resume_store.py:
   - save_resume_text(text) — persists to data/master_resume.txt
   - get_resume_text() — returns uploaded resume text, or synthesises one 
     from profile.yaml if none exists (concatenate candidate.summary, 
     each proof_point.summary + context, skills, certifications, 
     target_roles, and the candidate.title)
   - get_resume_embedding() — returns a cached embedding of the resume 
     text (see Prompt 3 for the embedder)
   - The synthesised fallback is important: even without an uploaded CV, 
     the profile has enough signal (title "AI Project Manager", 20 years, 
     PMP, proof points) to match an IT PM role correctly.

The existing resume.py router already handles upload + parse — wire its 
parsed output into resume_store.save_resume_text().

Run: cd backend && pytest tests/test_services/test_resume_store.py -v
```

### Prompt 3: Local embedding service (TDD)

```
Add a local, offline embedding service using sentence-transformers. 
Zero API cost, runs on CPU, fits the free/private/offline-first story.

WRITE TESTS FIRST — backend/tests/test_tools/test_embedder.py:

1. test_embed_returns_fixed_dimension_vector:
   - embed("hello world") returns a list[float] of the model's dim 
     (384 for all-MiniLM-L6-v2).

2. test_cosine_identical_text_near_one:
   - cosine(embed("project manager"), embed("project manager")) > 0.99

3. test_cosine_related_roles_high:
   - cosine(embed("AI Project Manager and Technical Delivery Lead"), 
            embed("Information Technology Project Manager")) > 0.5
   - This is the CORE test — it proves semantic matching solves the 
     0% bug. Related roles with no shared keywords must score similar.

4. test_cosine_unrelated_low:
   - cosine(embed("project manager"), embed("pastry chef")) < 0.3

5. test_model_loads_once:
   - The SentenceTransformer model is loaded once and reused (singleton).

THEN IMPLEMENT backend/app/agents/tools/embedder.py:
   - Lazy-load sentence-transformers model "all-MiniLM-L6-v2" 
     (small, ~80MB, CPU-friendly, good quality)
   - embed(text: str) -> list[float]
   - embed_batch(texts: list[str]) -> list[list[float]]
   - cosine(a, b) -> float  (reuse the pattern from story_matcher.py)
   - Singleton model instance (load once, reuse)
   - Graceful fallback: if sentence-transformers isn't installed, log a 
     clear error telling the user to pip install it, and fall back to 
     the existing keyword scorer.

Add to backend/requirements.txt:
   sentence-transformers>=3.0,<4.0

Note: this pulls in torch (CPU). Document the ~200MB install in the README. 
For users who can't install it, the keyword scorer remains as fallback.

Run: cd backend && pytest tests/test_tools/test_embedder.py -v
```

### Prompt 4: Semantic scorer — embeddings for recall (TDD)

```
Replace keyword overlap with semantic similarity as the recall signal.

WRITE TESTS FIRST — backend/tests/test_tools/test_semantic_scorer.py:

1. test_it_pm_role_scores_high_for_pm_profile:
   - THE REGRESSION TEST for the 0% bug.
   - Profile: AI Project Manager / Technical Delivery Lead, 20 yrs, PMP
   - Job: "Information Technology Project Manager" with a realistic JD
   - Expect: semantic_score >= 0.55 (was 0.0 with keyword matching)

2. test_full_jd_required:
   - A job with needs_enrichment=True (empty JD) is NOT scored — 
     returned as deferred.

3. test_semantic_score_combines_with_dimensions:
   - The final score blends semantic similarity with the existing 
     location/rate/seniority signals (which keyword matching does fine).

THEN IMPLEMENT backend/app/agents/tools/semantic_scorer.py:
   - score_semantic(job, profile, resume_text) -> SemanticScoreResult
   - Compute cosine(resume_embedding, jd_embedding) as the core 
     "fit" signal (this replaces the broken skill keyword overlap)
   - KEEP the existing location_match and rate_match dimensions from 
     local_scorer.py — those keyword/rule checks work fine for location 
     and rate; only SKILL/EXPERIENCE matching needed semantics
   - Blend: overall = semantic_fit * (skill_weight + experience_weight) 
            + rate_match * rate_weight 
            + location_match * location_weight
   - Return matched/missing themes by comparing JD key phrases to resume 
     (for the rationale UI) — extract these via the LLM in Layer 2, or 
     a simple noun-phrase overlap for the local-only tier
   - If embedder unavailable, fall back to local_scorer.score_locally

Run: cd backend && pytest tests/test_tools/test_semantic_scorer.py -v
```

### Prompt 5: LLM-as-judge for the shortlist (TDD)

```
For top semantic-ranked jobs, use the LLM to judge holistic fit and 
produce a human-readable rationale — the trust layer.

WRITE TESTS FIRST — backend/tests/test_agents/test_scorer_agent.py 
(extend existing):

1. test_llm_judge_receives_full_resume_and_jd:
   - Verify the prompt includes the full resume text and full JD, 
     not just skill tags.

2. test_llm_judge_returns_rationale:
   - Mock LLM returns a fit score + reasoning; verify both persist.

3. test_hybrid_routes_top_semantic_to_llm:
   - 10 jobs ranked by semantic score; top N + borderline band go to 
     the LLM judge, clearly-low ones stay semantic-only.

THEN UPDATE backend/app/agents/scorer_agent.py:
   - New pipeline order:
     1. Skip jobs with needs_enrichment (no real JD)
     2. Semantic-score ALL jobs (Layer 1, free)
     3. Select top N% + borderline band (within ±0.15 of threshold) 
        for LLM judging
     4. LLM judge reads full resume + full JD, returns:
        { overall_score, fit_reasoning, strengths[], gaps[], 
          recommend: bool }
     5. Persist with the rationale
   - Rewrite _build_scoring_prompt to be a "judge like an experienced 
     recruiter" prompt:
     "Here is a candidate's full resume: {resume_text}
      Here is a job description: {jd_text}
      Assess fit holistically. A candidate whose title or experience 
      maps to the role counts as a strong match even if exact keywords 
      differ (e.g. 'AI Project Manager' fits 'IT Project Manager'). 
      Consider transferable experience, seniority, domain. 
      Return a 0-1 fit score, 2-3 specific strengths, any genuine gaps, 
      and whether to recommend."
   - This is what makes the IT PM role score ~0.85 with a clear reason.

Run: cd backend && pytest tests/test_agents/test_scorer_agent.py -v
```

### Prompt 6: Calibration regression suite (TDD)

```
Lock in correct behaviour with golden cases so scoring never regresses 
to the 0% failure again.

CREATE backend/tests/test_integration/test_scoring_calibration.py:

Use the embedder + semantic scorer (deterministic, no LLM needed):

1. test_pm_to_it_pm_is_strong:
   - The exact failure case. AI/Technical PM profile vs IT PM job.
   - Expect overall >= 0.60 (was 0.0).

2. test_exact_role_match_very_strong:
   - Delivery Lead profile vs "Senior Delivery Lead" job → >= 0.75

3. test_adjacent_role_moderate:
   - PM profile vs "Programme Manager" job → >= 0.55

4. test_wrong_field_low:
   - PM profile vs "Pastry Chef" job → <= 0.30

5. test_wrong_seniority_penalised:
   - 20-yr profile vs "Graduate Scheme" → <= 0.45

6. test_empty_jd_deferred_not_zero:
   - needs_enrichment job → deferred, never scored 0% and shown as 
     "no match"

These run in CI (CPU embeddings are fast for short texts). They are the 
guardrail that the redesign actually fixed the problem.

Run: cd backend && pytest tests/test_integration/test_scoring_calibration.py -v
```

### Prompt 7: Surface the rationale in the UI (TDD)

```
Show WHY a job matched — the trust layer the design calls "Why Hatch 
surfaced this."

WRITE TESTS FIRST for the component, then:

1. Update the job detail and approval pages to show:
   - Overall fit score (large)
   - "Why this is a fit" — the LLM rationale paragraph
   - "Your strengths for this role" — strengths[] as green tags
   - "Possible gaps" — gaps[] as neutral tags (honest, not alarming)
   - A method badge: "AI assessment" vs "Quick estimate"

2. Replace the current "Skills Gap Analysis: 0% — manager, information, 
   project, technology" block entirely. That keyword-diff UI is 
   misleading and must go. The new rationale is qualitative and accurate.

3. For the synthesised-profile case (no uploaded CV), add a gentle nudge: 
   "Upload your CV for more accurate matching."

Run: cd frontend && npm test
```

---

## Part 2 — Assisted apply

The principle: when you approve a job, the agent does everything up to the irreversible step. It tailors your CV, drafts the cover letter, pre-fills what it can, and opens the application in your browser. **You review and click submit.** No autonomous submission — ever.

### Prompt 8: Assisted-apply backend (TDD)

```
WRITE TESTS FIRST — backend/tests/test_services/test_assisted_apply.py:

1. test_approve_triggers_tailoring:
   - Approving a job creates a tailored CV + cover letter for that job.

2. test_application_package_assembled:
   - The assisted-apply package contains: tailored CV (docx), cover 
     letter, the job URL, and a pre-fill field map (name, email, phone, 
     etc. from profile).

3. test_no_autonomous_submission:
   - CRITICAL: verify there is NO code path that submits the application. 
     The package is prepared and surfaced; submission is manual. Assert 
     the service exposes no "submit" method and makes no POST to any 
     job-board endpoint.

THEN IMPLEMENT backend/app/services/assisted_apply.py:
   - prepare_application(job_id) -> ApplicationPackage:
     - Runs the tailor (CV + cover letter for this specific JD)
     - Assembles a pre-fill field map from profile (contact details, 
       work authorisation from locale legal_fields, etc.)
     - Returns paths to the generated docs + the original job URL + 
       the pre-fill map
   - NO browser automation, NO form submission, NO credentials. 
     This is deliberate — assisted, not auto.
   - Status flow: approved → preparing → ready_to_apply → 
     (user submits) → applied (user confirms)

Run: cd backend && pytest tests/test_services/test_assisted_apply.py -v
```

### Prompt 9: Assisted-apply UI (TDD)

```
WRITE TESTS FIRST for the component, then build the "ready to apply" 
experience.

On the approved jobs page, each approved job shows a "Prepare application" 
action. When prepared, show an "Application ready" card:

1. Tailored CV — preview + download button
2. Cover letter — preview + edit + download
3. Pre-fill summary — "We'll fill: name, email, phone, work auth"
4. Two buttons:
   - "Open application" (primary) — opens job.url in a new tab so the 
     user can paste/upload the prepared docs and submit themselves
   - "Mark as applied" — user confirms after they've submitted, moves 
     the card to the Applied column in the pipeline
5. A clear, reassuring line: "Hatch prepared everything. Review, then 
   submit on the company's site — you're always in control of the final 
   click."

Do NOT build any auto-submit button or browser-automation trigger.

The design reference (Hatch.html) approval flow: approving moves a job 
to Approved; from there "Prepare application" is the assisted step.

Run: cd frontend && npm test
```

---

## Execution order

| # | Prompt | Why this order |
|---|--------|---------------|
| 1 | Fix scraper | Prerequisite — no matching works without real JD text |
| 2 | Resume store | Scorer needs full resume text (or synthesised fallback) |
| 3 | Local embedder | Foundation for semantic matching |
| 4 | Semantic scorer | Replaces broken keyword overlap |
| 5 | LLM judge | Adds precision + rationale on the shortlist |
| 6 | Calibration suite | Locks in the fix — the 0% case must pass forever |
| 7 | Rationale UI | Makes scores transparent and trustworthy |
| 8 | Assisted-apply backend | Prepares the package, never submits |
| 9 | Assisted-apply UI | The review-then-submit experience |

Run 1-3 first and verify the embedder calibration test (`test_cosine_related_roles_high`) passes — that single test proves the semantic approach fixes your IT PM 0% problem. Then 4-6 wire it into the pipeline, and 7-9 complete the trust and apply layers.

---

## Why this rebuilds trust

The current system shows "0% — you match 0/13 skills, gaps: manager, information, project." That's not just wrong, it's *insultingly* wrong to a 20-year PMP-certified PM, and it teaches the user the system is broken. The new system will show "88% — strong fit. Your 20 years of IT project delivery and PMP certification directly match this IT Project Manager role; the JD emphasises infrastructure programmes, which aligns with your Northern Powergrid work." That's a score you can trust, with a reason you can verify — and it's the difference between a tool you abandon and one you rely on.
