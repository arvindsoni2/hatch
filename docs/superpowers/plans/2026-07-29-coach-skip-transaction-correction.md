# Conversational Skip Transaction Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make normal typed `skip_question` execution resolve V6 transient state within its command transaction and return stable `asking` or `reporting`.

**Architecture:** Keep the existing command transaction, receipt, state-version, event, and reconciliation architecture. Move next-question presentation and terminal report transition into `_skip_question`; retain reconciliation only for directly seeded interrupted `advancing` aggregates.

**Tech Stack:** Python 3, FastAPI service layer, SQLAlchemy async ORM, pytest, SQLite test databases.

## Global Constraints

- V6 section 8.7: `asking_follow_up` and `advancing` must be entered and resolved in one backend transaction during normal command execution; normal API responses must not leave either state pending.
- The V6 authority SHA-256 remains `626381be8963340972711bdfa5e47df0c82d521bb4e22ad75f3f873022c19ae8`.
- `HATCH_COACH_CONVERSATIONAL_ENABLED` remains `False` by default.
- A successful skip increments `InterviewSession.state_version` exactly once and `activity_version` exactly once.
- Command receipt replay returns the original stable result and causes no additional question presentation, report job, state increment, or event.
- Reconciliation retains support for directly seeded interrupted `advancing` state.
- No report generation, media, transcription, evaluation, frontend, migration, legacy skip, database-bootstrap, or Phase 2 changes.

---

### Task 1: Resolve typed skip within the command transaction

**Files:**
- Modify: `backend/app/services/coach_conversation_commands.py:898-965`
- Modify: `backend/tests/test_services/test_coach_conversation_commands.py:1322-1356`
- Modify: `backend/tests/test_services/test_coach_conversation_commands.py:1981-2055`
- Test: `backend/tests/test_services/test_coach_reconciliation.py`

**Interfaces:**
- Consumes: `ConversationCommandService.execute`, `_change_session_state`, `ConversationalSessionRepository.append_session_events`, and `AsyncJobService.create`.
- Produces: unchanged public command API; `skip_question` returns `ConversationCommandResult.state == "asking"` when another question exists and `state == "reporting"` for the terminal question.

- [ ] **Step 1: Write failing stable-state tests**

  Replace normal-command expectations for `advancing` with independent, observable assertions:

  ```python
  assert result.state == "asking"
  assert result.active_question_id == questions[1].id
  assert (questions[1].question_state, questions[1].asked_sequence) == ("asked", 2)
  assert result.state_version == 4
  ```

  For the terminal path assert:

  ```python
  assert (result.state, result.state_version) == ("reporting", 5)
  assert persisted_session.active_question_id is None
  assert persisted_session.report_state == "building"
  assert report_job_count == 1
  ```

  Replay the same command and assert equality with the first result, one receipt,
  one report job, and no state-version or event-count increase.

- [ ] **Step 2: Run the new tests and verify RED**

  Run:

  ```bash
  pytest -q \
    backend/tests/test_services/test_coach_conversation_commands.py::test_skip_resolves_to_next_question_within_command_transaction \
    backend/tests/test_services/test_coach_conversation_commands.py::test_terminal_skip_resolves_to_reporting_within_command_transaction
  ```

  Expected: both fail because the current implementation returns `advancing` and
  requires a separate reconciliation call.

- [ ] **Step 3: Implement the minimal transactional correction**

  For a non-terminal skip, conditionally change the next pending question to
  `asked` with the next literal sequence, update the session directly to
  `asking`, and persist `question_skipped`, `question_advanced`, and
  `question_presented` events under the command's one resulting state version.

  For a terminal skip, create the existing initial report job and ownership
  snapshot, update the session directly to `reporting`, clear active question,
  root, and recording identifiers, and persist `question_skipped` and
  `report_claimed` events. Use candidate/system actor types consistently with
  normal command execution; do not label normal work as reconciler work.

  Every conditional question or session write must raise the canonical invalid
  state error if its fence loses, allowing the surrounding command transaction
  to roll back all partial writes.

- [ ] **Step 4: Verify GREEN and recovery separation**

  Run the two named tests from Step 2, then:

  ```bash
  pytest -q \
    backend/tests/test_services/test_coach_conversation_commands.py \
    backend/tests/test_services/test_coach_reconciliation.py
  ```

  Confirm normal command tests no longer call reconciliation, while directly
  seeded interrupted-state reconciliation tests remain green.

- [ ] **Step 5: Run scoped quality gates**

  ```bash
  ruff check backend/app/services/coach_conversation_commands.py \
    backend/tests/test_services/test_coach_conversation_commands.py \
    backend/tests/test_services/test_coach_reconciliation.py
  ruff format --check backend/app/services/coach_conversation_commands.py \
    backend/tests/test_services/test_coach_conversation_commands.py \
    backend/tests/test_services/test_coach_reconciliation.py
  git diff --check
  ```

- [ ] **Step 6: Commit the correction**

  ```bash
  git add backend/app/services/coach_conversation_commands.py \
    backend/tests/test_services/test_coach_conversation_commands.py \
    backend/tests/test_services/test_coach_reconciliation.py
  git commit -m "fix(coach): resolve skip transaction state"
  ```

- [ ] **Step 7: Run release verification after review**

  Run the locked seven-file PR1 suite, migration suite, full backend suite,
  documentation validation, and exact `make ci`. Record exact pass, skip,
  warning, coverage, and frontend counts before declaring merge readiness.
