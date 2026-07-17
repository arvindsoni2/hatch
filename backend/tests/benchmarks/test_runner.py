from __future__ import annotations

import json
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
from benchmarks.adapters import BenchmarkModelUnavailableError, GenerationObservation
from benchmarks.contracts import BenchmarkCase, ExpectedFacts, ModelSpec, RoleFact
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


@pytest.mark.asyncio
async def test_runner_ranks_gate_pass_rate_before_quality(tmp_path: Path) -> None:
    order: list[tuple[str, int]] = []

    def factory(spec: ModelSpec, seed: int) -> FakeClient:
        return FakeClient(spec, seed, order)

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
    raw_payloads = json.loads(raw.read_text(encoding="utf-8"))
    assert json.loads(raw_payloads[0])["summary"].startswith(
        "Delivery Manager"
    )


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
