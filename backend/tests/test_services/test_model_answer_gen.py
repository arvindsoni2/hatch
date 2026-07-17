"""Grounding tests for interview model answers."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.model_answer_gen import ModelAnswerGeneratorService


def _client(answer: str, result: str) -> MagicMock:
    client = MagicMock()
    client.complete_json = AsyncMock(
        return_value={
            "model_answer": answer,
            "star_breakdown": {"result": result},
        }
    )
    return client


@pytest.mark.asyncio
async def test_model_answer_preserves_approved_metric_and_includes_evidence_ids() -> None:
    client = _client(
        "I reduced incident volume by 25% through automation.",
        "Incident volume fell by 25%.",
    )
    service = ModelAnswerGeneratorService(client)

    result = await service.generate(
        question="Tell me about an improvement.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary="Reduced incident volume by 25% through automation.",
    )

    assert "25%" in result
    combined = "".join(client.complete_json.await_args.args[:2])
    assert '"prompt_id": "model_answer"' in combined
    assert "immutable_tokens" in combined
    assert "25%" in combined


@pytest.mark.asyncio
async def test_model_answer_withholds_mutated_metric() -> None:
    service = ModelAnswerGeneratorService(
        _client(
            "I reduced incident volume by 40%.",
            "Incident volume fell by 40%.",
        )
    )

    result = await service.generate(
        question="Tell me about an improvement.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary="Reduced incident volume by 25%.",
    )

    assert result == ""


@pytest.mark.asyncio
async def test_model_answer_without_candidate_evidence_is_empty() -> None:
    client = _client("A fabricated STAR story.", "A fabricated result.")
    service = ModelAnswerGeneratorService(client)

    result = await service.generate(
        question="Tell me about a project.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary="",
    )

    assert result == ""
    client.complete_json.assert_not_awaited()
