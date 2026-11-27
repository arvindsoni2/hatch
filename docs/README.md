# Hatch Documentation

Use this index to find the current product, operations, architecture, development, and historical documentation for Hatch.

## Start Here

- New user: [Installation](getting-started/INSTALLATION.md), [Windows install](getting-started/WINDOWS_INSTALL.md), [First run](getting-started/FIRST_RUN.md)
- Existing user: [User guide](user-guide/USER_GUIDE.md), [Troubleshooting](getting-started/TROUBLESHOOTING.md)
- Operator: [Operations guide](operations/OPERATIONS.md), [Local AI observability](operations/OBSERVABILITY.md), [CLI reference](operations/CLI_REFERENCE.md), [Representative local-model selection](operations/REPRESENTATIVE_LOCAL_MODEL_BENCHMARK.md), [Backup and recovery](operations/BACKUP_AND_RECOVERY.md)
- Contributor: [Development setup](development/DEVELOPMENT_SETUP.md), [Repository structure](development/REPOSITORY_STRUCTURE.md), [Testing](development/TESTING.md)
- Maintainer: [Architecture overview](architecture/OVERVIEW.md), [AI architecture](architecture/AI_ARCHITECTURE.md), [Decision layer](architecture/DECISION_LAYER.md), [Release checklist](operations/RELEASE_CHECKLIST.md), [Security surface](architecture/SECURITY_SURFACE.md), [Archive](archive/)

## Current Implementation Work

- Decision layer: approved target design, not yet implemented. See [Decision layer](architecture/DECISION_LAYER.md).
- Task evidence for current work lives in [implementation-reports](implementation-reports/).
- Coach model benchmark tool: [how to run it](benchmarks/COACH_MODEL_BENCHMARK.md).

## Completed Specifications

Kept for design history in [implementation-specs/completed](implementation-specs/completed/):

- [Coach Phase 2 — Interview Readiness Loop](implementation-specs/completed/2026-10-22-coach-phase2-readiness-loop.md) (P0–P9 merged; features opt-in, off by default). Also: [screen designs](visual-evidence/coach-phase2-design/README.md), [diagrams](architecture/coach-phase2-readiness-loop.html), [task evidence](implementation-reports/coach-phase2/) and the archived [implementation plan](archive/implementation-notes/2026-10-22-coach-phase2-readiness-loop-plan.md)
- [Conversational AI Interview Coach Phase 1 v6](implementation-specs/completed/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md) (acceptance closed October 2026)
- [Architecture Foundation v2](implementation-specs/completed/Hatch_Architecture_Foundation_Implementation_Spec_v2.md) (runtime slices R0–R6 delivered; R7–R9 paused, see the [implementation plan](implementation-notes/Hatch_Architecture_Foundation_Implementation_Plan_v2.md))
- [Coach model quality, benchmark and observability v5](implementation-specs/completed/Hatch_Coach_Model_Quality_Benchmark_Observability_Codex_Spec_v5.md)
- [Prompt, skill and local writing reliability v4](implementation-specs/completed/Hatch_Prompt_Skill_Local_Writing_Reliability_Codex_Spec_v4.md)
- [Easy install, hardware and model selection v8](implementation-specs/completed/Hatch_Easy_Install_Hardware_Model_Selection_Spec_v8.md)
- [Backend container optimisation](implementation-specs/completed/Hatch_Backend_Container_Optimisation_Spec.md)
- [UX gap review](implementation-specs/completed/hatch_ux_gap_review_codex_spec.md)

Specs moved here from `active/` unchanged, so the "canonical path" line inside some of them still names the old location. Earlier draft versions of these specs were removed; they remain in Git history.

## Documentation Map

- Getting started: install, first-run, Windows, troubleshooting
- User guide: Today, discovery, Pipeline, Applications, CV Studio, Interview Prep, Interview Coach, Question Bank, Watched companies, Settings
- Architecture: runtime, components, workflows, AI, data, security, deployment
- Operations: CLI, capability profiles, local models, cloud providers, backup and recovery, release checklist
- Development: setup, repository structure, testing, route taxonomy
- Reference: configuration, lifecycle, glossary
- Implementation specifications: active, completed
- Implementation reports: task evidence for current work
- Archive: historical JobPilot material, design handoffs, superseded plans and specs, past implementation notes and reports, past benchmarks, non-current visual evidence

## Document Status

- Current: verified against `main`
- Planned: intended but not yet implemented
- Active specification: mixed or unfinished implementation work
- Implemented specification: verified complete and retained for design history
- Superseded: replaced by a newer source
- Historical: retained for context and not current product guidance

## Source Of Truth

When documentation disagrees with implementation, use the current code on `main`, active Docker Compose files, installer and CLI scripts, and current tests before older specs or historical documents.

## Report Drift

Report documentation drift through the repository issue tracker or in a pull request against the affected file. If a technical statement cannot be confirmed from the repo, label it as planned, experimental, inferred, or not yet verified.
