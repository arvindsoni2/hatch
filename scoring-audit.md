# Hatch — Scoring & Matching Audit + Trust-Building Plan

**Date:** 28 May 2026
**Repo:** https://github.com/arvindsoni2/hatch
**Focus:** Is the job scoring/matching correct, sufficient, and trustworthy?

---

## Executive summary

I audited the full scoring pipeline: `local_scorer.py` (keyword scoring), `scorer_agent.py` (LLM + hybrid orchestration), the supervisor's shortlisting threshold, and how scores surface in the UI. 

**The architecture is sound** — four weighted dimensions, two-tier LLM, hybrid local+LLM, configurable weights. But there are **specific correctness bugs and trust gaps** that explain why you're unsure if it's working. The biggest issue: **the local scorer (which scores 80% of jobs in hybrid/free-tier mode) has weak heuristics that produce misleading scores, and the UI doesn't show users WHY a job scored the way it did.**

Trust comes from transparency. Right now the system shows a number ("78% match") but hides the reasoning. Users can't tell if 78% means "great fit, minor gaps" or "the keyword matcher got lucky."

---

## Part 1 — Correctness issues in the scoring logic

### Issue 1.1: Rate matching is fundamentally broken (HIGH)

`local_scorer.py` `_rate_match()` extracts ANY 3-6 digit number from the JD and guesses if it's a salary:

```python
numbers = re.findall(r"\b(\d{3,6})\b", jd_lower)
for num_str in numbers:
    num = int(num_str)
    if comp.rate_type == "daily":
        if 200 <= num <= 2000:  # assumes any number 200-2000 is a daily rate
```

**Problems:**
- "We have 500 employees" → 500 matches as a daily rate
- "Founded in 1998" → not caught (good) but "team of 1200" → 1200 caught as daily rate
- A JD mentioning "£75,000 salary" with `rate_type=daily` won't match because 75000 > 2000, so it falls through to 0.5
- Job postings often state ranges like "£550-£650" — the regex captures both as separate numbers, scores on the first match
- No currency awareness — a job in India quoting "2500000" (₹25 LPA) scored against a UK profile gets nonsense

**Impact:** Rate is weighted at typically 20% of the overall score. A broken rate dimension corrupts 1 in 5 points of every score.

### Issue 1.2: Experience matching uses crude keyword presence (MEDIUM)

`_experience_match()` checks if the JD contains words like "senior" or "junior":

```python
if jd_has_junior and years > 5:
    return 0.2  # overqualified
if jd_has_senior and years >= 7:
    return 0.9
```

**Problems:**
- A JD that says "you'll mentor junior engineers" contains "junior" → a senior candidate gets flagged as overqualified (0.2) for a senior role
- No actual years-of-experience extraction from the JD ("5+ years required" is ignored)
- "manager" is in the senior list, so "we work with your manager" triggers a senior match
- Title matching splits on spaces and matches words > 3 chars, so "Lead" in "Team Lead" matches "Lead Generation Specialist"

### Issue 1.3: Skill matching has no semantic understanding (MEDIUM)

`_skill_match()` does exact word-boundary matching:

```python
if _keyword_present(jd_lower, skill):
    matched.append(skill)
```

**Problems:**
- "React" matches but "ReactJS" or "React.js" does not
- "Agile delivery" as a profile skill won't match a JD that says "agile environment" and "delivery management" separately
- "stakeholder management" won't match "managing stakeholders"
- No synonym handling: "k8s" ≠ "Kubernetes", "ML" ≠ "machine learning"
- The local scorer (used for 80% of jobs in hybrid mode) misses most real matches, deflating skill scores

### Issue 1.4: The hybrid top-20% cutoff can hide good jobs (MEDIUM)

In `_run_hybrid()`, only the top 20% of locally-scored jobs get LLM refinement:

```python
llm_count = max(1, round(len(local_results) * top_pct))  # top 20%
```

Because the local scorer is weak (Issues 1.1-1.3), a genuinely great job can score low locally (e.g. because its skills are phrased differently) and never reach the LLM. It gets persisted with the inaccurate local score and may fall below the shortlist threshold — **so the user never sees it.**

This is likely a major reason "no jobs match" — good jobs are being locally mis-scored and filtered out before the LLM ever sees them.

### Issue 1.5: Batch size of 5 with rate limiting starves the pipeline (MEDIUM)

`_BATCH_SIZE = 5` means each scorer run processes only 5 jobs. If Scout discovers 50 jobs, it takes 10 supervisor ticks to score them all. Combined with free-tier rate limits, scoring can lag far behind discovery, leaving most jobs unscored (status stuck at `pending`).

---

## Part 2 — Trust gaps (why you can't tell if it's working)

### Gap 2.1: The 4-dimension breakdown is computed but never shown

The scorer produces `skill_match`, `experience_match`, `rate_match`, `location_match` and stores them in the `job_scores` table. But the UI only shows the single `overall_score` ("78% match"). 

**Users can't see:** "This scored 78% because skills matched 95% but rate only matched 40% (the rate wasn't stated in the JD)." Without the breakdown, the number is opaque and untrustworthy.

The design file (`pages/jobs.jsx`) has an "AI rationale" card ("Why Hatch surfaced this") and a "Skills matched vs required" section — but the implementation's `MatchScoreBadge.tsx` only shows a tooltip with generic reasons, not the dimension breakdown.

### Gap 2.2: No distinction between local and LLM scores in the UI

A job scored by the weak local keyword matcher and a job scored by the LLM both show as "78% match" with no indicator of confidence. Users should know: "This score is a quick estimate" vs "This score is a detailed AI assessment."

### Gap 2.3: No scoring transparency / audit trail

There's no way for a user to ask "why did this score 78%?" and get a real answer. The `reasoning` field exists for LLM scores but says "local-keyword" for 80% of jobs. The decision trail we specified in earlier phases isn't surfacing the scoring logic.

### Gap 2.4: Threshold is invisible and unexplained

The shortlist threshold (default 0.75) silently determines what the user sees. If it's set too high, the queue is empty and the user thinks the system is broken. If too low, they're flooded. There's no feedback like "12 jobs scored 60-75% — lower your threshold to see them" or "your threshold is 75%, average score this week was 62%."

---

## Part 3 — What "sufficient criteria" should look like

The current 4 dimensions (skill, experience, rate, location) are a reasonable start but incomplete. Strong job-matching systems also consider:

| Dimension | Why it matters | Currently? |
|-----------|---------------|-----------|
| Skill match | Core fit | ✓ (weak local impl) |
| Experience/seniority | Right level | ✓ (crude) |
| Compensation | Worth applying | ✓ (broken local impl) |
| Location/remote | Can you take it | ✓ (decent) |
| **Domain/industry** | Sector fit | ✗ (in prompt, not scored) |
| **Company stage/size** | Startup vs enterprise preference | ✗ |
| **Recency** | Fresh postings convert better | ✗ |
| **Title alignment** | Exact role vs adjacent | Partial |
| **Growth signal** | Career progression | ✗ |

---

## Part 4 — Claude Code Instructions

### Prompt 1: Fix the local scorer correctness (TDD)

```
The local keyword scorer has correctness bugs that corrupt scores for 
~80% of jobs in hybrid/free-tier mode. Fix each, test-first.

WRITE TESTS FIRST in backend/tests/test_tools/test_local_scorer.py:

1. test_rate_match_ignores_non_salary_numbers:
   - JD "team of 500 engineers, founded 1998" with daily rate target
   - Should NOT match 500 or 1998 as a rate → return neutral (rate not stated)

2. test_rate_match_handles_salary_with_rate_type_mismatch:
   - JD "£75,000 per annum" with profile rate_type=annual
   - Should correctly parse and match

3. test_rate_match_parses_ranges:
   - JD "£550 - £650 per day" → should match against daily range

4. test_experience_match_ignores_mentor_junior:
   - JD "Senior role — you'll mentor junior engineers", candidate 10 yrs
   - Should score HIGH (senior match), not 0.2 (overqualified)

5. test_skill_match_handles_variants:
   - profile skill "React", JD says "ReactJS" → should match
   - profile skill "Kubernetes", JD says "k8s" → should match (synonym)

THEN FIX local_scorer.py:

a. _rate_match: Only extract numbers near currency symbols or rate 
   keywords ("salary", "per annum", "per day", "/day", "£", "$", "k", "LPA").
   Use a context window: look for digits within 20 chars of a currency 
   indicator. Parse ranges (X - Y). Handle "75k" → 75000. Respect the 
   profile's currency and rate_type. If no salary-context number found, 
   return 0.6 (neutral, not penalising).

b. _experience_match: 
   - Extract explicit requirements: "5+ years", "minimum 7 years" via regex
   - Only count seniority keywords in the JOB TITLE, not the full description 
     (avoids "mentor junior" false positives)
   - Compare extracted required years against candidate years

c. _skill_match: Add a normalisation + synonym layer:
   - Normalise: strip ".js", "JS", spaces, hyphens before matching 
     ("React.js" → "react", "k8s" → "kubernetes")
   - Maintain a small synonym map (k8s↔kubernetes, ml↔machine learning, 
     js↔javascript, etc.)
   - Match multi-word skills as a phrase OR all words present within 
     a window (so "agile delivery" matches "agile ... delivery")

Run: cd backend && pytest tests/test_tools/test_local_scorer.py -v
All new tests must pass.
```

### Prompt 2: Fix the hybrid cutoff to not hide good jobs (TDD)

```
The hybrid mode only sends the top 20% of locally-scored jobs to the LLM. 
Because the local scorer is imperfect, good jobs can be mis-scored low 
and never reach the LLM, then fall below the shortlist threshold and 
never reach the user.

WRITE TEST FIRST in backend/tests/test_agents/test_scorer_agent.py:

test_hybrid_sends_borderline_jobs_to_llm:
   - 10 jobs, local scores ranging 0.4 to 0.9
   - Jobs scoring near the threshold (0.65-0.85 if threshold is 0.75) 
     should ALL get LLM refinement, not just top 20%
   - Clearly-low jobs (< 0.5) can stay local

THEN FIX scorer_agent.py _run_hybrid:
   - Instead of "top 20% by local score", use a smarter selection:
     a. Always LLM-score jobs whose local score is within ±0.15 of the 
        shortlist threshold (the borderline cases where accuracy matters most)
     b. Always LLM-score the top N by local score
     c. Skip LLM only for jobs scoring clearly below (threshold - 0.15)
   - This ensures borderline jobs get the accurate LLM assessment 
     rather than being filtered out by a weak local score.
   - Make the band width configurable: profile.scoring.hybrid_llm_band (default 0.15)

Run: cd backend && pytest tests/test_agents/test_scorer_agent.py -v
```

### Prompt 3: Surface the score breakdown in the UI (TDD)

```
The 4-dimension breakdown is computed and stored but never shown. Users 
see "78% match" with no explanation. Build the transparency UI.

WRITE TESTS FIRST in frontend/src/__tests__/components/ScoreBreakdown.test.tsx:
   - renders all 4 dimension bars with labels and percentages
   - shows the scoring method badge (local vs AI)
   - shows reasoning text when present
   - highlights the weakest dimension

THEN CREATE frontend/src/components/ScoreBreakdown.tsx:
   - Four horizontal bars: Skill match, Experience, Compensation, Location
   - Each bar: label + percentage + coloured fill (green/amber/red by value)
   - Below: overall score (large) with the weighted calculation shown
   - A method badge: "AI assessment" (accent) or "Quick estimate" (muted) 
     based on scoring_method
   - The reasoning text from the score
   - If local-only: a note "Quick keyword estimate — approve to get full AI review"

THEN INTEGRATE into:
   - approvals/[id]/page.tsx — show full ScoreBreakdown in the detail panel
   - The approval inbox detail (from the design's "Why Hatch surfaced this")
   - jobs/[id]/page.tsx — show in the job detail

Use the existing job_scores data (skill_match, experience_match, 
rate_match, location_match, reasoning) from the API. If the API doesn't 
return these per-job, add them to the job detail endpoint.

Run: cd frontend && npm test
```

### Prompt 4: Add "Why Hatch surfaced this" rationale (TDD)

```
The design has an AI rationale card explaining why each job was surfaced. 
The implementation shows only generic tooltip reasons. Build the real thing.

WRITE TEST FIRST:
   - ScoreRationale renders the reasoning, matched skills, and missed skills
   - shows matched skills as green tags, missing as plain tags

THEN:
1. Ensure the scorer's keyword_matches and keyword_misses are persisted 
   to the job_scores table (add columns if missing) and returned by the API.

2. Create frontend/src/components/ScoreRationale.tsx matching the design's 
   ai-rationale card:
   - Sparkle icon + "Why Hatch surfaced this" heading
   - The reasoning paragraph
   - "Skills you have" — green check tags from keyword_matches
   - "Skills they want that you're missing" — plain tags from keyword_misses
   - If missing skills exist: "Consider adding these to your profile if 
     you have them" with a link to settings

3. Show this card in the approval detail and job detail pages.

Run: cd frontend && npm test
```

### Prompt 5: Threshold feedback and score distribution (TDD)

```
The shortlist threshold silently controls what users see. Add feedback 
so an empty queue is explained, not mysterious.

WRITE TESTS FIRST for the backend endpoint and frontend component.

1. Backend: add GET /api/v2/scoring/insights returning:
   {
     "threshold": 0.75,
     "scored_last_7d": 142,
     "above_threshold": 8,
     "in_band_60_75": 23,    // jobs just below threshold
     "avg_score": 0.62,
     "distribution": [{"bucket": "0-10", "count": 2}, ...],
     "recommendation": "Your threshold is 75% but the average score is 62%. 
                        Lowering to 65% would surface 23 more roles."
   }

2. Frontend: on the approval queue, when the queue is near-empty, show 
   a banner: "Only 8 jobs above your 75% threshold this week. 23 more 
   scored 60-75%. [Lower threshold] [See why]"

3. On the analytics page, add a score distribution histogram with the 
   threshold line (this was specced before — verify it's wired to real data).

This turns "no jobs match" from a dead end into an actionable insight.

Run: make test
```

### Prompt 6: Add domain/recency scoring dimensions (TDD)

```
The scoring criteria are incomplete. Add domain match and recency as 
scoring signals (the prompt mentions domains but doesn't score them).

WRITE TESTS FIRST for both new dimensions in test_local_scorer.py.

1. Add _domain_match to local_scorer.py:
   - Check if the job's company/description mentions any of 
     profile.domains.preferred
   - Penalise if it matches profile.domains.excluded
   - Return a 0-1 score

2. Add recency as a soft modifier (not a full dimension):
   - Jobs posted in last 48h get a small boost (fresh postings convert better)
   - Jobs older than 30 days get a small penalty

3. Make the weights configurable. Update profile.yaml schema:
   scoring.weights now includes optional domain_match (default 0.0 so 
   existing profiles are unaffected unless they opt in).

4. Update both local_scorer and the LLM scoring prompt to include domain.

Keep backwards compatibility — if domain_match weight is 0, behaviour 
is unchanged.

Run: make test
```

### Prompt 7: Scoring confidence and calibration test (TDD)

```
Add a calibration test that validates the scorer produces sensible 
scores on known cases — this is the regression guard for trust.

CREATE backend/tests/test_integration/test_scoring_calibration.py:

Build a set of golden test cases — job + profile pairs with expected 
score ranges:

1. test_perfect_match_scores_high:
   - Profile: Delivery Lead, 20yrs, London hybrid, £600/day, skills 
     [agile, stakeholder mgmt, delivery]
   - Job: "Senior Delivery Lead, London hybrid, £550-650/day, agile 
     delivery, stakeholder management"
   - Expect: overall_score >= 0.80

2. test_wrong_seniority_scores_low:
   - Same profile
   - Job: "Junior Project Coordinator, graduate scheme"
   - Expect: overall_score <= 0.40

3. test_wrong_location_lowers_score:
   - Profile wants London onsite only
   - Job in "San Francisco, onsite only"
   - Expect: location_match <= 0.40

4. test_missing_skills_lowers_skill_match:
   - Profile skills [python, fastapi]
   - Job requires [java, spring, kotlin]
   - Expect: skill_match <= 0.30

5. test_rate_below_minimum_lowers_rate_match:
   - Profile min £550/day
   - Job offers £300/day
   - Expect: rate_match <= 0.40

These run against the LOCAL scorer (deterministic, no LLM needed) so 
they're fast and CI-safe. They guard against scoring regressions.

Run: cd backend && pytest tests/test_integration/test_scoring_calibration.py -v
```

---

## Part 5 — Recommended priority order

| Priority | Prompt | Why |
|----------|--------|-----|
| 1 | Prompt 1 (fix local scorer) | Corrects the root cause of mis-scoring |
| 2 | Prompt 7 (calibration tests) | Locks in correct behaviour, prevents regression |
| 3 | Prompt 2 (hybrid cutoff) | Stops good jobs being hidden |
| 4 | Prompt 3 (score breakdown UI) | Makes scores transparent → builds trust |
| 5 | Prompt 5 (threshold feedback) | Explains empty queues |
| 6 | Prompt 4 (rationale card) | Completes the "why" story |
| 7 | Prompt 6 (domain/recency) | Improves criteria completeness |

Run Prompts 1, 7, and 2 first — they fix the correctness problems that are most likely causing "no jobs match." Then 3, 5, 4 build the transparency that creates trust. Prompt 6 is an enhancement once the foundation is solid.
