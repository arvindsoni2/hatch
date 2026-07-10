---
title: CV Quality Gate
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

# CV Quality Gate

The CV Quality Gate checks evidence before generation and parses the generated DOCX after generation.

It reports ATS readability, required sections, keyword coverage, and material claims that cannot be traced to profile or master CV evidence. Coverage below 30%, unreadable output, missing experience, or multiple missing core sections require acknowledgement in first-party download controls. Direct backend file URLs remain available because Hatch is a local, self-hosted tool.

Regenerated document versions receive a separate quality result and acknowledgement.
