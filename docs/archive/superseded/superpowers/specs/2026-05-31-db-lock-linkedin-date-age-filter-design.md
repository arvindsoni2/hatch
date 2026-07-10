---
title: Design: DB Lock Retry + LinkedIn Date Parsing + Approval Queue Age Filter
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

# Design: DB Lock Retry + LinkedIn Date Parsing + Approval Queue Age Filter

**Date:** 2026-05-31  
**Status:** Approved

## Background

Three bugs were root-caused via container inspection and code review:

1. **Q1 — Scrape button returns 500.** `BaseAgent.update_state()` calls `db.commit()` with no retry logic. When the scheduled ScoutAgent run holds the SQLite write lock, a concurrent manual trigger's `update_state("running")` throws `OperationalError: database is locked` → HTTP 500.

2. **Q2 — Container stale (deployment, not code).** `scheduler.py` on disk already delegates scraping to ScoutAgent. The running container was built before this change. Fix: full `--no-cache` container rebuild. No code change required.

3. **Q3 — Stale 2021 jobs in approval queue.** LinkedIn's `_parse_card` sets `posted_at = datetime.utcnow()` (scrape time), discarding the actual posting date embedded in the card HTML. Jobs from years ago score well on skills alone and surface in the approval queue.

---

## Fix 1 — DB Write-Lock Retry

### Scope
`backend/app/agents/base_agent.py` — `update_state()` method only.

### Design
Wrap the `await db.commit()` in a 3-attempt retry loop with linear backoff, identical to the pattern already used in `approve_application` (`routers/agents.py`):

```python
from sqlalchemy.exc import OperationalError
import asyncio

for attempt in range(3):
    try:
        await db.commit()
        break
    except OperationalError as exc:
        if "database is locked" in str(exc) and attempt < 2:
            await db.rollback()
            await asyncio.sleep(0.3 * (attempt + 1))
        else:
            raise
```

- **Retries:** 3 (attempts 0, 1, 2)
- **Backoff:** 300 ms, 600 ms
- **On final failure:** re-raise so callers see the real error
- **No signature changes**, no new methods, no callers affected

### Files changed
- `backend/app/agents/base_agent.py` — add `import asyncio`, `from sqlalchemy.exc import OperationalError`, replace bare `await db.commit()` with retry loop

---

## Fix 2 — LinkedIn Date Parsing

### Scope
`backend/app/scrapers/linkedin.py` — `LinkedInScraper` only.

### Design

Add a private helper `_parse_posted_at(card: Tag) -> tuple[datetime, bool]`:

1. **`<time>` element first** — find `card.find("time")` and read the `datetime` attribute (e.g. `"2025-03-12T00:00:00.000Z"`). Parse with `datetime.fromisoformat(attr.replace("Z", "+00:00")).replace(tzinfo=None)`.

2. **Relative text fallback** — search `card.get_text()` for the pattern:
   ```
   (\d+)\s+(day|week|month|year)s?\s+ago
   ```
   Map units: day→1, week→7, month→30, year→365. Return `datetime.utcnow() - timedelta(days=value * multiplier)`.

3. **Both fail** — return `(datetime.utcnow(), True)` where `True` signals date is unknown.

In `_parse_card`, replace:
```python
posted_at=datetime.utcnow(),
```
with:
```python
posted_at, date_unknown = self._parse_posted_at(card)
```
and update:
```python
needs_enrichment = needs_enrichment or date_unknown
```

### Files changed
- `backend/app/scrapers/linkedin.py` — new `_parse_posted_at` method, updated `_parse_card`

---

## Fix 3 — Approval Queue Age Filter

### Design

**Part A — Profile schema** (`backend/app/agents/tools/profile_loader.py`)

Add `max_job_age_days: int = 60` to the `Preferences` Pydantic model. The default of 60 means existing `profile.yaml` files need no changes.

**Part B — Approval queue query** (`backend/app/routers/agents.py`, `list_pending_approvals`)

At request time, load the profile and compute a cutoff datetime:
```python
try:
    max_age = load_profile().preferences.max_job_age_days
except Exception:
    max_age = 60
cutoff = datetime.utcnow() - timedelta(days=max_age)
```

Add a join to `JobPosting` and filter:
```python
.join(JobPosting, Application.job_id == JobPosting.id)
.where(JobPosting.posted_at >= cutoff)
```

Applications without a linked `JobPosting` are excluded by the inner join — correct behaviour since age cannot be determined.

**No frontend changes required** — the approval list re-fetches on mount; filtered jobs simply disappear.

### Files changed
- `backend/app/agents/tools/profile_loader.py` — add `max_job_age_days: int = 60` to `Preferences` model
- `backend/app/routers/agents.py` — updated `list_pending_approvals` query with join + cutoff filter

---

## Out of Scope

- Retry logic for `emit_event` / `EventBus.emit` — event-bus failures are non-fatal and retried on next supervisor poll
- Other scrapers' date parsing — only LinkedIn was confirmed to have this bug
- Container rebuild procedure — deployment concern, not a code change

## Testing

- **Fix 1:** Trigger scout manually while a background scout is running; verify no 500. Check that `update_state` errors are re-raised after 3 failures.
- **Fix 2:** Unit test `_parse_posted_at` with: `<time datetime="...">` card, "3 months ago" card, card with no date info.
- **Fix 3:** Seed a job with `posted_at = now - 90 days`; verify it does not appear in `GET /api/agents/approvals/pending`. Seed one with `posted_at = now - 30 days`; verify it does appear.
