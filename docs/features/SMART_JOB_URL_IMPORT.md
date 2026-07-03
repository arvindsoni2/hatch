# Smart Job URL Import

Open **Applications → Import from URL** to extract a public job page and review its fields before saving.

Hatch tries schema.org `JobPosting` data before conservative HTML extraction. Weak extraction returns an editable manual-review form. Optional Firecrawl fallback is disabled by default and receives no profile, CV, master CV, or proof-point data.

The importer normalizes tracking parameters and redirects, prevents duplicate jobs, limits response size and redirects, and rejects local, private, reserved, loopback, and link-local destinations. Save actions map to `saved`, `discovered`, or `discovered` followed by Tailor. Only a completed application pack enters `ready_to_apply`.
