# Hatch — instructions for coding agents

Hatch is a self-hosted, human-in-the-loop job-search workspace. Backend: Python 3.12, FastAPI, async SQLAlchemy 2, Alembic, SQLite (WAL), shared runtime in `backend/app/runtime/`. Frontend: Next.js 15, React 18, TypeScript, Tailwind 3, components in `frontend/src/components/ui/`. Local models run in llama.cpp (`llm-primary` :8080, `llm-triage` :8081). Hatch never takes an external action (applying, messaging) without the user.

## Current work

The owner names the governing spec for each piece of work. Active specs live in `docs/implementation-specs/active/`; a spec may also be kept outside Git while it describes unfixed weaknesses, in which case the owner gives its path. A spec's own rules override this file where they differ.

Roles: **OpenCode implements**, one task per PR. **Claude Code reviews** every PR and writes the failing (RED) tests first where a spec marks a task high-assurance. The owner merges.

Completed work and the Coach Phase 2 instructions are archived in `docs/archive/agent-instructions/`.

## Task loop (implementer)

1. Start from current `main` (`git fetch` then branch from `origin/main`); record the base SHA. Use the branch name the spec gives. If a branch already holds a RED commit, check it out instead.
2. Read the task section and every section it names. If a listed file or interface does not exist or differs from the spec, stop and report; do not redesign.
3. Write the named tests (or use the RED tests already committed). Run them and record the failure.
4. Implement the minimum to pass. Keep to the files the task lists. No unrelated refactors, no new dependencies unless the task names them.
5. Run the focused tests and the listed regressions, `ruff check` on changed backend files, `npm run type-check` when the frontend changed, `python scripts/check_docs.py` when docs changed, and `git diff --check`.
6. Fill the evidence report the spec names. Report only commands you actually ran, with their real output.
7. Commit exact paths with the spec's commit message. Ask the owner before pushing. Then say "Ready for review" with the branch name and stop. Do not start the next task.

## Hard rules

- Never edit the governing spec, `AGENTS.md`, `CLAUDE.md`, `opencode.json`, anything in `.claude/` or `docs/archive/`, or a RED test file listed by the spec. If one of these is wrong, stop and report.
- For high-assurance tasks, implement the assumed interfaces in the RED report exactly as listed.
- Never read or paste the contents of `data/`, `.env*`, `${HATCH_HOME}`, real CVs, transcripts or recordings into a prompt, test or fixture. All fixtures are synthetic.
- Never weaken, skip or delete an existing test to make a change pass. Never mock the unit under test.
- Never merge, force-push, rebase, amend, reset, delete a branch, turn a feature flag on, or promote a model in `model_tiers.json` without the owner. Bring a branch up to date with `git merge main`.
- Never send requests to the live containers on ports 3000, 8000, 8080, 8081 or 8090; use test ports.
- Interview round times are UTC in storage and the API; show them in the display timezone.
- Model output is a proposal. Every feature must still render useful deterministic content with AI mode set to None.
- No raw candidate text in runtime records, events, traces, logs or metric labels. No database write transaction may span a model call.
- UI: use the existing components and design tokens. Both themes, 390 px width and keyboard must work.
- Do not switch models silently. If you change model, write the switch and its reason in the evidence report.

## Stop and hand to the reviewer when

- two repair cycles on the same failing test have not fixed it (switch to the `argon` agent once, then stop);
- a RED test written by Claude Code looks wrong;
- the task would need a file outside its list, a schema change the spec does not describe, or a new dependency;
- you are about to touch privacy, deletion or ownership code in a way the task does not describe.

## Verification commands

Repository root: `python scripts/check_readme_contract.py`, `python scripts/check_docs.py`, `git diff --check`

Backend (`cd backend`): `ruff check app/ tests/`, `python -m pytest -q --no-cov <paths>`, `python -m pytest -q --no-cov tests/runtime`, `alembic heads`

Frontend (`cd frontend`): `npx vitest run <paths>`, `npm run type-check`, `npm run build`, `npx playwright test <spec>`
