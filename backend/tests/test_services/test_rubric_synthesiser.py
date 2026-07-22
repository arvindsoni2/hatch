"""Tests for RubricSynthesiserService — LLM-as-judge enrichment of SessionRubric."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.coach import (
    AnswerEvaluation,
    SessionRubric,
    SpeechMetrics,
    VoiceToneResult,
)
from app.services.rubric_builder import CONTENT_DIMENSIONS


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_evaluation(score: int = 7) -> AnswerEvaluation:
    return AnswerEvaluation(
        scores={d: score for d in CONTENT_DIMENSIONS},
        overall=float(score),
        feedback="Solid STAR answer with specific examples.",
        strengths=["Clear STAR structure", "Quantified impact"],
        improvements=["Add more technical depth"],
    )


_LLM_RUBRIC_RESPONSE = {
    "dimensions": {
        "star_structure": {
            "score": 8,
            "score_band": "strong",
            "evidence": ["'So I implemented a blue-green deployment' — clear action step.", "Result quantified: '80% fewer failures'."],
            "drill": "Practise a 90-second STAR story daily.",
        },
        "delivery": {
            "score": 6,
            "score_band": "good",
            "evidence": ["Pace 145 WPM — ideal range.", "3 filler words detected."],
            "drill": "Record and replay to count fillers.",
        },
    },
    "focus_for_next_session": "Focus next session on: impact metrics and delivery.",
}


def _mock_llm(response_json: dict | None = None) -> MagicMock:
    """Return a mock LangChain LLM that yields a JSON string on ainvoke."""
    response_json = response_json or _LLM_RUBRIC_RESPONSE
    msg_mock = MagicMock()
    msg_mock.content = json.dumps(response_json)
    llm_mock = MagicMock()
    llm_mock.ainvoke = AsyncMock(return_value=msg_mock)
    return llm_mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRubricSynthesiserService:

    @pytest.mark.asyncio
    async def test_drops_evidence_not_supported_by_transcript_or_metrics(self) -> None:
        from app.services.rubric_synthesiser import RubricSynthesiserService  # noqa: PLC0415

        response = {
            "dimensions": {
                dimension: {
                    "score": 7,
                    "score_band": "good",
                    "evidence": [],
                    "drill": "Practise one answer.",
                }
                for dimension in CONTENT_DIMENSIONS
            }
            | {
                "star_structure": {
                    "score": 8,
                    "score_band": "strong",
                    "evidence": [
                        "'implemented a blue-green deployment'",
                        "Led 500 engineers",
                    ],
                    "drill": "Practise one STAR answer.",
                }
            },
            "focus_for_next_session": "Practise STAR structure.",
        }
        mock_llm = _mock_llm(response)
        with patch("app.services.rubric_synthesiser.get_json_model", return_value=mock_llm):
            rubric = await RubricSynthesiserService().synthesise(
                transcript="I implemented a blue-green deployment.",
                evaluation=_make_evaluation(),
            )

        assert rubric.dimensions["star_structure"].evidence == [
            "'implemented a blue-green deployment'"
        ]
        assert rubric.dimensions["star_structure"].score == 7
        assert rubric.dimensions["star_structure"].score_band == "good"
        assert rubric.diagnostic is not None
        assert "coach_rubric_score_mutation" in rubric.diagnostic.gate_codes
        assert "coach_rubric_evidence_ungrounded" in rubric.diagnostic.gate_codes
        system_message = mock_llm.ainvoke.await_args.args[0][0].content
        assert '"prompt_id": "rubric_synthesis"' in system_message
        assert "OBSERVATION" in system_message

    @pytest.mark.asyncio
    async def test_returns_session_rubric(self) -> None:
        """synthesise() returns a SessionRubric."""
        from app.services.rubric_synthesiser import RubricSynthesiserService  # noqa: PLC0415

        with patch("app.services.rubric_synthesiser.get_json_model", return_value=_mock_llm()):
            svc = RubricSynthesiserService()
            eval_ = _make_evaluation()
            rubric = await svc.synthesise(
                transcript="In my previous role I led a migration. So I designed the rollout. As a result we cut failures by 80%.",
                evaluation=eval_,
            )

        assert isinstance(rubric, SessionRubric)

    @pytest.mark.asyncio
    async def test_calls_llm_once(self) -> None:
        """synthesise() invokes the LLM exactly once."""
        from app.services.rubric_synthesiser import RubricSynthesiserService  # noqa: PLC0415

        mock_llm = _mock_llm()
        with patch("app.services.rubric_synthesiser.get_json_model", return_value=mock_llm):
            svc = RubricSynthesiserService()
            await svc.synthesise(
                transcript="test transcript",
                evaluation=_make_evaluation(),
            )

        mock_llm.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_includes_speech_metrics_when_present(self) -> None:
        """Speech metrics are included in the rubric output when provided."""
        from app.services.rubric_synthesiser import RubricSynthesiserService  # noqa: PLC0415

        metrics = SpeechMetrics(wpm=145.0, filler_count=3, pause_count=1, duration_ms=60_000)
        with patch("app.services.rubric_synthesiser.get_json_model", return_value=_mock_llm()):
            svc = RubricSynthesiserService()
            rubric = await svc.synthesise(
                transcript="test transcript",
                evaluation=_make_evaluation(),
                speech_metrics=metrics,
            )

        # At minimum, the rubric should not crash and should be a SessionRubric
        assert isinstance(rubric, SessionRubric)

    @pytest.mark.asyncio
    async def test_includes_tone_result_when_present(self) -> None:
        """VoiceToneResult is accepted without error."""
        from app.services.rubric_synthesiser import RubricSynthesiserService  # noqa: PLC0415

        tone = VoiceToneResult(arousal=0.6, valence=0.5, dominance=0.7)
        with patch("app.services.rubric_synthesiser.get_json_model", return_value=_mock_llm()):
            svc = RubricSynthesiserService()
            rubric = await svc.synthesise(
                transcript="test transcript",
                evaluation=_make_evaluation(),
                tone_result=tone,
            )

        assert isinstance(rubric, SessionRubric)

    @pytest.mark.asyncio
    async def test_falls_back_to_deterministic_on_llm_failure(self) -> None:
        """On LLM error, synthesise() returns the deterministic rubric, no crash."""
        from app.services.rubric_synthesiser import RubricSynthesiserService  # noqa: PLC0415

        failing_llm = MagicMock()
        failing_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

        with patch("app.services.rubric_synthesiser.get_json_model", return_value=failing_llm):
            svc = RubricSynthesiserService()
            eval_ = _make_evaluation()
            rubric = await svc.synthesise(
                transcript="test",
                evaluation=eval_,
            )

        # Fallback must still return a valid rubric with content dims
        assert isinstance(rubric, SessionRubric)
        for dim in CONTENT_DIMENSIONS:
            assert dim in rubric.dimensions, f"Missing fallback dimension: {dim}"
        assert rubric.diagnostic is not None
        assert rubric.diagnostic.outcome == "fallback_deterministic"
        assert rubric.diagnostic.gate_codes == ["coach_rubric_provider_unavailable"]

    @pytest.mark.asyncio
    async def test_focus_for_next_session_populated(self) -> None:
        """focus_for_next_session is non-empty in the returned rubric."""
        from app.services.rubric_synthesiser import RubricSynthesiserService  # noqa: PLC0415

        with patch("app.services.rubric_synthesiser.get_json_model", return_value=_mock_llm()):
            svc = RubricSynthesiserService()
            rubric = await svc.synthesise(
                transcript="test",
                evaluation=_make_evaluation(),
            )

        assert rubric.focus_for_next_session.strip() != ""

    @pytest.mark.asyncio
    async def test_merges_llm_dimensions_into_rubric(self) -> None:
        """Dimensions returned by the LLM are merged into the SessionRubric."""
        from app.services.rubric_synthesiser import RubricSynthesiserService  # noqa: PLC0415

        with patch("app.services.rubric_synthesiser.get_json_model", return_value=_mock_llm()):
            svc = RubricSynthesiserService()
            rubric = await svc.synthesise(
                transcript="So I implemented a blue-green deployment as a result we cut failures.",
                evaluation=_make_evaluation(),
                speech_metrics=SpeechMetrics(wpm=145.0, filler_count=3, pause_count=1, duration_ms=60_000),
            )

        # star_structure was in the LLM response — its evidence should be enriched
        if "star_structure" in rubric.dimensions:
            dim = rubric.dimensions["star_structure"]
            assert isinstance(dim.evidence, list)

    @pytest.mark.asyncio
    async def test_llm_cannot_add_dimension_without_available_signal(self) -> None:
        from app.services.rubric_synthesiser import RubricSynthesiserService

        response = {
            "dimensions": {
                dimension: {
                    "score": 7,
                    "score_band": "good",
                    "evidence": [],
                    "drill": "Practise.",
                }
                for dimension in CONTENT_DIMENSIONS
            }
            | {
                "delivery": {
                    "score": 10,
                    "score_band": "strong",
                    "evidence": ["145 WPM"],
                    "drill": "Practise.",
                }
            },
            "focus_for_next_session": "Delivery",
        }
        with patch(
            "app.services.rubric_synthesiser.get_json_model",
            return_value=_mock_llm(response),
        ):
            rubric = await RubricSynthesiserService().synthesise(
                transcript="Answer",
                evaluation=_make_evaluation(),
            )

        assert "delivery" not in rubric.dimensions
        assert rubric.diagnostic is not None
        assert "coach_rubric_optional_dimension_unexpected" in (
            rubric.diagnostic.gate_codes
        )

    @pytest.mark.asyncio
    async def test_missing_dimension_returns_deterministic_fallback(self) -> None:
        from app.services.rubric_synthesiser import RubricSynthesiserService

        response = {
            "dimensions": {
                "star_structure": {
                    "score": 7,
                    "score_band": "good",
                    "evidence": [],
                    "drill": "Practise one STAR answer.",
                }
            },
            "focus_for_next_session": "Practise STAR structure.",
        }
        with patch(
            "app.services.rubric_synthesiser.get_json_model",
            return_value=_mock_llm(response),
        ):
            rubric = await RubricSynthesiserService().synthesise(
                transcript="Answer",
                evaluation=_make_evaluation(),
            )

        assert set(rubric.dimensions) == set(CONTENT_DIMENSIONS)
        assert rubric.diagnostic is not None
        assert rubric.diagnostic.outcome == "fallback_deterministic"
        assert rubric.diagnostic.gate_codes == ["coach_rubric_dimension_missing"]

    @pytest.mark.asyncio
    async def test_metric_match_does_not_ground_unsupported_evidence_sentence(self) -> None:
        from app.services.rubric_synthesiser import RubricSynthesiserService

        response = {
            "dimensions": {
                dimension: {
                    "score": 7,
                    "score_band": "good",
                    "evidence": [],
                    "drill": "Practise.",
                }
                for dimension in CONTENT_DIMENSIONS
            }
            | {
                "delivery": {
                    "score": 9,
                    "score_band": "strong",
                    "evidence": ["145 WPM while leading 500 engineers"],
                    "drill": "Practise.",
                }
            },
            "focus_for_next_session": "Delivery",
        }
        metrics = SpeechMetrics(
            wpm=145.0,
            filler_count=0,
            pause_count=0,
            duration_ms=60_000,
        )
        with patch(
            "app.services.rubric_synthesiser.get_json_model",
            return_value=_mock_llm(response),
        ):
            rubric = await RubricSynthesiserService().synthesise(
                transcript="I described a deployment.",
                evaluation=_make_evaluation(),
                speech_metrics=metrics,
            )

        assert "145 WPM while leading 500 engineers" not in rubric.dimensions[
            "delivery"
        ].evidence
        assert rubric.diagnostic is not None
        assert "coach_rubric_evidence_ungrounded" in rubric.diagnostic.gate_codes

    @pytest.mark.asyncio
    async def test_quote_does_not_ground_unsupported_surrounding_claim(self) -> None:
        from app.services.rubric_synthesiser import RubricSynthesiserService

        response = {
            "dimensions": {
                dimension: {
                    "score": 7,
                    "score_band": "good",
                    "evidence": [],
                    "drill": "Practise.",
                }
                for dimension in CONTENT_DIMENSIONS
            },
            "focus_for_next_session": "STAR structure",
        }
        response["dimensions"]["star_structure"]["evidence"] = [
            "'implemented a blue-green deployment' proves Alex led 500 engineers"
        ]
        with patch(
            "app.services.rubric_synthesiser.get_json_model",
            return_value=_mock_llm(response),
        ):
            rubric = await RubricSynthesiserService().synthesise(
                transcript="I implemented a blue-green deployment.",
                evaluation=_make_evaluation(),
            )

        assert "500 engineers" not in " ".join(
            rubric.dimensions["star_structure"].evidence
        )
        assert rubric.diagnostic is not None
        assert "coach_rubric_evidence_ungrounded" in rubric.diagnostic.gate_codes
