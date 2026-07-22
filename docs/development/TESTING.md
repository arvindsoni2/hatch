# Testing

Common checks:

```bash
make test
make lint
docker compose config --quiet
```

Frontend:

```bash
cd frontend
npm run type-check
npm test
npx playwright test
```

Backend:

```bash
cd backend
python -m pytest
```

Coach C1 contract and correctness checks:

```bash
cd backend
pytest -q --no-cov \
  tests/test_services/test_question_generator.py \
  tests/test_services/test_model_answer_gen.py \
  tests/test_services/test_answer_evaluator.py \
  tests/test_services/test_rubric_builder.py \
  tests/test_services/test_rubric_synthesiser.py \
  tests/test_services/test_feedback_generator.py \
  tests/test_services/test_technical_drills.py \
  tests/test_services/test_followup_planner.py \
  tests/test_services/test_coach_prompt_contracts.py \
  tests/test_services/test_coach_session_queue.py \
  tests/test_services/test_coach_contracts.py \
  tests/test_services/test_coach_reconciliation.py \
  tests/test_migrations/test_coach_c1_migration.py \
  tests/test_routers/test_coach_router.py \
  tests/test_routers/test_coach_async.py
```

Frontend Coach compatibility checks:

```bash
cd frontend
npx vitest run \
  src/__tests__/components/coach/EvaluationCard.test.tsx \
  src/__tests__/components/coach/FeedbackReport.test.tsx \
  src/__tests__/components/CoachSessionQuestionBank.test.tsx \
  src/__tests__/components/CoachSessionRetry.test.tsx
npm run type-check
```
