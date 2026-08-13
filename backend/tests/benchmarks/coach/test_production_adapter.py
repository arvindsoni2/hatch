from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.schemas.coach import QuestionPresentation, SessionRubric, TechnicalDrill
from app.services.coach_contracts import CoachDiagnostic
from app.services.question_generator import (
    QuestionGenerationResult,
    QuestionGeneratorService,
)
from app.services.rubric_synthesiser import RubricSynthesiserService
from app.services.technical_drills import TechnicalDrillsResult, TechnicalDrillsService
from benchmarks.coach.production_adapter import (
    CoachProductionAdapter,
    ScenarioContext,
)
from benchmarks.coach.suite_loader import load_suite

ROOT = Path(__file__).resolve().parents[4]
V1_SUITE = ROOT / "backend" / "benchmarks" / "coach" / "fixtures" / "v1"


class FakeLiveClient:
    model = "fake-live-model"
    last_json_attempt_count = 1
    observations: list[object] = []


class StaticJSONClient(FakeLiveClient):
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response

    async def complete_json(self, *args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        return self.response


class CapturingJSONClient(StaticJSONClient):
    def __init__(self, response: dict[str, object]) -> None:
        super().__init__(response)
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    async def complete_json(
        self, system: str, user: str, **kwargs: object
    ) -> dict[str, object]:
        self.calls.append((system, user, kwargs))
        return self.response


def _diagnostic(*, execution_mode: str = "llm") -> CoachDiagnostic:
    return CoachDiagnostic(
        stage="question_generation",
        outcome="completed",
        execution_mode=execution_mode,
        prompt_id="question_generation" if execution_mode == "llm" else None,
        prompt_version="2.0.0" if execution_mode == "llm" else None,
        output_schema_version="1.0.0" if execution_mode == "llm" else None,
        model_id="fake-live-model" if execution_mode == "llm" else None,
        attempt_count=1 if execution_mode == "llm" else 0,
        repair_count=0,
        gate_codes=[],
        duration_ms=1,
    )


@pytest.mark.asyncio
async def test_follow_up_benchmark_renders_the_production_prompt() -> None:
    suite = load_suite(
        ROOT / "backend" / "benchmarks" / "coach" / "fixtures" / "conversational_v1"
    )
    scenario = suite.scenario("follow_up_admitted")
    transcript = str(scenario.input["transcript"])
    client = CapturingJSONClient(
        {
            "should_ask": True,
            "reason": "measurable_result",
            "question": "What measurable result followed your action?",
            "transcript_evidence": {
                "start": 0,
                "end": len(transcript),
                "excerpt": transcript,
            },
            "target_dimension": "impact",
            "aggregation_role": "gap_repair",
            "duplicate_key": "measurable-result",
        }
    )

    result = await CoachProductionAdapter().execute(
        scenario, client, ScenarioContext.from_suite(suite)
    )

    assert result.output["admitted"] is True
    system, user, kwargs = client.calls[0]
    assert "adaptive interview follow-up" in system
    assert transcript in user
    assert str(len(transcript)) in user
    assert '"transcript_evidence"' in user
    assert kwargs["max_tokens"] > 0


@pytest.mark.asyncio
async def test_question_generation_uses_production_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question = QuestionPresentation(
        id="q_1",
        text="How would you manage a dependency risk?",
        category="Technical",
        difficulty="medium",
        requirement_id="REQ-01",
        num=1,
        total=1,
    )
    initial = _diagnostic()
    final = _diagnostic(execution_mode="deterministic")
    called = AsyncMock(
        return_value=QuestionGenerationResult([question], initial, None, final)
    )
    monkeypatch.setattr(QuestionGeneratorService, "generate", called)
    suite = load_suite(V1_SUITE)

    result = await CoachProductionAdapter().execute(
        suite.scenario("qg_01_requirement_coverage"),
        FakeLiveClient(),
        ScenarioContext.from_suite(suite),
    )

    assert result.diagnostic.stage == "question_generation"
    assert result.output["questions"][0]["requirement_id"] == "REQ-01"
    assert result.provider_attempt_count == 1
    called.assert_awaited_once()


@pytest.mark.asyncio
async def test_model_answer_with_no_selected_evidence_uses_production_withholding() -> None:
    suite = load_suite(V1_SUITE)

    result = await CoachProductionAdapter().execute(
        suite.scenario("ma_02_insufficient_evidence"),
        FakeLiveClient(),
        ScenarioContext.from_suite(suite),
    )

    assert result.output["model_answer"] == ""
    assert result.diagnostic.outcome == "withheld_insufficient_evidence"
    assert result.diagnostic.execution_mode == "not_run"


@pytest.mark.asyncio
async def test_supported_model_answer_uses_atomic_fixture_evidence() -> None:
    suite = load_suite(V1_SUITE)
    scenario = suite.scenario("ma_01_supported_star")
    evidence = ScenarioContext.from_suite(suite).evidence_items(
        scenario.input["evidence_ids"]
    )
    by_part = {item["star_part"]: item for item in evidence}
    star = {part: by_part[part]["text"] for part in ("situation", "task", "action", "result")}
    client = StaticJSONClient(
        {
            "model_answer": ". ".join(star.values()) + ".",
            "star_breakdown": star,
            "evidence_references": [item["evidence_id"] for item in evidence],
        }
    )

    result = await CoachProductionAdapter().execute(
        scenario, client, ScenarioContext.from_suite(suite)
    )

    assert result.diagnostic.outcome == "completed"
    assert set(result.output["evidence_references"]) == set(scenario.input["evidence_ids"])


@pytest.mark.asyncio
async def test_company_research_uses_fixed_bundle_without_live_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suite = load_suite(V1_SUITE)
    client = FakeLiveClient()

    async def complete_json(*args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        return {
            "description": {
                "text": "Atlas Example Cloud builds workflow software.",
                "source_ids": ["SRC-OFFICIAL-01"],
            },
            "sector": {
                "text": "workflow software",
                "source_ids": ["SRC-OFFICIAL-01"],
            },
            "website": None,
            "recent_news": [],
            "key_products": [],
            "tech_stack_signals": [],
        }

    monkeypatch.setattr(client, "complete_json", complete_json, raising=False)
    result = await CoachProductionAdapter().execute(
        suite.scenario("cr_01_grounded_synthesis"),
        client,
        ScenarioContext.from_suite(suite),
    )

    assert result.output["verification_state"] == "verified"
    assert {item["source_id"] for item in result.output["sources"]} == {
        "SRC-OFFICIAL-01",
        "SRC-OFFICIAL-02",
        "SRC-NEWS-01",
    }


@pytest.mark.asyncio
async def test_rubric_synthesis_dispatches_to_production_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostic = CoachDiagnostic(
        stage="rubric_synthesis",
        outcome="completed",
        execution_mode="llm",
        prompt_id="rubric_synthesis",
        prompt_version="1.0.0",
        output_schema_version="1.0.0",
        model_id="fake-live-model",
        attempt_count=1,
        repair_count=0,
        gate_codes=[],
        duration_ms=1,
    )
    called = AsyncMock(return_value=SessionRubric(diagnostic=diagnostic))
    monkeypatch.setattr(RubricSynthesiserService, "synthesise", called)
    suite = load_suite(V1_SUITE)

    result = await CoachProductionAdapter().execute(
        suite.scenario("rb_01_score_immutability"),
        FakeLiveClient(),
        ScenarioContext.from_suite(suite),
    )

    assert result.diagnostic.stage == "rubric_synthesis"
    called.assert_awaited_once()


@pytest.mark.asyncio
async def test_technical_drill_dispatches_with_transient_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostic = CoachDiagnostic(
        stage="technical_drill",
        outcome="completed",
        execution_mode="llm",
        prompt_id="technical_drill",
        prompt_version="1.0.0",
        output_schema_version="1.0.0",
        model_id="fake-live-model",
        attempt_count=1,
        repair_count=0,
        gate_codes=[],
        duration_ms=1,
    )
    drill = TechnicalDrill(
        question_id="Q-SYNTH-TECH-01",
        question_text="How would you manage API migration rollback risk?",
        walkthrough="Start with rollback criteria and verification checks.",
        drill_prompt="Explain the rollback decision aloud.",
        category="Technical",
    )
    called = AsyncMock(
        return_value=TechnicalDrillsResult([drill], [], diagnostic)
    )
    monkeypatch.setattr(TechnicalDrillsService, "build_drills", called)
    suite = load_suite(V1_SUITE)

    result = await CoachProductionAdapter().execute(
        suite.scenario("td_01_technical_drill"),
        FakeLiveClient(),
        ScenarioContext.from_suite(suite),
    )

    assert result.output["drills"][0]["question_id"] == "Q-SYNTH-TECH-01"
    question = called.await_args.args[0][0]
    assert question.session_id == "SESSION-SYNTH-DRILL"
