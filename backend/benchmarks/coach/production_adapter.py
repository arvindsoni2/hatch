"""Benchmark-only adapters that exercise the production Coach service contracts."""

from __future__ import annotations

import json
import hashlib
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
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
    SessionRubric,
    SpeechMetrics,
)
from app.services.answer_evaluator import AnswerEvaluatorService
from app.services.coach_attempt_pipeline import SessionEvidenceSnapshot
from app.services.coach_coaching import (
    CoachCoachingService,
    build_coaching_skeleton,
)
from app.services.coach_conversational_evaluator import (
    ConversationalEvaluator,
    EvaluationRequest,
)
from app.services.coach_evidence_grounder import EvidenceGrounder, GroundingRequest
from app.services.coach_followup_policy import FollowUpContext, FollowUpPolicy
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
from app.services.rubric_builder import score_to_band
from app.services.technical_drills import TechnicalDrillsService
from benchmarks.adapters import BenchmarkModelUnavailableError

from .contracts import CoachScenario
from .suite_loader import LoadedCoachSuite

HarnessFailureMode = Literal[
    "provider_unavailable", "timeout", "malformed_output", "parser_exhaustion"
]


def _synthetic_follow_up_proposal(scenario: CoachScenario) -> dict[str, Any]:
    transcript = str(scenario.input["transcript"])
    return {
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

    def evidence_items(
        self, evidence_ids: list[str] | None = None
    ) -> list[dict[str, Any]]:
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
            {"attempt": attempt, "error": "malformed_json"} for attempt in range(1, 4)
        )
        return {}


class DeterministicCoachClient:
    """Scenario-aware fake model used only by the bounded contract-smoke profile."""

    def __init__(
        self,
        scenario: CoachScenario,
        context: ScenarioContext,
        model_id: str,
    ) -> None:
        self.scenario = scenario
        self.context = context
        self.model = model_id
        self.spec = SimpleNamespace(id=model_id)
        self.last_json_attempt_count = 1
        self.observations: list[dict[str, Any]] = []
        self._call_index = 0

    async def complete_json(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        schema: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        del system, user, max_tokens, schema
        self._call_index += 1
        self.observations.append({"attempt": 1, "outcome": "completed"})
        handler = getattr(self, f"_response_{self.scenario.stage}", None)
        if handler is None:
            raise ValueError(
                f"no deterministic response for stage {self.scenario.stage}"
            )
        return handler()

    def _dimension_proposal(self, level: str) -> dict[str, Any]:
        transcript = str(self.scenario.input["transcript"])
        evidence = (
            []
            if level == "not_assessed"
            else [
                {
                    "transcript_start": 0,
                    "transcript_end": len(transcript),
                    "excerpt": transcript,
                }
            ]
        )
        return {
            "level": level,
            "evidence": evidence,
            "rationale": None
            if level == "not_assessed"
            else "The transcript supports this named level.",
            "improvement": "Add one more concrete detail.",
        }

    def _response_conversational_rubric(self) -> dict[str, Any]:
        case = str(self.scenario.input["case"])
        if case == "technical_failure":
            raise RuntimeError("synthetic provider failure")
        level = "strong" if case == "strong" else "not_assessed"
        dimensions = {
            name: self._dimension_proposal(level)
            for name in (
                "relevance",
                "structure",
                "specificity",
                "impact",
                "role_depth",
                "clarity",
                "conciseness",
            )
        }
        if case == "prohibited":
            dimensions["clarity"]["rationale"] = "The candidate seems anxious."
            dimensions["clarity"]["level"] = "developing"
            dimensions["clarity"]["evidence"] = [
                {
                    "transcript_start": 0,
                    "transcript_end": len(str(self.scenario.input["transcript"])),
                    "excerpt": str(self.scenario.input["transcript"]),
                }
            ]
        elif case == "span_invalid":
            dimensions["clarity"]["level"] = "developing"
            dimensions["clarity"]["evidence"] = [
                {
                    "transcript_start": 0,
                    "transcript_end": 3,
                    "excerpt": "not the transcript span",
                }
            ]
        return {"dimensions": dimensions}

    def _grounding_claim(self) -> dict[str, Any]:
        transcript = str(self.scenario.input["transcript"])
        evidence = self.context.evidence_items(
            list(self.scenario.input.get("evidence_ids", []))
        )
        case = str(self.scenario.input["case"])
        references = []
        if case == "invalid_id":
            references = [
                {
                    "evidence_id": "unknown-synthetic-evidence",
                    "snapshot_hash": "sha256:" + "9" * 64,
                }
            ]
        elif case != "not_found" and evidence:
            references = [
                {
                    "evidence_id": evidence[0]["evidence_id"],
                    "snapshot_hash": evidence[0]["snapshot_hash"],
                }
            ]
        status = {
            "supported": "supported",
            "partial": "partially_supported",
            "conflict": "conflicting",
            "not_found": "not_found",
        }.get(case, "supported")
        return {
            "claim_id": "claim-synthetic-01",
            "claim_text": transcript,
            "transcript_start": 0,
            "transcript_end": len(transcript),
            "claim_type": "outcome",
            "materiality": "material",
            "centrality": "central",
            "deduplication_key": "sha256:"
            + hashlib.sha256(transcript.encode()).hexdigest(),
            "status": status,
            "evidence_references": references,
            "explanation": "The immutable synthetic evidence was checked.",
            "candidate_action": "Review this detail before reuse.",
        }

    def _response_evidence_grounding(self) -> dict[str, Any]:
        return {"claims": [self._grounding_claim()]}

    def _follow_up_proposal(self) -> dict[str, Any]:
        return _synthetic_follow_up_proposal(self.scenario)

    def _response_follow_up(self) -> dict[str, Any]:
        return self._follow_up_proposal()

    def _response_coaching(self) -> dict[str, Any]:
        invented = str(self.scenario.input["case"]) == "invented_fact"
        return {
            "positive_observation": "Your answer contains a usable example.",
            "priority_improvement": "Add one more concrete action or outcome.",
            "suggested_structure": "State the situation, action, and result.",
            "practice_instruction": "Practise once using only your evidence.",
            "example_revision": (
                "Project Apollo improved delivery by 42%."
                if invented
                else "I improved delivery by [add verified metric]."
            ),
        }

    def _response_prohibited_inference(self) -> dict[str, Any]:
        return self._response_conversational_rubric()

    def _response_conversational_end_to_end(self) -> dict[str, Any]:
        if self._call_index == 1:
            return {
                "dimensions": {
                    name: self._dimension_proposal("strong")
                    for name in (
                        "relevance",
                        "structure",
                        "specificity",
                        "impact",
                        "role_depth",
                        "clarity",
                        "conciseness",
                    )
                }
            }
        return {"claims": [self._grounding_claim()]}

    def _response_company_research(self) -> dict[str, Any]:
        sources = self.scenario.scoring.expected_source_ids or list(
            self.scenario.scoring.allowed_source_ids
        )
        source_id = sources[0] if sources else "SRC-OFFICIAL-01"
        return {
            "description": {
                "text": "Atlas Example Cloud provides workflow software for regulated service teams.",
                "source_ids": [source_id],
            },
            "sector": {"text": "workflow software", "source_ids": [source_id]},
            "website": None,
            "recent_news": [],
            "key_products": [{"text": "Atlas Flow", "source_ids": [source_id]}],
            "tech_stack_signals": [
                {"text": "event-driven integration", "source_ids": [source_id]}
            ],
        }

    def _response_question_generation(self) -> dict[str, Any]:
        count = int(self.scenario.input["question_count"])
        requirements = list(self.scenario.scoring.required_requirement_ids)
        if not requirements:
            requirements = list(self.scenario.scoring.accepted_requirement_ids)
        requirements = requirements or [
            f"REQ-{index:02d}" for index in range(1, count + 1)
        ]
        categories: list[str] = []
        for (
            category,
            category_count,
        ) in self.scenario.scoring.expected_category_counts.items():
            categories.extend([category] * category_count)
        fallback = ["Technical", "Behavioural", "Situational", "Commercial"]
        while len(categories) < count:
            categories.append(fallback[len(categories) % len(fallback)])
        return {
            "questions": [
                {
                    "text": (
                        f"How would you manage delivery risk and technical trade-offs "
                        f"for service metrics in scenario {index + 1}?"
                    ),
                    "category": categories[index],
                    "difficulty": self.scenario.input["difficulty"],
                    "requirement_id": requirements[index % len(requirements)],
                    "model_answer": None,
                }
                for index in range(count)
            ]
        }

    def _response_model_answer(self) -> dict[str, Any]:
        evidence = self.context.evidence_items(
            list(self.scenario.input.get("evidence_ids", []))
        )
        if not evidence:
            return {
                "model_answer": "",
                "star_breakdown": {
                    "situation": "",
                    "task": "",
                    "action": "",
                    "result": "",
                },
                "evidence_references": [],
            }
        by_part = {item.get("star_part"): item for item in evidence}
        star = {
            part: str(by_part[part]["text"])
            for part in ("situation", "task", "action", "result")
        }
        return {
            "model_answer": ". ".join(star.values()) + ".",
            "star_breakdown": star,
            "evidence_references": [item["evidence_id"] for item in evidence],
        }

    def _response_answer_evaluation(self) -> dict[str, Any]:
        dimensions = (
            "relevance",
            "star_structure",
            "technical_depth",
            "conciseness",
            "communication",
            "impact_metrics",
        )
        scores = {
            name: int(sum(self.scenario.expected.score_ranges[name]) // 2)
            for name in dimensions
        }
        overall = round(sum(scores.values()) / len(scores), 1)
        transcript = str(self.scenario.input["transcript"])
        evidence = [transcript.rstrip(".")]
        return {
            "scores": scores,
            "overall": overall,
            "feedback": "The answer was assessed against structure, specificity, and impact.",
            "evidence_references": evidence,
            "follow_up_question": (
                "What specific action did you take and what result followed?"
                if self.scenario.expected.follow_up_required
                else None
            ),
        }

    def _response_rubric_synthesis(self) -> dict[str, Any]:
        transcript = str(self.scenario.input["transcript"])
        evidence = transcript.rstrip(".")
        dimensions = {}
        for name, score in self.scenario.input["baseline_scores"].items():
            dimensions[name] = {
                "score": score,
                "score_band": score_to_band(score),
                "evidence": [evidence],
                "drill": f"Practise a concise {name.replace('_', ' ')} example.",
            }
        focus = " and ".join(self.scenario.input["focus_dimensions"])
        return {
            "dimensions": dimensions,
            "focus_for_next_session": f"Focus next session on {focus}.",
        }

    def _response_session_report(self) -> dict[str, Any]:
        improvements = list(
            self.scenario.input.get("authoritative_report", {}).get(
                "improvement_areas",
                self.scenario.expected.expected_priority_dimensions,
            )
        )
        return {
            "executive_summary": (
                "Delivery evidence is structured; practise specific technical impact next."
            ),
            "strengths": ["Clear delivery structure"],
            "improvement_areas": improvements,
            "coaching_points": [
                "Rehearse a technical example with a measurable result."
            ],
            "practice_plan": [
                {
                    "day": 1,
                    "focus": "technical delivery",
                    "activity": "Record one bounded practice answer",
                    "resource": None,
                }
            ],
        }

    def _response_technical_drill(self) -> dict[str, Any]:
        return {
            "question_id": self.scenario.input["question_id"],
            "question_text": self.scenario.input["question"],
            "walkthrough": (
                "Define the service objective, compare speed with safety and control, "
                "set rollback or escalation thresholds, then verify leading and lagging "
                "measures across availability and consistency."
            ),
            "drill_prompt": (
                "Explain the API rollback or service-measures decision and its trade-offs."
            ),
        }

    def _response_end_to_end(self) -> dict[str, Any]:
        return self._response_session_report()


class _ServiceClient:
    """Expose benchmark model identity and per-call attempt counts to services."""

    def __init__(self, delegate: object) -> None:
        self._delegate = delegate
        spec = getattr(delegate, "spec", None)
        self.model = str(
            getattr(spec, "id", None) or getattr(delegate, "model", "configured")
        )
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
            item.attempt_count
            for item in all_diagnostics
            if item.execution_mode == "llm"
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

    @staticmethod
    def _conversational_diagnostic(
        client: _ServiceClient,
        *,
        stage: str,
        outcome: str = "completed",
        repair_count: int = 0,
    ) -> CoachDiagnostic:
        mapped = {
            "conversational_rubric": "answer_evaluation",
            "evidence_grounding": "model_answer",
            "follow_up": "question_generation",
            "coaching": "rubric_synthesis",
            "prohibited_inference": "answer_evaluation",
            "conversational_end_to_end": "answer_evaluation",
        }[stage]
        return CoachDiagnostic(
            stage=mapped,
            outcome=outcome,
            execution_mode="llm",
            prompt_id=f"coach_benchmark_{stage}",
            prompt_version="1",
            output_schema_version="1",
            model_id=client.model,
            attempt_count=max(1, client.last_json_attempt_count),
            repair_count=repair_count,
            gate_codes=[],
            duration_ms=0,
        )

    @staticmethod
    def _evidence_package(
        context: ScenarioContext, evidence_ids: list[str]
    ) -> tuple[SessionEvidenceSnapshot, ...]:
        return tuple(
            SessionEvidenceSnapshot(
                evidence_id=str(item["evidence_id"]),
                source_type=str(item.get("source_type", "application_cv")),
                source_record_id=str(item.get("source_record_id", "synthetic-record")),
                source_record_version=str(item.get("source_record_version", "1")),
                source_path=str(item["source_path"]),
                snapshot_text=str(item["text"]),
                approval_state=str(item.get("approval_state", "approved")),
                content_hash=str(item.get("content_hash", "sha256:" + "1" * 64)),
                snapshot_hash=str(item.get("snapshot_hash", "sha256:" + "2" * 64)),
            )
            for item in context.evidence_items(evidence_ids)
        )

    async def _execute_conversational_rubric(
        self, scenario: CoachScenario, client: _ServiceClient, context: ScenarioContext
    ) -> StageExecution:
        del context
        result = await ConversationalEvaluator(client).evaluate(
            EvaluationRequest(
                question=str(scenario.input["question"]),
                normalized_transcript=str(scenario.input["transcript"]),
                recording_type=str(scenario.input.get("recording_type", "text")),
                deadline_at=datetime.utcnow() + timedelta(seconds=30),
            )
        )
        output = {
            "state": result.state,
            "dimensions": {
                name: item.model_dump(mode="json")
                for name, item in result.dimensions.items()
            },
            "answer_level": result.answer_level,
            "delivery": result.delivery.model_dump(mode="json"),
            "repair_count": result.repair_count,
            "error_code": result.error_code,
        }
        diagnostic = self._conversational_diagnostic(
            client,
            stage=scenario.stage,
            outcome="completed" if result.state == "completed" else "unavailable",
            repair_count=result.repair_count,
        )
        return _execution(output, diagnostic, client)

    async def _execute_prohibited_inference(
        self, scenario: CoachScenario, client: _ServiceClient, context: ScenarioContext
    ) -> StageExecution:
        return await self._execute_conversational_rubric(scenario, client, context)

    async def _execute_evidence_grounding(
        self, scenario: CoachScenario, client: _ServiceClient, context: ScenarioContext
    ) -> StageExecution:
        package = self._evidence_package(
            context, list(scenario.input.get("evidence_ids", []))
        )
        result = await EvidenceGrounder(client).ground(
            GroundingRequest(
                normalized_transcript=str(scenario.input["transcript"]),
                evidence_records=package,
                deadline_at=datetime.utcnow() + timedelta(seconds=30),
                draft_evidence_consent=bool(
                    scenario.input.get("draft_evidence_consent", False)
                ),
            )
        )
        output = {
            "state": result.state,
            "claims": [asdict(item) for item in result.claims],
            "level": result.level,
            "repair_count": result.repair_count,
            "error_code": result.error_code,
        }
        diagnostic = self._conversational_diagnostic(
            client,
            stage=scenario.stage,
            outcome="completed" if result.state == "completed" else "unavailable",
            repair_count=result.repair_count,
        )
        return _execution(output, diagnostic, client)

    async def _execute_follow_up(
        self, scenario: CoachScenario, client: _ServiceClient, context: ScenarioContext
    ) -> StageExecution:
        del context
        raw = await client.complete_json("Follow-up policy", "Synthetic proposal")
        decision = FollowUpPolicy().validate(
            raw,
            FollowUpContext(
                transcript=str(scenario.input["transcript"]),
                accepted_attempt_id=str(scenario.input["accepted_attempt_id"]),
                current_accepted_attempt_id=scenario.input.get(
                    "current_accepted_attempt_id"
                ),
                target_dimension_levels=dict(
                    scenario.input.get("target_dimension_levels", {})
                ),
                existing_duplicate_keys=tuple(
                    scenario.input.get("existing_duplicate_keys", [])
                ),
                persisted_follow_up_count=int(
                    scenario.input.get("persisted_follow_up_count", 0)
                ),
                root_skipped=bool(scenario.input.get("root_skipped", False)),
                session_ended=bool(scenario.input.get("session_ended", False)),
            ),
        )
        output = asdict(decision)
        return _execution(
            output,
            self._conversational_diagnostic(client, stage=scenario.stage),
            client,
        )

    async def _execute_coaching(
        self, scenario: CoachScenario, client: _ServiceClient, context: ScenarioContext
    ) -> StageExecution:
        evaluation = dict(scenario.input["evaluation"])
        skeleton = build_coaching_skeleton(evaluation)
        evidence_texts = [
            str(item["text"])
            for item in context.evidence_items(
                list(scenario.input.get("evidence_ids", []))
            )
        ]
        result = await CoachCoachingService(client).enrich(
            skeleton,
            transcript=str(scenario.input["transcript"]),
            evidence_texts=evidence_texts,
            deadline_at=datetime.utcnow() + timedelta(seconds=30),
        )
        output = {**asdict(result), "fallback": result == skeleton}
        return _execution(
            output,
            self._conversational_diagnostic(client, stage=scenario.stage),
            client,
        )

    async def _execute_conversational_end_to_end(
        self, scenario: CoachScenario, client: _ServiceClient, context: ScenarioContext
    ) -> StageExecution:
        rubric = await self._execute_conversational_rubric(scenario, client, context)
        grounding = await self._execute_evidence_grounding(scenario, client, context)
        raw = _synthetic_follow_up_proposal(scenario)
        decision = FollowUpPolicy().validate(
            raw,
            FollowUpContext(
                transcript=str(scenario.input["transcript"]),
                accepted_attempt_id="attempt-e2e",
                current_accepted_attempt_id="attempt-e2e",
                target_dimension_levels={"impact": "developing"},
                existing_duplicate_keys=(),
                persisted_follow_up_count=0,
                root_skipped=False,
                session_ended=False,
            ),
        )
        output = {
            "state": "completed",
            "answer_level": rubric.output["answer_level"],
            "evidence_level": grounding.output["level"],
            "follow_up_admitted": decision.admitted,
        }
        return _execution(
            output,
            self._conversational_diagnostic(client, stage=scenario.stage),
            client,
            diagnostics=(rubric.diagnostic, grounding.diagnostic),
        )

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
        requirement_ids = (
            scenario.scoring.accepted_requirement_ids
            or scenario.scoring.required_requirement_ids
        )
        requirements = [
            {
                "requirement_id": requirement_id,
                "text": f"Synthetic benchmark requirement {requirement_id}",
            }
            for requirement_id in requirement_ids
        ]
        try:
            with (
                patch(
                    "app.services.question_generator._load_candidate_summary",
                    return_value=context.question_candidate_summary(),
                ),
                patch(
                    "app.services.question_generator._build_requirements",
                    return_value=requirements,
                ),
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
        speech_metrics = (
            SpeechMetrics.model_validate(raw_metrics) if raw_metrics else None
        )
        references = list(scenario.input.get("model_answer_evidence_ids", []))
        model_answer = (
            " ".join(item["text"] for item in context.evidence_items(references))
            or None
        )
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
            "star_structure": int(
                scores.get("star_structure", scores.get("structure", 0))
            ),
            "technical_depth": int(
                scores.get("technical_depth", scores.get("content", 0))
            ),
            "conciseness": int(scores.get("conciseness", scores.get("structure", 0))),
            "communication": int(
                scores.get("communication", scores.get("delivery", 0))
            ),
            "impact_metrics": int(
                scores.get("impact_metrics", scores.get("specificity", 0))
            ),
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

    async def _execute_end_to_end(
        self, scenario: CoachScenario, client: _ServiceClient, context: ScenarioContext
    ) -> StageExecution:
        """Run E2E-01 against a disposable SQLite database and production services."""
        del context
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.database import Base
        from app.models import Application, JobPosting
        from app.models.coach_session import (
            InterviewSession,
            SessionQuestion,
            SessionRecording,
        )
        from app.repositories.session_repository import SessionRepository
        from app.schemas.coach import RubricDimension
        from app.services.coach_service import CoachService
        from app.services.followup_planner import FollowUpPlannerService

        temporary = tempfile.TemporaryDirectory(prefix="coach-e2e-")
        database = Path(temporary.name) / "coach-e2e.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
        tables = [
            JobPosting.__table__,
            Application.__table__,
            InterviewSession.__table__,
            SessionQuestion.__table__,
            SessionRecording.__table__,
        ]
        try:
            async with engine.begin() as connection:
                await connection.run_sync(
                    lambda sync_connection: Base.metadata.create_all(
                        sync_connection, tables=tables
                    )
                )
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as database_session:
                repository = SessionRepository(database_session)
                interview = await repository.create_session(
                    company_name=str(scenario.input["company_name"]),
                    role_title=str(scenario.input["role_title"]),
                    config={"question_count": scenario.input["question_count"]},
                )
                questions = await repository.add_questions(
                    interview.id,
                    [
                        {
                            "question_num": index,
                            "text": f"Synthetic interview question {index}",
                            "category": "Behavioural" if index < 3 else "Technical",
                            "difficulty": "medium",
                            "order_in_session": index,
                        }
                        for index in range(1, 4)
                    ],
                )
                await repository.update_session_status(interview.id, "active")

                answer_specs = (
                    (scenario.input["answers"][0], 8, 8, 8.0),
                    (scenario.input["answers"][1], 2, 3, 4.0),
                )
                for index, (answer, specificity, impact, overall) in enumerate(
                    answer_specs
                ):
                    rubric = SessionRubric(
                        dimensions={
                            "specificity": RubricDimension(
                                score=specificity,
                                score_band=score_to_band(specificity),
                                evidence=[str(answer["transcript"])],
                                drill="Add a concrete action.",
                            ),
                            "impact": RubricDimension(
                                score=impact,
                                score_band=score_to_band(impact),
                                evidence=[str(answer["transcript"])],
                                drill="Add a measurable outcome.",
                            ),
                        }
                    )
                    evaluation = AnswerEvaluation(
                        scores={
                            "relevance": int(overall),
                            "star_structure": specificity,
                            "technical_depth": impact,
                            "conciseness": int(overall),
                            "communication": int(overall),
                            "impact_metrics": impact,
                        },
                        overall=overall,
                        evidence_references=[str(answer["transcript"])],
                        rubric=rubric,
                    )
                    await repository.save_recording(
                        session_id=interview.id,
                        question_id=questions[index].id,
                        recording_type="text",
                        transcript=str(answer["transcript"]),
                        speech_metrics=None,
                        video_metrics=None,
                        evaluation_json=json.dumps(evaluation.model_dump(mode="json")),
                        evaluation_state="completed",
                    )
                await repository.record_skip(
                    session_id=interview.id,
                    question_id=questions[2].id,
                )
                await database_session.commit()

                service = CoachService.__new__(CoachService)
                service._feedback_gen = FeedbackGeneratorService(client)  # type: ignore[attr-defined]
                service._followup_planner = FollowUpPlannerService()  # type: ignore[attr-defined]
                with patch(
                    "app.services.feedback_generator._load_candidate_name",
                    return_value="Candidate",
                ):
                    report = await service.end_session(interview.id, database_session)
                follow_up = await service.plan_followup_session(
                    interview.id, database_session
                )
                persisted = await SessionRepository(database_session).get_session(
                    interview.id
                )
                if persisted is None or report.diagnostic is None:
                    raise RuntimeError(
                        "E2E-01 did not persist terminal report evidence"
                    )
                output = report.model_dump(mode="json")
                output.update(
                    {
                        "persistence": {
                            "session_status": persisted.status,
                            "report_snapshot": persisted.report_json is not None,
                            "rubric_snapshot": persisted.rubric is not None,
                        },
                        "persisted_rubric": persisted.rubric,
                        "follow_up_focus": follow_up.focus_areas,
                    }
                )
                return _execution(output, report.diagnostic, client)
        finally:
            await engine.dispose()
            temporary.cleanup()
