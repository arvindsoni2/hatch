# Changelog

All notable changes to Hatch are documented here.

## [0.1.0] - 2026-07-11

### Added

- Guided Windows installer preflight and bootstrap validation for the public install path.
- Reproducible README screenshots using fictional demo data.
- Canonical public-release notes and release evidence checklist under `docs/`.

### Changed

- Reorganized release-facing documentation around the current installation, operations, and troubleshooting paths.
- Clarified route taxonomy, capability-profile guidance, and release governance contracts.
- Improved the Applications board and Pipeline workflow for review and preparation tasks.

### Fixed

- Kept review-queue interactions responsive during CV generation work.
- Corrected the Windows installer test contract so CI evaluates check-only behavior deterministically across hosts.

### Security

- Added documentation and validation guardrails for release links, install commands, privacy boundaries, and tracked-artifact review.

### Known limitations

- Hatch remains human-in-the-loop and does not auto-apply or message recruiters.
- Job-source reliability can vary because third-party boards change access patterns, rate limits, and markup.
- Local model quality and performance depend on the selected model and the host machine.
