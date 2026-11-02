---
description: Write and commit the RED contract tests for a high-assurance Coach Phase 2 task (P2, P6, P9)
argument-hint: <task id, e.g. P2>
---

Write the failing contract tests for Coach Phase 2 task **$ARGUMENTS** before OpenCode implements it.

1. Check the task is P2, P6 or P9. If not, stop: OpenCode writes its own tests for other tasks.
2. `git switch main && git pull --ff-only`, then create the branch `coach-p2/<task id lower case>-<short name>` (or check it out if it exists and has no implementation commits yet). Record `git rev-parse HEAD`.
3. Read, in this order: the task's section in `docs/implementation-notes/2026-10-22-coach-phase2-readiness-loop-plan.md` (its Files, Named tests and "Read first" list); every spec section it names in `docs/implementation-specs/active/2026-10-22-coach-phase2-readiness-loop.md`; the existing code and tests the task touches. Note where the plan's file paths or interfaces do not match the code.
4. Write only the named tests the plan marks for Claude Code, in the test files the plan lists. Test through the interfaces fixed in spec §10.1 and names that already exist in the codebase, not a parallel implementation of the policy. If a test needs anything else (a helper, a fixture factory, a DTO field, a route parameter), keep it minimal and list it in step 7 under **Assumed interfaces**. For integration tests, assert durable rows and real dispatch counts after reloading the database, not in-memory flags. Use synthetic data only; never read `data/`.
5. Run them. Each must fail because the behaviour is missing (missing module, route, table or assertion), not because of a syntax or fixture error. Fix your tests until that is true.
6. Commit only the test files: `test(coach): RED contract for $ARGUMENTS`.
7. Write `docs/implementation-reports/coach-phase2/<task id>-red.md` with: the RED commit SHA, the test file paths OpenCode must not edit, each test name with the failure you observed, any plan/code mismatch from step 3, and an **Assumed interfaces** section (each signature or field the tests rely on beyond spec §10.1, with the file it belongs in). Commit it in a second commit.
8. Ask before pushing. Then tell the owner the branch is ready for OpenCode once they approve the Assumed interfaces list (it becomes binding for the implementation), and list any mismatch that needs an owner decision first.

Do not write implementation code.
