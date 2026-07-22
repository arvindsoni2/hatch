"""Benchmark-only adapters that exercise the production Coach service contracts."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, Literal
from unittest.mock import patch

from pydantic import BaseModel

from app.models.coach_session import SessionQuestion
from app.schemas.coach import (
    AnswerEvaluation,
    CompanyResearchResponse,
    ResearchSource,
    SessionConfig,
    SessionFeedbackReport,
    SpeechMetrics,
)
from app.services.answer_evaluator import AnswerEvaluatorService
from app.services.coach_contracts import CoachDiagnostic
from app.services.company_researcher import (
    CompanyResearchService,
    ResearchBundle,
)
from app.services.feedback_generator import FeedbackGeneratorService
from app.services.model_answer_gen import ModelAnswerGeneratorService
from app.services.question_generator import (
    QuestionGenerationContractError,
    QuestionGeneratorService,
)
from app.services.rubric_synthesiser import RubricSynthesiserService
from app.services.technical_drills import TechnicalDrillsService
from benchmarks.adapters import BenchmarkModelUnavailableError

from .contracts import CoachScenario
from .suite_loader import LoadedCoachSuite

HarnessFailureMode = Literal[
    "provider_unavailable", "timeout", "malformed_output", "parser_exhaustion"
]


@dataclass(frozen=True)
class StageExecution:
    """A normalized production result and its privacy-safe execution metadata."""

    output: dict[str, Any]
    diagnostic: CoachDiagnostic
    provider_attempt_count: int
    repair_count: int
    diagnostics: tuple[CoachDiagnostic, ...] = ()
    observations: tuple[dict[str, Any], ...] = ()

    @property
    def gate_codes(self) -> list[str]:
        return list(
            dict.fromkeys(
                gate
                for diagnostic in (self.diagnostics or (self.diagnostic,))
                for gate in diagnostic.gate_codes
            )
        )

    @property
    def prompt_metadata(self) -> dict[str, str]:
        for diagnostic in self.diagnostics or (self.diagnostic,):
            if diagnostic.prompt_id:
                return {
                    "prompt_id": diagnostic.prompt_id,
                    "prompt_version": diagnostic.prompt_version or "",
                    "output_schema_version": diagnostic.output_schema_version or "",
                    "model_id": diagnostic.model_id or "",
                }
        return {}


@dataclass(frozen=True)
class ScenarioContext:
    """Synthetic fixture context supplied at production loader/retrieval boundaries."""

    candidate_evidence: dict[str, Any]
    job_description: str
    company_research: dict[str, Any]
    company_research_sources: dict[str, Any]

    @classmethod
    def from_suite(cls, suite: LoadedCoachSuite) -> "ScenarioContext":
        return cls(
            candidate_evidence=suite.candidate_evidence,
            job_description=suite.job_description,
            company_research=suite.company_research,
            company_research_sources=suite.company_research_sources,
        )

    def evidence_items(self, evidence_ids: list[str] | None = None) -> list[dict[str, Any]]:
        items = list(self.candidate_evidence["evidence"])
        if evidence_ids is None:
            return items
        selected = set(evidence_ids)
        return [item for item in items if item["evidence_id"] in selected]

    def candidate_summary(self, evidence_ids: list[str] | None = None) -> str:
        return "\n".join(item["text"] for item in self.evidence_items(evidence_ids))

    def question_candidate_summary(self) -> str:
        name = str(self.candidate_evidence.get("candidate_name") or "Candidate")
        return f"{name}\n\n{self.candidate_summary()}"

    def research_bundle(self) -> ResearchBundle:
        raw = self.company_research_sources
        retrieved_at = datetime.fromisoformat(
            str(raw["retrieved_at"]).replace("Z", "+00:00")
        )
        if retrieved_at.tzinfo is None:
            retrieved_at = retrieved_at.replace(tzinfo=UTC)
        sources = tuple(
            ResearchSource(
                source_id=item["source_id"],
                title=f"Synthetic {item['source_id']}",
                url=f"https://example.test/{str(item['source_id']).casefold()}",
                retrieved_at=retrieved_at,
            )
            for item in raw["sources"]
        )
        text = "\n\n".join(
            f"[{item['source_id']}]\n{item['text']}" for item in raw["sources"]
        )
        return ResearchBundle(text=text, sources=sources, retrieved_at=retrieved_at)

    def company_response(self) -> CompanyResearchResponse:
        source_ids = set(self.company_research.get("source_ids", []))
        bundle = self.research_bundle()
        return CompanyResearchResponse(
            **{
                key: value
                for key, value in self.company_research.items()
                if key not in {"source_ids", "sources"}
            },
            sources=[item for item in bundle.sources if item.source_id in source_ids],
        )


class HarnessFailureClient:
    """Deterministic service-compatible client for harness-contract scenarios."""

    _MODES = {
        "provider_unavailable",
        "timeout",
        "malformed_output",
        "parser_exhaustion",
    }

    def __init__(self, mode: HarnessFailureMode) -> None:
        if mode not in self._MODES:
            raise ValueError(f"unsupported harness failure mode: {mode}")
        self.mode = mode
        self.model = f"harness-{mode}"
        self.last_json_attempt_count = 1
        self.observations: list[dict[str, Any]] = []

    async def complete_json(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        schema: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        del system, user, max_tokens, schema
        if self.mode == "provider_unavailable":
            self.observations.append({"attempt": 1, "error": "model_unavailable"})
            raise BenchmarkModelUnavailableError("manufactured provider unavailability")
        if self.mode == "timeout":
            self.observations.append({"attempt": 1, "error": "timeout"})
            raise TimeoutError("manufactured provider timeout")
        self.last_json_attempt_count = 3
        self.observations.extend(
            {"attempt": attempt, "error": "malformed_json"}
            for attempt in range(1, 4)
        )
        return {}


class _ServiceClient:
    """Expose benchmark model identity and per-call attempt counts to services."""

    def __init__(self, delegate: object) -> None:
        self._delegate = delegate
        spec = getattr(delegate, "spec", None)
        self.model = str(getattr(spec, "id", None) or getattr(delegate, "model", "configured"))
        self.last_json_attempt_count = 1

    @property
    def observations(self) -> list[Any]:
        value = getattr(self._delegate, "observations", [])
        return value if isinstance(value, list) else []

    async def complete_json(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        schema: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        before = len(self.observations)
        try:
            return await self._delegate.complete_json(
                system, user, max_tokens=max_tokens, schema=schema
            )
        finally:
            exposed = getattr(self._delegate, "last_json_attempt_count", None)
            delta = len(self.observations) - before
            self.last_json_attempt_count = (
                exposed if isinstance(exposed, int) and exposed >= 1 else max(1, delta)
            )


class _FixedResearchService(CompanyResearchService):
    def __init__(self, client: object, bundle: ResearchBundle) -> None:
        super().__init__(client)  # type: ignore[arg-type]
        self._bundle = bundle

    async def _scrape_company_info(self, company_name: str) -> ResearchBundle:
        del company_name
        return self._bundle


class _LangChainClient:
    """Minimal LangChain-compatible view over the benchmark JSON client."""

    def __init__(self, client: _ServiceClient) -> None:
        self._client = client
        self.model = client.model

    async def ainvoke(self, messages: list[object]) -> SimpleNamespace:
        contents = [str(getattr(item, "content", "")) for item in messages]
        system = contents[0] if contents else ""
        user = "\n\n".join(contents[1:])
        raw = await self._client.complete_json(system, user)
        return SimpleNamespace(content=json.dumps(raw))


def _dump_observations(client: _ServiceClient) -> tuple[dict[str, Any], ...]:
    values: list[dict[str, Any]] = []
    for item in client.observations:
        if isinstance(item, BaseModel):
            values.append(item.model_dump(mode="json"))
        elif isinstance(item, dict):
            values.append(dict(item))
    return tuple(values)


def _execution(
    output: dict[str, Any],
    diagnostic: CoachDiagnostic,
    client: _ServiceClient,
    *,
    diagnostics: tuple[CoachDiagnostic, ...] = (),
) -> StageExecution:
    all_diagnostics = diagnostics or (diagnostic,)
    return StageExecution(
        output=output,
        diagnostic=diagnostic,
        provider_attempt_count=sum(
            item.attempt_count for item in all_diagnostics if item.execution_mode == "llm"
        ),
        repair_count=sum(item.repair_count for item in all_diagnostics),
        diagnostics=all_diagnostics,
        observations=_dump_observations(client),
    )


class CoachProductionAdapter:
    """Dispatch benchmark scenarios through production Coach service methods."""

    async def execute(
        self,
        scenario: CoachScenario,
        client: object,
        context: ScenarioContext,
    ) -> StageExecution:
        if scenario.forced_failure and not isinstance(client, HarnessFailureClient):
            raise ValueError("forced-failure scenarios require HarnessFailureClient")
        if (
            scenario.forced_failure
            and isinstance(client, HarnessFailureClient)
            and client.mode != scenario.forced_failure
        ):
            raise ValueError("harness failure mode does not match scenario")
        handler = getattr(self, f"_execute_{scenario.stage}", None)
        if handler is None:
            raise ValueError(f"unsupported production-adapter stage: {scenario.stage}")
        return await handler(scenario, _ServiceClient(client), context)

    async def _execute_company_research(
        self, scenario: CoachScenario, client: _ServiceClient, context: ScenarioContext
    ) -> StageExecution:
        service = _FixedResearchService(client, context.research_bundle())
        output = await service.research(
            str(scenario.input["company_name"]), scenario.input.get("sector")
        )
        if service.last_diagnostic is None:
            raise RuntimeError("production company research omitted its diagnostic")
        return _execution(
            output.model_dump(mode="json"), service.last_diagnostic, client
        )

    async def _execute_question_generation(
        self, scenario: CoachScenario, client: _ServiceClient, context: ScenarioContext
    ) -> StageExecution:
        service = QuestionGeneratorService(client)  # type: ignore[arg-type]
        config = SessionConfig(
            question_count=scenario.input["question_count"],
            difficulty=scenario.input["difficulty"],
        )
        try:
            with patch(
                "app.services.question_generator._load_candidate_summary",
                return_value=context.question_candidate_summary(),
            ):
                result = await service.generate(
                    config,
                    str(scenario.input["company_name"]),
                    str(scenario.input["role_title"]),
                    company_research=context.company_response(),
                    jd_text=context.job_description,
                )
        except QuestionGenerationContractError as exc:
            result = exc.result
        diagnostics = tuple(
            item
            for item in (
                result.initial_diagnostic,
                result.repair_diagnostic,
                result.final_diagnostic,
            )
            if item is not None
        )
        return _execution(
            {"questions": [item.model_dump(mode="json") for item in result.questions]},
            result.final_diagnostic,
            client,
            diagnostics=diagnostics,
        )

    async def _execute_model_answer(
        self, scenario: CoachScenario, client: _ServiceClient, context: ScenarioContext
    ) -> StageExecution:
        evidence_ids = list(scenario.input.get("evidence_ids", []))
        service = ModelAnswerGeneratorService(client)  # type: ignore[arg-type]
        result = await service.generate(
            question=str(scenario.input["question"]),
            category=str(scenario.input["category"]),
            difficulty=str(scenario.input["difficulty"]),
            company_name=str(scenario.input["company_name"]),
            company_research=context.company_research,
            candidate_summary=context.candidate_summary(evidence_ids),
        )
        return _execution(result.model_dump(mode="json"), result.diagnostic, client)

    async def _execute_answer_evaluation(
        self, scenario: CoachScenario, client: _ServiceClient, context: ScenarioContext
    ) -> StageExecution:
        raw_metrics = scenario.input.get("speech_metrics")
        speech_metrics = SpeechMetrics.model_validate(raw_metrics) if raw_metrics else None
        references = list(scenario.input.get("model_answer_evidence_ids", []))
        model_answer = " ".join(
            item["text"] for item in context.evidence_items(references)
        ) or None
        service = AnswerEvaluatorService(client)  # type: ignore[arg-type]
        result = await service.evaluate(
            question=str(scenario.input["question"]),
            category=str(scenario.input["category"]),
            transcript=str(scenario.input["transcript"]),
            speech_metrics=speech_metrics,
            model_answer=model_answer,
        )
        if result.diagnostic is None:
            raise RuntimeError("production answer evaluation omitted its diagnostic")
        return _execution(result.model_dump(mode="json"), result.diagnostic, client)

    async def _execute_rubric_synthesis(
        self, scenario: CoachScenario, client: _ServiceClient, context: ScenarioContext
    ) -> StageExecution:
        del context
        scores = scenario.input["baseline_scores"]
        production_scores = {
            "relevance": int(scores.get("relevance", scores.get("content", 0))),
            "star_structure": int(scores.get("star_structure", scores.get("structure", 0))),
            "technical_depth": int(scores.get("technical_depth", scores.get("content", 0))),
            "conciseness": int(scores.get("conciseness", scores.get("structure", 0))),
            "communication": int(scores.get("communication", scores.get("delivery", 0))),
            "impact_metrics": int(scores.get("impact_metrics", scores.get("specificity", 0))),
        }
        evaluation = AnswerEvaluation(
            scores=production_scores,
            overall=sum(production_scores.values()) / len(production_scores),
        )
        service = RubricSynthesiserService()
        service._llm = _LangChainClient(client)
        result = await service.synthesise(
            transcript=str(scenario.input["transcript"]), evaluation=evaluation
        )
        if result.diagnostic is None:
            raise RuntimeError("production rubric synthesis omitted its diagnostic")
        return _execution(result.model_dump(mode="json"), result.diagnostic, client)

    async def _execute_session_report(
        self, scenario: CoachScenario, client: _ServiceClient, context: ScenarioContext
    ) -> StageExecution:
        del context
        authoritative = SessionFeedbackReport.model_validate(
            {
                "session_id": scenario.input["session_id"],
                **scenario.input["authoritative_report"],
            }
        )
        service = FeedbackGeneratorService(client)  # type: ignore[arg-type]
        with patch(
            "app.services.feedback_generator._load_candidate_name",
            return_value="Candidate",
        ):
            result = await service.generate_report(
                session_id=str(scenario.input["session_id"]),
                role_title=str(scenario.input["role_title"]),
                company_name=str(scenario.input["company_name"]),
                question_evaluations=[],
                deterministic_report=authoritative,
            )
        if result.diagnostic is None:
            raise RuntimeError("production session report omitted its diagnostic")
        return _execution(result.model_dump(mode="json"), result.diagnostic, client)

    async def _execute_technical_drill(
        self, scenario: CoachScenario, client: _ServiceClient, context: ScenarioContext
    ) -> StageExecution:
        del context
        question = SessionQuestion(
            id=str(scenario.input["question_id"]),
            session_id="SESSION-SYNTH-DRILL",
            question_num=1,
            text=str(scenario.input["question"]),
            category=str(scenario.input["category"]),
            difficulty="medium",
            requirement_id=str(scenario.input["requirement_id"]),
            order_in_session=1,
        )
        service = TechnicalDrillsService(client)  # type: ignore[arg-type]
        with patch(
            "app.services.technical_drills._load_candidate_names", return_value=()
        ):
            result = await service.build_drills([question])
        return _execution(
            {
                "drills": [item.model_dump(mode="json") for item in result],
                "item_diagnostics": result.items_diagnostics,
            },
            result.summary_diagnostic,
            client,
        )
