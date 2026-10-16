"""Completed CV service tests: only the external model transport is synthetic."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.application import Application
from app.models.job import JobPosting
from app.models.document import GeneratedDocument
from app.runtime import RuntimeMode
from app.runtime.evaluation.models import ContextPackageRecord, ExecutionRecord
from app.runtime.workflow.models import TaskAttemptRecord
from app.schemas.profile import Profile
from app.services.tailor_service import TailorService


CANARY = "PRIVATE_ORCHID_739"
MASTER = {
    "personal": {"name": "Avery Example", "email": "avery@example.test"},
    "summary_variants": {"engineer": f"AWS engineer delivering {CANARY} platforms."},
    "skills": {"cloud": {"category": "Cloud", "items": ["AWS"]}},
    "experience": [
        {
            "role": "Engineer",
            "company": "Example & Sons",
            "period": "2020-2024",
            "achievements": [{"text": "Delivered AWS platform migrations."}],
        }
    ],
    "education": [
        {"qualification": "BSc", "institution": "Example University", "year": "2020"}
    ],
    "certifications": ["AWS Certified"],
}


class ModelTransport:
    """External provider double; prompts and selected model affect its output."""

    def __init__(self, state, name):
        self.state, self.name = state, name

    def bind(self, **kwargs):
        return self

    async def ainvoke(self, messages):
        prompt = "\n".join(message.content for message in messages)
        self.state.calls.append((self.name, prompt))
        if self.state.delay:
            import asyncio

            await asyncio.sleep(self.state.delay)
        if "CV CONTENT:" in prompt:
            raw = {"overall_score": 90, "format_warnings": [CANARY]}
        elif (
            "role_title" in prompt
            and "summary_variants" not in prompt
            and "best_summary" not in prompt
            and "tailor" not in messages[0].content.lower()
        ):
            raw = {
                "role_title": f"AWS Engineer {CANARY}",
                "ats_keywords": {"technical": ["AWS"]},
            }
        else:
            source = self.state.master
            raw = {
                "summary": next(iter(source["summary_variants"].values())),
                "skills": list(source["skills"].values()),
                "experience": [
                    {**item, "achievements": [a["text"] for a in item["achievements"]]}
                    for item in source["experience"]
                ],
                "education": source["education"],
                "certifications": source["certifications"],
            }
            if (
                getattr(self.state, "shadow_diff", False)
                and self.name != "legacy-profile"
            ):
                raw["summary"] = source["summary_variants"]["alternative"]
            if self.state.unsupported:
                raw["experience"][0]["achievements"][0] = (
                    "Invented Kubernetes revenue growth."
                )
        return SimpleNamespace(content=json.dumps(raw))


@pytest.fixture
async def cv_service(workflow_runtime, monkeypatch, tmp_path):
    _, factory = workflow_runtime
    state = SimpleNamespace(
        calls=[], master=deepcopy(MASTER), delay=0, unsupported=False
    )
    profile = Profile.model_validate(
        {
            "llm": {
                "provider": "ollama",
                "primary_model": "selected-primary",
                "triage_model": "unused-triage",
            }
        }
    )
    from app.agents.tools import llm_factory

    monkeypatch.setattr(llm_factory, "load_profile", lambda: profile)
    monkeypatch.setattr(
        llm_factory, "_build_model", lambda name, config: ModelTransport(state, name)
    )
    monkeypatch.setattr("app.services.llm_client.load_profile", lambda: profile)
    monkeypatch.setattr(
        "app.services.llm_client.get_json_model",
        lambda **kwargs: ModelTransport(state, "legacy-profile"),
    )
    monkeypatch.setattr("app.services.tailor_service.load_profile", lambda: profile)
    monkeypatch.setattr(
        "app.services.tailor_service._load_master_cv", lambda: deepcopy(state.master)
    )
    monkeypatch.setattr(
        "app.services.tailor_service._load_personal", lambda: state.master["personal"]
    )
    monkeypatch.setattr(
        "app.services.cv_tailor.load_master_cv", lambda: deepcopy(state.master)
    )
    monkeypatch.setattr(
        "app.services.docx_cv_builder._OUTPUT_BASE", tmp_path / "generated"
    )
    service = TailorService()
    service._cv_tailor._master_cv_loader = lambda: deepcopy(state.master)
    service._runtime_factory = factory
    async with factory.session_factory() as db:
        db.add(
            JobPosting(
                id="job-r6",
                title="AWS Engineer",
                url="https://example.test/r6",
                source="manual",
            )
        )
        await db.flush()
        db.add(Application(id="app-r6", job_id="job-r6", status="discovered"))
        await db.commit()
    return service, factory, state


async def generate(fixture, **kwargs):
    service, factory, _ = fixture
    async with factory.session_factory() as db:
        return await service.generate_cv(
            "app-r6",
            "A",
            f"AWS Engineer {CANARY}",
            db,
            _resolved_mode=RuntimeMode.NEW,
            **kwargs,
        )


async def test_real_service_binds_routed_models_context_artifact_and_finalization(
    cv_service, caplog
):
    doc = await generate(cv_service)
    service, factory, state = cv_service
    assert Path(doc.file_path).is_file()
    assert {name for name, _ in state.calls} == {"selected-primary"}
    async with factory.session_factory() as db:
        executions = list(await db.scalars(select(ExecutionRecord)))
        assert {e.capability_id for e in executions} >= {
            "cv.tailor.analyse",
            "cv.tailor.generate",
            "cv.tailor.evaluate",
            "artifact.render_cv",
        }
        assert all(
            e.model_id == "configured-primary"
            for e in executions
            if e.capability_id != "artifact.render_cv"
        )
        context = await db.scalar(select(ContextPackageRecord))
        assert len(context.items_json["items"]) == 6
        attempt = await db.scalar(select(TaskAttemptRecord))
        assert attempt.status == "succeeded"
        assert (
            attempt.result_ref_json["artifact_bytes"]
            == Path(doc.file_path).stat().st_size
        )
        assert (
            attempt.result_ref_json["artifact_hash"]
            == hashlib.sha256(Path(doc.file_path).read_bytes()).hexdigest()
        )
        row = await db.get(GeneratedDocument, doc.id)
        assert CANARY not in json.dumps(
            {c.name: str(getattr(row, c.name)) for c in row.__table__.columns}
        )
        history = await service.get_document_history("app-r6", None, db)
        assert len(history) == 1
    assert CANARY not in caplog.text


async def test_redelivery_reuses_document_but_new_request_can_repeat(cv_service):
    first = await generate(
        cv_service, request_ref="request:one", delivery_ref="delivery:one"
    )
    second = await generate(
        cv_service, request_ref="request:one", delivery_ref="delivery:one"
    )
    third = await generate(
        cv_service, request_ref="request:two", delivery_ref="delivery:two"
    )
    assert first.id == second.id
    assert third.id != first.id
    assert Path(first.file_path).exists() and Path(third.file_path).exists()


async def test_compact_template_validates_its_actual_render_contract(cv_service):
    _, _, state = cv_service
    state.master["summary_variants"]["engineer"] = "AWS engineer " + " ".join(
        ["platform"] * 85
    )
    state.master["experience"][0]["achievements"] = [
        {"text": f"Delivered AWS platform {word}."}
        for word in ("design", "delivery", "testing", "operations")
    ]
    doc = await generate(cv_service, template_id="modern_compact")
    assert Path(doc.file_path).is_file()


async def test_shadow_links_real_comparable_results_without_runtime_artifacts(
    cv_service, caplog
):
    from app.models.cv_publication import CVPublication
    from app.runtime.evaluation.models import ShadowComparisonRecord

    service, factory, state = cv_service
    async with factory.session_factory() as db:
        doc = await service.generate_cv(
            "app-r6",
            "A",
            f"AWS Engineer {CANARY}",
            db,
            _resolved_mode=RuntimeMode.SHADOW,
        )
    async with factory.session_factory() as db:
        rows = list(await db.scalars(select(GeneratedDocument)))
        assert [row.id for row in rows] == [doc.id]
        assert not list(await db.scalars(select(CVPublication)))
        comparison = await db.scalar(select(ShadowComparisonRecord))
        assert comparison is not None
        assert await db.get(ExecutionRecord, comparison.legacy_execution_ref)
        assert await db.get(ExecutionRecord, comparison.runtime_execution_id)
        assert comparison.comparison_status == "same"
        assert comparison.legacy_result_hash == comparison.runtime_result_hash
        assert CANARY not in json.dumps(
            {c.name: str(getattr(rows[0], c.name)) for c in rows[0].__table__.columns}
        )
    assert CANARY not in caplog.text


async def test_repair_then_fallback_has_real_gateway_lineage_and_no_invented_prose(
    cv_service,
):
    from app.runtime_bindings.migration.cv_tailor import read_artifact_cv

    _, factory, state = cv_service
    state.unsupported = True
    doc = await generate(cv_service)
    cv = read_artifact_cv(doc.file_path)
    assert cv.experience[0].achievements == ["Delivered AWS platform migrations."]
    async with factory.session_factory() as db:
        records = list(
            await db.scalars(
                select(ExecutionRecord).order_by(ExecutionRecord.started_at)
            )
        )
        assert [r.execution_role for r in records] == [
            "tool",
            "primary",
            "repair",
            "fallback",
            "artifact",
            "evaluator",
        ]
        for previous, current in zip(records, records[1:]):
            assert current.parent_execution_id == previous.id


async def test_all_runtime_database_and_error_sinks_reject_content_canary(
    cv_service, caplog
):
    from app.database import Base
    from sqlalchemy import text

    await generate(cv_service)
    _, factory, _ = cv_service
    async with factory.session_factory() as db:
        for table in Base.metadata.sorted_tables:
            if table.name.startswith("runtime_") or table.name in {
                "cv_publications",
                "generated_documents",
                "async_jobs",
            }:
                rows = (await db.execute(text(f'SELECT * FROM "{table.name}"'))).all()
                assert CANARY not in repr(rows), table.name
    from app.agents.tools.llm_factory import get_llm_traces

    assert CANARY not in repr(get_llm_traces())
    assert CANARY not in caplog.text


async def test_finalize_refusal_never_exposes_document_history(cv_service, monkeypatch):
    from app.runtime.workflow import WorkflowKernel
    from fastapi import HTTPException

    service, factory, _ = cv_service

    async def refuse(*args, **kwargs):
        return False

    monkeypatch.setattr(WorkflowKernel, "finalize", refuse)
    with pytest.raises(HTTPException):
        await generate(cv_service)
    async with factory.session_factory() as db:
        assert not await service.get_document_history("app-r6", None, db)


async def test_full_package_reuses_committed_cv_and_honors_both_variants(
    cv_service, monkeypatch
):
    from app.runtime_bindings.migration.cv_tailor import read_artifact_cv
    from app.schemas.tailor import CoverLetterResult

    service, factory, state = cv_service
    seen = []

    async def cover(analysis, cv, personal, variant, **kwargs):
        seen.append(cv)
        return CoverLetterResult(
            subject_line="Application",
            greeting="Hello",
            body_paragraphs=["Synthetic letter"],
            sign_off="Regards",
            word_count=2,
        )

    # Cover-letter generation itself belongs to R7; only its CV input is in R6.
    monkeypatch.setattr(service._cl_generator, "generate", cover)
    monkeypatch.setattr(
        "app.services.docx_cl_builder._OUTPUT_BASE",
        Path(
            service._cv_builder.staging_paths("app-r6", 0, "A", "probe")[1]
        ).parent.parent,
    )
    async with factory.session_factory() as db:
        bundle = await service.generate_all(
            "app-r6",
            "A",
            f"AWS Engineer {CANARY}",
            db,
            generate_variants=True,
            _resolved_mode=RuntimeMode.NEW,
            delivery_ref="delivery:package",
        )
        replay = await service.generate_all(
            "app-r6",
            "A",
            f"AWS Engineer {CANARY}",
            db,
            generate_variants=True,
            _resolved_mode=RuntimeMode.NEW,
            delivery_ref="delivery:package",
        )
    async with factory.session_factory() as db:
        cvs = list(
            await db.scalars(
                select(GeneratedDocument).where(GeneratedDocument.document_type == "cv")
            )
        )
    assert {doc.variant_label for doc in cvs} == {"A", "B"}
    assert len(seen) == 2
    assert bundle.cl_document_id == replay.cl_document_id
    for cv, doc in zip(seen, cvs):
        assert cv.model_dump() == read_artifact_cv(doc.file_path).model_dump()
    assert bundle.ats_score.overall_score == cvs[0].ats_score
    assert len([name for name, _ in state.calls if name == "legacy-profile"]) == 0


@pytest.mark.parametrize(
    "mode", [RuntimeMode.NEW, RuntimeMode.SHADOW, RuntimeMode.LEGACY]
)
async def test_completed_http_async_history_download_and_rollback(
    cv_service, monkeypatch, mode
):
    import asyncio
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.database import get_db
    from app.routers.tailor import router, get_tailor_service
    from app.models.async_job import AsyncJob
    from app.config import settings

    service, factory, state = cv_service
    monkeypatch.setattr("app.database.AsyncSessionLocal", factory.session_factory)
    monkeypatch.setattr(settings, "HATCH_RUNTIME_CV_TAILOR_MODE", mode)
    monkeypatch.setattr(
        "app.routers.tailor.resolve_master_cv_path", lambda: Path(__file__)
    )
    api = FastAPI()
    api.include_router(router)

    async def database():
        async with factory.session_factory() as db:
            yield db

    api.dependency_overrides[get_db] = database
    api.dependency_overrides[get_tailor_service] = lambda: service
    async with AsyncClient(
        transport=ASGITransport(app=api), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/tailor/generate-cv",
            json={
                "application_id": "app-r6",
                "variant": "A",
                "jd_text": f"AWS Engineer {CANARY}",
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        for _ in range(200):
            async with factory.session_factory() as db:
                job = await db.get(AsyncJob, job_id)
            if job.status in {"done", "failed"}:
                break
            await asyncio.sleep(0.025)
        assert job.status == "done", job.error
        result = json.loads(job.result_json)
        history = await client.get("/api/tailor/history/app-r6")
        assert [item["id"] for item in history.json()] == [result["id"]]
        download = await client.get(f"/api/tailor/document/{result['id']}/download")
        assert download.status_code == 200
        assert download.content.startswith(b"PK")
        if mode != RuntimeMode.LEGACY:
            assert CANARY not in job.result_json


async def test_cancelled_renderer_waits_for_cleanup_without_publication(
    cv_service, monkeypatch
):
    import asyncio
    import threading
    from app.models.cv_publication import CVPublication

    service, factory, _ = cv_service
    started, release = threading.Event(), threading.Event()
    original = service._cv_builder.build_staged

    def slow(*args, **kwargs):
        started.set()
        release.wait(3)
        return original(*args, **kwargs)

    monkeypatch.setattr(service._cv_builder, "build_staged", slow)
    task = asyncio.create_task(generate(cv_service))
    await asyncio.to_thread(started.wait, 3)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with factory.session_factory() as db:
        assert not list(await db.scalars(select(GeneratedDocument)))
        row = await db.scalar(select(CVPublication))
        assert row.state == "aborted"
        assert not Path(row.staged_path).exists()
        assert not Path(row.final_path).exists()


async def test_ambiguous_final_commit_reconciles_without_model_or_render_repeat(
    cv_service, monkeypatch
):
    from app.runtime.workflow import WorkflowKernel
    from app.models.cv_publication import CVPublication
    from fastapi import HTTPException

    service, factory, state = cv_service
    original = WorkflowKernel.finalize

    async def interrupted(self, claim, result, **kwargs):
        async def projection(uow):
            await kwargs["projection"](uow)
            raise OSError(CANARY)

        return await original(self, claim, result, projection=projection)

    monkeypatch.setattr(WorkflowKernel, "finalize", interrupted)
    with pytest.raises(HTTPException):
        await generate(cv_service, delivery_ref="delivery:crash")
    count = len(state.calls)
    async with factory.session_factory() as db:
        assert not list(await db.scalars(select(GeneratedDocument)))
        row = await db.scalar(select(CVPublication))
        assert row.state == "staged" and Path(row.final_path).exists()
        # Simulate a restarted worker after its former owner's lease expired.
        from app.runtime.workflow.models import ExecutionClaimRecord
        from datetime import datetime, timedelta

        claim = await db.get(ExecutionClaimRecord, row.id)
        claim.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
        await db.commit()
    monkeypatch.setattr(WorkflowKernel, "finalize", original)
    doc = await generate(cv_service, delivery_ref="delivery:crash")
    assert len(state.calls) == count
    assert Path(doc.file_path).exists()
    async with factory.session_factory() as db:
        assert len(list(await db.scalars(select(GeneratedDocument)))) == 1


async def test_shadow_success_with_different_content_is_never_same(cv_service):
    from app.runtime.evaluation.models import ShadowComparisonRecord

    service, factory, state = cv_service
    state.master["summary_variants"]["alternative"] = (
        "AWS engineer with platform delivery experience."
    )
    state.shadow_diff = True
    async with factory.session_factory() as db:
        await service.generate_cv(
            "app-r6", "A", "AWS Engineer", db, _resolved_mode=RuntimeMode.SHADOW
        )
    async with factory.session_factory() as db:
        comparison = await db.scalar(select(ShadowComparisonRecord))
        assert comparison.comparison_status == "different"
        assert comparison.legacy_result_hash != comparison.runtime_result_hash


async def test_real_latency_renews_runtime_lease(cv_service, monkeypatch):
    from datetime import timedelta
    from app.runtime.workflow import WorkflowKernel
    from app.runtime.workflow.models import ExecutionClaimRecord
    from app.runtime_bindings.migration.cv_tailor import DurableCVTailorRuntime

    _, factory, state = cv_service
    # Keep the model call longer than the initial lease while leaving enough
    # scheduler headroom for coverage-instrumented full-suite runs.  The former
    # 20 ms / 80 ms timing window could expire during ordinary SQLite or event
    # loop contention, making this lifecycle assertion nondeterministic.
    state.delay = 0.9
    original = DurableCVTailorRuntime.__init__

    def configure(self, *args, **kwargs):
        original(self, *args, **kwargs, heartbeat_seconds=0.1)

    monkeypatch.setattr(DurableCVTailorRuntime, "__init__", configure)
    monkeypatch.setattr(
        "app.services.tailor_service.WorkflowKernel",
        lambda factory: WorkflowKernel(factory, lease_duration=timedelta(seconds=0.8)),
    )
    doc = await generate(cv_service)
    assert Path(doc.file_path).exists()
    async with factory.session_factory() as db:
        claim = await db.scalar(select(ExecutionClaimRecord))
        assert (claim.lease_expires_at - claim.claimed_at).total_seconds() > 0.8


async def test_model_timeout_is_metadata_only_and_never_publishes(
    cv_service, monkeypatch, caplog
):
    from app.runtime_bindings.migration.cv_tailor import DurableCVTailorRuntime
    from fastapi import HTTPException

    _, factory, state = cv_service
    state.delay = 0.2
    original = DurableCVTailorRuntime.__init__

    def configure(self, *args, **kwargs):
        original(self, *args, **kwargs, model_timeout=0.03)

    monkeypatch.setattr(DurableCVTailorRuntime, "__init__", configure)
    with pytest.raises(HTTPException) as error:
        await generate(cv_service)
    assert CANARY not in str(error.value)
    async with factory.session_factory() as db:
        assert not list(await db.scalars(select(GeneratedDocument)))
        assert (await db.scalar(select(ExecutionRecord))).result_class == "timeout"
    assert CANARY not in caplog.text


async def test_partial_renderer_failure_cleans_owned_stage_and_hides_history(
    cv_service, monkeypatch, caplog
):
    from fastapi import HTTPException
    from app.models.cv_publication import CVPublication

    service, factory, state = cv_service

    def partial(cv, jd, personal, application, version, variant, *args, **kwargs):
        staged, _ = service._cv_builder.staging_paths(
            application, version, variant, kwargs["attempt_id"]
        )
        Path(staged).parent.mkdir(parents=True, exist_ok=True)
        Path(staged).write_text(CANARY)
        raise OSError(CANARY)

    monkeypatch.setattr(service._cv_builder, "build_staged", partial)
    with pytest.raises(HTTPException) as error:
        await generate(cv_service)
    async with factory.session_factory() as db:
        assert not list(await db.scalars(select(GeneratedDocument)))
        row = await db.scalar(select(CVPublication))
        assert row.state == "aborted"
        assert not Path(row.staged_path).exists()
    assert CANARY not in str(error.value) + caplog.text
    assert not any("CV CONTENT:" in prompt for _, prompt in state.calls)
