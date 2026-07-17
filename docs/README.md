# Hatch Documentation

Use this index to find the current product, operations, architecture, development, and historical documentation for Hatch.

## Start Here

- New user: [Installation](getting-started/INSTALLATION.md), [Windows install](getting-started/WINDOWS_INSTALL.md), [First run](getting-started/FIRST_RUN.md)
- Existing user: [User guide](user-guide/USER_GUIDE.md), [Troubleshooting](getting-started/TROUBLESHOOTING.md)
- Operator: [Operations guide](operations/OPERATIONS.md), [CLI reference](operations/CLI_REFERENCE.md), [Representative local-model selection](operations/REPRESENTATIVE_LOCAL_MODEL_BENCHMARK.md), [Backup and recovery](operations/BACKUP_AND_RECOVERY.md)
- Contributor: [Development setup](development/DEVELOPMENT_SETUP.md), [Repository structure](development/REPOSITORY_STRUCTURE.md), [Testing](development/TESTING.md)
- Maintainer: [Architecture overview](architecture/OVERVIEW.md), [Release checklist](operations/RELEASE_CHECKLIST.md), [Archive](archive/)

## Active Implementation Work

- [Prompt, skill, and local writing reliability specification v4](implementation-specs/active/Hatch_Prompt_Skill_Local_Writing_Reliability_Codex_Spec_v4.md)
- [Local writing model benchmark — 15 July 2026](benchmarks/LOCAL_WRITING_MODEL_BENCHMARK_2026-07-15.md)

## Documentation Map

- Getting started: install, first-run, Windows, troubleshooting
- User guide: Today, discovery, Pipeline, Applications, CV Studio, Interview Prep, Question Bank, Watched companies, Settings
- Architecture: runtime, components, workflows, AI, data, security, deployment
- Operations: CLI, capability profiles, local models, cloud providers, backup and recovery, release checklist
- Development: setup, repository structure, testing, route taxonomy
- Reference: configuration, lifecycle, glossary
- Implementation specifications: active, completed, superseded
- Archive: historical JobPilot material, design handoffs, non-current visual evidence

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
