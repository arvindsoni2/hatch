---
title: Smart Job URL Import
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

# Smart Job URL Import

Open **Applications → Import from URL** to extract a public job page and review its fields before saving.

Hatch tries schema.org `JobPosting` data before conservative HTML extraction. Weak extraction returns an editable manual-review form. Optional Firecrawl fallback is disabled by default and receives no profile, CV, master CV, or proof-point data.

The importer normalizes tracking parameters and redirects, prevents duplicate jobs, limits response size and redirects, and rejects local, private, reserved, loopback, and link-local destinations. Save actions map to `saved`, `discovered`, or `discovered` followed by Tailor. Only a completed application pack enters `ready_to_apply`.
