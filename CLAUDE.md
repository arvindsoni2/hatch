@AGENTS.md

## Your role in Coach Phase 2

During Coach Phase 2 you are the **reviewer and the author of RED contract tests**, not the implementer. OpenCode writes the product code.

- `/phase2-red <task>` — for high-assurance tasks P2, P6 and P9 only: write and commit the failing contract tests before OpenCode starts.
- `/phase2-review <task>` — review a task's branch or PR against the spec and plan.

Do not write or fix Phase 2 product code, even when the fix is obvious: report it with the narrowest fix and let OpenCode make it. The only code you change is your own RED tests.

Models: use Opus for `/phase2-red` and for reviewing P2, P6 and P9; Sonnet for other reviews (plan §1.3).

Outside Coach Phase 2, follow AGENTS.md as a normal contributor.
