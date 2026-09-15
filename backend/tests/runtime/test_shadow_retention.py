"""R5's product-level retention check uses the shared 30-day shadow store."""

from datetime import datetime
from datetime import timedelta

from sqlalchemy import select

from app.runtime.evaluation.models import ShadowComparisonRecord
from app.runtime_bindings.migration.facade import record_job_score_shadow_comparison
from app.runtime_bindings.tasks.job_score import JobScoreInput, JobScoreOutput


def _request() -> JobScoreInput:
    return JobScoreInput(
        job_ref="job:synthetic-002",
        profile_ref="profile:synthetic",
        event_ref="event:synthetic-002",
    )


def _result() -> JobScoreOutput:
    return JobScoreOutput(
        skill_match=0.8,
        experience_match=0.8,
        rate_match=0.8,
        location_match=0.8,
        overall_score=0.8,
        reasoning="synthetic_reason",
        keyword_matches=(),
        keyword_misses=(),
        fit_reasoning=None,
        strengths=(),
        score_gaps=(),
        scoring_method="local",
    )


async def test_shadow_retention_purge_removes_expired_comparisons(
    workflow_runtime,
) -> None:
    _, factory = workflow_runtime
    async with factory.transaction() as uow:
        await record_job_score_shadow_comparison(
            uow.shadow,
            request=_request(),
            legacy_result=_result(),
            runtime_result=_result(),
            created_at=datetime(2030, 1, 1),
        )
        await uow.commit()

    async with factory.transaction() as uow:
        assert await uow.shadow.purge_expired(now=datetime(2030, 1, 31)) == 1
        await uow.commit()

    async with factory.session_factory() as session:
        assert list((await session.scalars(select(ShadowComparisonRecord))).all()) == []


async def test_startup_retention_purges_and_registers_daily_retry(workflow_runtime):
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from app.runtime_bindings.migration.retention import install_shadow_retention

    _, factory = workflow_runtime
    async with factory.transaction() as uow:
        await record_job_score_shadow_comparison(
            uow.shadow,
            request=_request(),
            legacy_result=_result(),
            runtime_result=_result(),
            created_at=datetime(2000, 1, 1),
        )
        await uow.commit()
    scheduler = AsyncIOScheduler()
    await install_shadow_retention(scheduler, factory)
    async with factory.session_factory() as session:
        assert list(await session.scalars(select(ShadowComparisonRecord))) == []
    maintenance = scheduler.get_job("runtime-shadow-retention")
    assert maintenance.trigger.interval == timedelta(days=1)
    # Invoke the registered production callback against another expired row.
    async with factory.transaction() as uow:
        await record_job_score_shadow_comparison(
            uow.shadow,
            request=_request(),
            legacy_result=_result(),
            runtime_result=_result(),
            created_at=datetime(2000, 1, 1),
        )
        await uow.commit()
    await maintenance.func(**maintenance.kwargs)
    async with factory.session_factory() as session:
        assert list(await session.scalars(select(ShadowComparisonRecord))) == []


async def test_purge_failure_is_observable_safe_and_next_run_retries(
    workflow_runtime, caplog
):
    from app.runtime_bindings.migration.retention import purge_shadow_comparisons

    _, factory = workflow_runtime

    class UnavailableDatabase:
        def transaction(self):
            raise RuntimeError("SYNTHETIC_PRIVATE_CANARY")

    assert await purge_shadow_comparisons(UnavailableDatabase()) is None
    assert "shadow_purge_failed" in caplog.text
    assert "SYNTHETIC_PRIVATE_CANARY" not in caplog.text
    assert await purge_shadow_comparisons(factory) == 0


async def test_application_lifespan_installs_real_shadow_maintenance(
    workflow_runtime, monkeypatch
):
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from fastapi import FastAPI
    from app import main

    _, factory = workflow_runtime
    async with factory.transaction() as uow:
        await record_job_score_shadow_comparison(
            uow.shadow,
            request=_request(),
            legacy_result=_result(),
            runtime_result=_result(),
            created_at=datetime(2000, 1, 1),
        )
        await uow.commit()

    async def noop(*args, **kwargs):
        return 0

    scheduler = AsyncIOScheduler()
    monkeypatch.setattr(main, "init_db", noop)
    monkeypatch.setattr(main, "AsyncSessionLocal", factory.session_factory)
    monkeypatch.setattr(
        "app.services.coach_reconciliation.reconcile_stale_coach_state", noop
    )
    monkeypatch.setattr("app.agents.tools.context_checker.assert_context_budgets", noop)
    for name in (
        "JobRepository",
        "JobService",
        "ApplicationRepository",
        "ReminderService",
        "LLMClient",
        "EmailGenerator",
    ):
        monkeypatch.setattr(main, name, lambda *args, **kwargs: object())
    monkeypatch.setattr(main, "create_scheduler", lambda *args, **kwargs: scheduler)
    monkeypatch.setattr(main, "load_runtime", lambda: {"ai_mode": "not_configured"})
    monkeypatch.setattr(main.settings, "DIGEST_ENABLED", False)
    monkeypatch.setattr(main, "shutdown_telemetry", lambda **kwargs: None)
    async with main.lifespan(FastAPI()):
        assert scheduler.running
        assert scheduler.get_job(
            "runtime-shadow-retention"
        ).trigger.interval == timedelta(days=1)
        async with factory.session_factory() as session:
            assert list(await session.scalars(select(ShadowComparisonRecord))) == []
