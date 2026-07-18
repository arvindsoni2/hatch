from __future__ import annotations

import json
import asyncio
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.schemas.tailor import (
    ATSKeywords,
    CompanyContext,
    JDAnalysisResult,
    Requirements,
)
from benchmarks.adapters import BenchmarkModelUnavailableError, BenchmarkTimeoutError, GenerationObservation
from benchmarks.contracts import BenchmarkCase, BenchmarkProfile, ExpectedFacts, ModelSpec, RoleFact
from benchmarks import runner
from benchmarks.runner import run_benchmark


def _case() -> BenchmarkCase:
    bullet = (
        "Led a cross-functional Scrum delivery team and managed the product backlog "
        "through planning, review, and retrospective ceremonies."
    )
    master = {
        "personal": {"full_name": "Alex Example", "email": "alex@example.test"},
        "summary_variants": {
            "delivery": "Delivery Manager experienced in Scrum, Kanban, coaching, and hybrid delivery."
        },
        "skills": {
            "delivery": {
                "category": "Delivery & Leadership",
                "items": ["Scrum", "Kanban", "Product backlog", "Coaching"],
            }
        },
        "experience": [
            {
                "role": "Delivery Manager",
                "company": "Example Ltd",
                "period": "2020 - Present",
                "achievements": [{"text": bullet}],
            }
        ],
        "education": [],
        "certifications": ["PSM I"],
    }
    models = [
        ModelSpec(
            id=model_id,
            runtime="ollama",
            model=model_id,
            endpoint="http://127.0.0.1:11434",
            context_size=16384,
        )
        for model_id in ("qwen35-4b", "unsafe")
    ]
    return BenchmarkCase(
        case_id="synthetic-delivery",
        source_dir=Path("/tmp/synthetic"),
        master_cv=master,
        job_description="Delivery Manager requiring Scrum, Kanban, coaching, and backlog management.",
        jd_analysis=JDAnalysisResult(
            role_title="Delivery Manager",
            requirements=Requirements(
                must_have=["Scrum", "Kanban", "product backlog", "coaching"]
            ),
            ats_keywords=ATSKeywords(
                methodologies=["Scrum", "Kanban"],
                soft_skills=["coaching"],
                domain=["product backlog"],
            ),
            company_context=CompanyContext(company_name="Target Ltd", sector="software"),
        ),
        expected_facts=ExpectedFacts(
            roles=[
                RoleFact(
                    role="Delivery Manager",
                    company="Example Ltd",
                    period="2020 - Present",
                    achievement_count=1,
                )
            ],
            certifications=["PSM I"],
            allowed_numeric_tokens=["2020"],
        ),
        models=models,
        seeds=[11, 23, 41],
        cv_length_tolerance=0.1,
        input_hashes={"case.json": "abc"},
    )


def _cv_payload(case: BenchmarkCase) -> dict[str, Any]:
    master = case.master_cv
    return {
        "summary": master["summary_variants"]["delivery"],
        "skills": [
            {
                "category": "Delivery & Leadership",
                "items": ["Scrum", "Kanban", "Product backlog", "Coaching"],
            }
        ],
        "experience": [
            {
                "role": "Delivery Manager",
                "company": "Example Ltd",
                "period": "2020 - Present",
                "achievements": [master["experience"][0]["achievements"][0]["text"]],
            }
        ],
        "education": [],
        "certifications": ["PSM I"],
        "ats_keywords_embedded": ["Scrum", "Kanban", "product backlog", "coaching"],
        "tailoring_notes": "Grounded delivery emphasis.",
    }


def _cl_payload(*, unsafe: bool = False) -> dict[str, Any]:
    sentence = (
        "I offer grounded Delivery Manager experience using Scrum and Kanban to coach teams, "
        "manage the product backlog, and lead hybrid delivery for Example Ltd."
    )
    paragraphs = [" ".join([sentence] * 3) for _ in range(4)]
    if unsafe:
        paragraphs[1] += " I increased productivity by 97%."
    return {
        "subject_line": "Application: Delivery Manager - Target Ltd",
        "greeting": "Dear Hiring Manager,",
        "body_paragraphs": paragraphs,
        "sign_off": "Kind regards,",
        "word_count": len(" ".join(paragraphs).split()),
        "key_keywords_used": ["Scrum", "Kanban", "product backlog", "coaching"],
    }


class FakeClient:
    def __init__(self, spec: ModelSpec, seed: int, order: list[tuple[str, int]]) -> None:
        self.spec = spec
        self.seed = seed
        self.order = order
        self.calls = 0
        self.raw_responses: list[str] = []
        self.observations: list[GenerationObservation] = []

    async def complete_json(self, system: str, user: str, max_tokens: int = 4096) -> dict:
        del user, max_tokens
        self.calls += 1
        if self.calls == 1:
            payload = _cv_payload(CASE)
        else:
            payload = _cl_payload(unsafe=self.spec.id == "unsafe")
        self.raw_responses.append(json.dumps(payload))
        self.observations.append(
            GenerationObservation(
                attempt=1,
                duration_ms=10.0 if "cover letter" in system.lower() else 20.0,
                status_code=200,
                prompt_tokens=100,
                completion_tokens=50,
            )
        )
        return deepcopy(payload)

    async def aclose(self) -> None:
        self.order.append((self.spec.id, self.seed))


CASE = _case()


def test_database_path_preserves_absolute_aiosqlite_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "jobpilot.db"
    monkeypatch.setattr(
        runner.settings,
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{database}",
    )

    assert runner._database_path() == database


def test_protected_hashes_include_sqlite_wal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "jobpilot.db"
    database.write_bytes(b"database")
    wal = Path(f"{database}-wal")
    wal.write_bytes(b"before")
    monkeypatch.setattr(
        runner.settings,
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{database}",
    )
    monkeypatch.setattr(runner, "current_profile_hash", lambda: "profile")

    before = runner._protected_hashes()
    wal.write_bytes(b"after")

    assert runner._protected_hashes()["database"] != before["database"]


@pytest.mark.asyncio
async def test_runner_ranks_gate_pass_rate_before_quality(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[tuple[str, int]] = []

    def factory(spec: ModelSpec, seed: int) -> FakeClient:
        return FakeClient(spec, seed, order)

    def fake_probe(url: str) -> dict[str, Any]:
        return {"url": url, "status_code": 204}

    monkeypatch.setattr(runner, "_probe_http", fake_probe)

    summary = await run_benchmark(
        CASE,
        model_ids=["qwen35-4b", "unsafe"],
        repetitions=3,
        output_root=tmp_path,
        adapter_factory=factory,
        run_id="test-run",
    )

    assert summary.ranking[0].model_id == "qwen35-4b"
    assert summary.ranking[0].hard_gate_pass_rate == 1.0
    assert summary.ranking[1].hard_gate_pass_rate == 0.0
    assert order == [
        ("qwen35-4b", 11),
        ("qwen35-4b", 23),
        ("qwen35-4b", 41),
        ("unsafe", 11),
        ("unsafe", 23),
        ("unsafe", 41),
    ]
    assert (tmp_path / "test-run" / "summary.json").exists()
    manifest = json.loads(
        (tmp_path / "test-run" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["prompt_versions"]["cv_tailoring"] == "2.0.0"
    assert manifest["prompt_versions"]["cover_letter_generation"] == "2.0.0"
    assert manifest["schema_versions"]["evidence_ledger"] == "1.0.0"
    manifest = json.loads((tmp_path / "test-run" / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["accepted_baseline_merge_sha"] == "a5a4d729a4dfddcabb2ec4ca54c91120f616f6de"
    assert manifest["repository_commit"]
    assert manifest["working_tree_clean_before"] in {True, False}
    assert manifest["working_tree_clean_after"] in {True, False}
    assert manifest["protected_hashes"]["unchanged"] in {True, False, "not_recorded"}
    assert manifest["health"] == {
        "backend": {"url": "http://127.0.0.1:8000/api/health", "status_code": 204},
        "frontend": {"url": "http://127.0.0.1:3000", "status_code": 204},
    }
    assert "cover_letter_generation" in manifest["prompt_versions"]
    artifact = tmp_path / "test-run" / "runs" / "qwen35-4b" / "01" / "result.json"
    raw = tmp_path / "test-run" / "runs" / "qwen35-4b" / "01" / "raw_responses.json"
    assert artifact.exists()
    assert raw.exists()
    result_payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert (
        result_payload["prompt_metadata"]["cv_tailoring"]["schema_version"]
        == "1.0.0"
    )
    assert (
        result_payload["prompt_metadata"]["cover_letter_generation"][
            "prompt_version"
        ]
        == "2.0.0"
    )
    assert "cover_letter_repair" not in result_payload["prompt_metadata"]
    assert (
        "cover_letter_paragraph_regeneration"
        not in result_payload["prompt_metadata"]
    )
    assert result_payload["first_pass_cover_letter_word_count"] == result_payload["final_cover_letter_word_count"]
    assert result_payload["cover_letter_repair_count"] == 0
    metrics = result_payload["pair_metrics"]
    assert metrics["schema_succeeded"] is True
    assert metrics["post_repair_hard_gate_passed"] is True
    assert metrics["first_pass_hard_gate_passed"] is True
    assert metrics["unsupported_candidate_claims"] == 0
    assert metrics["unsupported_numeric_tokens"] == 0
    assert metrics["immutable_token_mutations"] == 0
    assert metrics["prompt_tokens"] == 200
    assert metrics["output_tokens"] == 100
    assert metrics["tokens_per_eligible_pair"] == 300
    assert metrics["normalized_combined_quality"] == result_payload["score"]["combined"]
    workflow = result_payload["workflow_diagnostics"]
    assert workflow["skill_id"] == "cover-letter"
    assert workflow["skill_version"] == "1.0.0"
    assert workflow["final_state"] in {
        "passed",
        "repaired",
        "review_required",
    }
    assert workflow["attempts"][0]["attempt_number"] == 1
    serialized_workflow = json.dumps(workflow)
    assert CASE.master_cv["personal"]["email"] not in serialized_workflow
    assert CASE.master_cv["experience"][0]["achievements"][0]["text"] not in serialized_workflow
    assert _cl_payload()["body_paragraphs"][0] not in serialized_workflow
    raw_payloads = json.loads(raw.read_text(encoding="utf-8"))
    assert json.loads(raw_payloads[0])["summary"].startswith(
        "Delivery Manager"
    )


def test_pair_metrics_separate_first_pass_repair_and_evidence_coverage() -> None:
    from types import SimpleNamespace

    from app.services.writing_contracts import build_evidence_ledger
    from benchmarks.contracts import PairScore
    from benchmarks.runner import _pair_metrics

    ledger = build_evidence_ledger(CASE.master_cv)
    used_ids = [item.id for item in ledger[:2]]
    cv = SimpleNamespace(
        blocking_issues=[],
        generation_provenance=SimpleNamespace(
            source_evidence_ids=tuple(used_ids[:1]),
        ),
    )
    letter = SimpleNamespace(
        validation_status="repaired",
        validation_issues=[],
        grounding_issues=[],
        generation_provenance=SimpleNamespace(
            source_evidence_ids=tuple(item.id for item in ledger),
            content_plan={
                "opening_evidence_ids": used_ids[:1],
                "primary_evidence_ids": used_ids[1:],
                "secondary_evidence_ids": [],
                "alignment_job_requirement_ids": ["jobreq-1"],
            },
            workflow={
                "final_state": "repaired",
                "attempts": [
                    {
                        "latency_ms": 800,
                        "input_tokens": 100,
                        "output_tokens": 40,
                        "validator_results": {
                            "passed": False,
                            "issues": [
                                {
                                    "gate": "word_count",
                                    "code": "under_length",
                                    "severity": "blocking",
                                    "message": "too short",
                                }
                            ],
                        },
                    },
                    {
                        "latency_ms": 300,
                        "input_tokens": 50,
                        "output_tokens": 20,
                        "validator_results": {
                            "passed": True,
                            "issues": [],
                        },
                    },
                ],
            },
        ),
    )
    metrics = _pair_metrics(
        CASE,
        cv,
        letter,
        PairScore(eligible=True, combined=88.5),
        observations=[],
        duration_ms=1400,
    )

    assert metrics.first_pass_hard_gate_passed is False
    assert metrics.post_repair_hard_gate_passed is True
    assert metrics.first_pass_latency_ms == 800
    assert metrics.repair_latency_ms == 300
    assert metrics.eligible_pair_latency_ms == 1400
    assert metrics.prompt_tokens == 150
    assert metrics.output_tokens == 60
    assert metrics.tokens_per_eligible_pair == 210
    assert metrics.evidence_items_used == 2
    assert metrics.evidence_items_available == len(ledger)
    assert metrics.evidence_coverage == pytest.approx(2 / len(ledger))


def test_sparse_review_required_is_recorded_as_safe_fallback() -> None:
    from types import SimpleNamespace

    from benchmarks.contracts import PairScore
    from benchmarks.runner import _pair_metrics

    sparse_case = CASE.model_copy(
        update={"risk_tags": {"sparse_evidence"}}
    )
    cv = SimpleNamespace(
        blocking_issues=[],
        generation_provenance=None,
    )
    letter = SimpleNamespace(
        validation_status="review_required",
        validation_issues=["missing candidate evidence"],
        grounding_issues=[],
        generation_provenance=SimpleNamespace(
            source_evidence_ids=(),
            content_plan={},
            workflow={"final_state": "review_required", "attempts": []},
        ),
    )

    metrics = _pair_metrics(
        sparse_case,
        cv,
        letter,
        PairScore(eligible=False),
        observations=[],
        duration_ms=100,
    )

    assert metrics.missing_evidence_safe_fallback is True
    assert metrics.missing_evidence_case is True
    assert metrics.post_repair_hard_gate_passed is False
    assert metrics.normalized_combined_quality is None


@pytest.mark.asyncio
async def test_runner_preserves_partial_failure_and_continues(tmp_path: Path) -> None:
    order: list[tuple[str, int]] = []

    class FailingClient(FakeClient):
        async def complete_json(self, system: str, user: str, max_tokens: int = 4096) -> dict:
            if self.seed == 23:
                raise RuntimeError("synthetic inference failure")
            return await super().complete_json(system, user, max_tokens)

    def factory(spec: ModelSpec, seed: int) -> FakeClient:
        return FailingClient(spec, seed, order)

    summary = await run_benchmark(
        CASE,
        model_ids=["qwen35-4b"],
        repetitions=3,
        output_root=tmp_path,
        adapter_factory=factory,
        run_id="partial-run",
    )

    aggregate = summary.models[0]
    assert aggregate.attempted == 3
    assert aggregate.succeeded == 2
    assert aggregate.failed == 1
    failure_path = tmp_path / "partial-run" / "runs" / "qwen35-4b" / "02" / "result.json"
    failure = json.loads(failure_path.read_text(encoding="utf-8"))
    assert failure["status"] == "failed"
    assert failure["error_type"] == "RuntimeError"


@pytest.mark.asyncio
async def test_runner_marks_unavailable_model_and_continues(tmp_path: Path) -> None:
    case = _case()
    case.models[0].id = "missing"
    order: list[tuple[str, int]] = []

    class UnavailableClient(FakeClient):
        async def complete_json(self, system: str, user: str, max_tokens: int = 4096) -> dict:
            if self.spec.id == "missing":
                raise BenchmarkModelUnavailableError("model is not installed")
            return await super().complete_json(system, user, max_tokens)

    def factory(spec: ModelSpec, seed: int) -> FakeClient:
        return UnavailableClient(spec, seed, order)

    summary = await run_benchmark(
        case,
        model_ids=["missing", "unsafe"],
        repetitions=1,
        output_root=tmp_path,
        adapter_factory=factory,
        run_id="unavailable-run",
    )

    assert summary.models[0].unavailable == 1
    assert summary.models[1].succeeded == 1
    result_path = tmp_path / "unavailable-run" / "runs" / "missing" / "01" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "unavailable"


@pytest.mark.asyncio
async def test_acceptance_profile_times_out_model_and_writes_incremental_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case()
    order: list[tuple[str, int]] = []

    class SlowClient(FakeClient):
        async def complete_json(self, system: str, user: str, max_tokens: int = 4096) -> dict:
            if self.spec.id == "qwen35-4b":
                await asyncio.sleep(0.05)
            return await super().complete_json(system, user, max_tokens)

    def factory(spec: ModelSpec, seed: int) -> FakeClient:
        return SlowClient(spec, seed, order)

    profile = BenchmarkProfile(
        name="acceptance-smoke",
        call_timeout_seconds=0.01,
        model_timeout_seconds=0.01,
        whole_run_timeout_seconds=60.0,
    )
    monkeypatch.setattr(runner, "_probe_http", lambda url: {"url": url, "status_code": 204})

    summary = await run_benchmark(
        case,
        model_ids=["qwen35-4b", "unsafe"],
        repetitions=1,
        output_root=tmp_path,
        adapter_factory=factory,
        run_id="acceptance-timeout",
        profile=profile,
    )

    timeout_model = summary.models[0]
    completed_model = summary.models[1]
    assert timeout_model.timeout == 1
    assert timeout_model.succeeded == 0
    assert completed_model.succeeded == 1
    assert summary.recommendation.classification == "inconclusive"
    assert "does not select a model" in summary.recommendation.rationale[0]
    assert order == [("qwen35-4b", 11), ("unsafe", 11)]

    run_dir = tmp_path / "acceptance-timeout"
    progress = json.loads((run_dir / "progress.json").read_text(encoding="utf-8"))
    assert progress["benchmark_profile"] == "acceptance-smoke"
    assert progress["models"]["qwen35-4b"]["execution_status"] == "timeout"
    assert progress["models"]["qwen35-4b"]["completed_repetitions"] == 0
    assert progress["models"]["qwen35-4b"]["requested_repetitions"] == 1
    assert progress["models"]["unsafe"]["execution_status"] == "completed"

    timeout_payload = json.loads(
        (run_dir / "models" / "qwen35-4b" / "repetition-001.json").read_text(encoding="utf-8")
    )
    assert timeout_payload["availability"] == "available"
    assert timeout_payload["status"] == "timeout"
    assert timeout_payload["execution_status"] == "timeout"
    assert timeout_payload["timeout_stage"] == "model"
    assert timeout_payload["eligible_for_ranking"] is False

    assert (run_dir / "summary.json").exists()
    assert (run_dir / "aggregate.json").exists()
    assert (run_dir / "report.md").exists()
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["benchmark_profile"] == "acceptance-smoke"
    assert manifest["completion_state"] == "completed_with_model_outcomes"
    assert manifest["timeout_settings"] == {
        "call_timeout_seconds": 0.01,
        "model_timeout_seconds": 0.01,
        "whole_run_timeout_seconds": 60.0,
    }
    assert manifest["requested_repetitions"] == 1
    assert manifest["health"]["backend"]["status_code"] == 204


@pytest.mark.asyncio
async def test_call_timeout_error_is_recorded_as_timeout_not_generic_failure(
    tmp_path: Path,
) -> None:
    order: list[tuple[str, int]] = []

    class CallTimeoutClient(FakeClient):
        async def complete_json(self, system: str, user: str, max_tokens: int = 4096) -> dict:
            raise BenchmarkTimeoutError("synthetic call timeout")

    def factory(spec: ModelSpec, seed: int) -> FakeClient:
        return CallTimeoutClient(spec, seed, order)

    summary = await run_benchmark(
        CASE,
        model_ids=["qwen35-4b"],
        repetitions=1,
        output_root=tmp_path,
        adapter_factory=factory,
        run_id="call-timeout-run",
        profile=BenchmarkProfile(name="acceptance-smoke"),
    )

    assert summary.models[0].timeout == 1
    assert summary.models[0].failed == 0
    result = json.loads(
        (tmp_path / "call-timeout-run" / "models" / "qwen35-4b" / "repetition-001.json").read_text(
            encoding="utf-8"
        )
    )
    assert result["status"] == "timeout"
    assert result["execution_status"] == "timeout"
    assert result["timeout_stage"] == "call"
    assert result["error_type"] == "BenchmarkTimeoutError"


@pytest.mark.asyncio
async def test_whole_run_deadline_preserves_partial_results_and_stops_launching_models(
    tmp_path: Path,
) -> None:
    order: list[tuple[str, int]] = []

    def factory(spec: ModelSpec, seed: int) -> FakeClient:
        return FakeClient(spec, seed, order)

    profile = BenchmarkProfile(
        name="acceptance-smoke",
        call_timeout_seconds=60.0,
        model_timeout_seconds=60.0,
        whole_run_timeout_seconds=0.0,
    )

    summary = await run_benchmark(
        CASE,
        model_ids=["qwen35-4b", "unsafe"],
        repetitions=1,
        output_root=tmp_path,
        adapter_factory=factory,
        run_id="deadline-run",
        profile=profile,
    )

    assert order == []
    assert summary.completion_state == "incomplete_deadline"
    progress = json.loads((tmp_path / "deadline-run" / "progress.json").read_text(encoding="utf-8"))
    assert progress["completion_state"] == "incomplete_deadline"
    assert progress["models"]["qwen35-4b"]["execution_status"] == "not_started"
    assert progress["models"]["unsafe"]["execution_status"] == "not_started"


@pytest.mark.asyncio
async def test_interrupted_run_flushes_current_attempt_and_incomplete_outputs(
    tmp_path: Path,
) -> None:
    order: list[tuple[str, int]] = []

    class InterruptedClient(FakeClient):
        async def complete_json(self, system: str, user: str, max_tokens: int = 4096) -> dict:
            raise asyncio.CancelledError()

    def factory(spec: ModelSpec, seed: int) -> FakeClient:
        return InterruptedClient(spec, seed, order)

    summary = await run_benchmark(
        CASE,
        model_ids=["qwen35-4b", "unsafe"],
        repetitions=1,
        output_root=tmp_path,
        adapter_factory=factory,
        run_id="interrupted-run",
        profile=BenchmarkProfile(name="acceptance-smoke"),
    )

    assert summary.completion_state == "incomplete_interrupted"
    assert summary.models[0].interrupted == 1
    assert summary.models[1].attempted == 0
    assert order == [("qwen35-4b", 11)]
    result_path = tmp_path / "interrupted-run" / "models" / "qwen35-4b" / "repetition-001.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "interrupted"
    assert result["execution_status"] == "interrupted"
    progress = json.loads((tmp_path / "interrupted-run" / "progress.json").read_text(encoding="utf-8"))
    assert progress["completion_state"] == "incomplete_interrupted"
    assert progress["models"]["unsafe"]["execution_status"] == "not_started"

    resumed = await run_benchmark(
        CASE,
        model_ids=["qwen35-4b", "unsafe"],
        repetitions=1,
        output_root=tmp_path,
        adapter_factory=lambda spec, seed: FakeClient(spec, seed, order),
        resume_run_id="interrupted-run",
        retry_timeouts=True,
        profile=BenchmarkProfile(name="acceptance-smoke"),
    )

    assert resumed.completion_state == "completed"
    assert order == [
        ("qwen35-4b", 11),
        ("qwen35-4b", 11),
        ("unsafe", 11),
    ]
