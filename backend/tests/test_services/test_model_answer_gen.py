"""Grounding tests for interview model answers."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.model_answer_gen import (
    ModelAnswerGeneratorService,
    _build_candidate_evidence,
)


def _client(answer: str, result: str, candidate_summary: str) -> MagicMock:
    evidence_ids = [item.id for item in _build_candidate_evidence(candidate_summary)]
    client = MagicMock()
    client.complete_json = AsyncMock(
        return_value={
            "model_answer": answer,
            "star_breakdown": {
                "situation": "A service had recurring incidents.",
                "task": "I needed to improve reliability.",
                "action": "I automated the recurring remediation.",
                "result": result,
            },
            "evidence_references": evidence_ids,
        }
    )
    return client


@pytest.mark.asyncio
async def test_model_answer_preserves_approved_metric_and_includes_evidence_ids() -> None:
    candidate_summary = (
        "A service had recurring incidents. I needed to improve reliability. "
        "I automated the recurring remediation. I reduced incident volume by "
        "25% through automation."
    )
    client = _client(
        "I reduced incident volume by 25% through automation.",
        "I reduced incident volume by 25% through automation.",
        candidate_summary,
    )
    service = ModelAnswerGeneratorService(client)

    result = await service.generate(
        question="Tell me about an improvement.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary=candidate_summary,
    )

    assert "25%" in result.model_answer
    assert result.diagnostic.outcome == "completed"
    combined = "".join(client.complete_json.await_args.args[:2])
    assert '"prompt_id": "model_answer"' in combined
    assert "immutable_tokens" in combined
    assert "25%" in combined


@pytest.mark.asyncio
async def test_model_answer_withholds_mutated_metric() -> None:
    candidate_summary = (
        "A service had recurring incidents. I needed to improve reliability. "
        "I automated the recurring remediation. Incident volume fell by 25%."
    )
    service = ModelAnswerGeneratorService(
        _client(
            "I reduced incident volume by 40%.",
            "Incident volume fell by 40%.",
            candidate_summary,
        )
    )

    result = await service.generate(
        question="Tell me about an improvement.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary=candidate_summary,
    )

    assert result.model_answer == ""
    assert result.diagnostic.outcome == "invalid_output"
    assert result.diagnostic.gate_codes == ["coach_model_answer_numeric_fidelity"]


@pytest.mark.asyncio
async def test_model_answer_without_candidate_evidence_is_empty() -> None:
    client = MagicMock()
    client.complete_json = AsyncMock()
    service = ModelAnswerGeneratorService(client)

    result = await service.generate(
        question="Tell me about a project.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary="",
    )

    assert result.model_answer == ""
    assert result.diagnostic.outcome == "withheld_insufficient_evidence"
    assert result.diagnostic.gate_codes == ["coach_model_answer_no_evidence"]
    client.complete_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_model_answer_provider_failure_is_unavailable() -> None:
    client = MagicMock()
    client.complete_json = AsyncMock(side_effect=RuntimeError("offline"))

    result = await ModelAnswerGeneratorService(client).generate(
        question="Tell me about an improvement.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary="Reduced incident volume by 25% through automation.",
    )

    assert result.model_answer == ""
    assert result.diagnostic.outcome == "unavailable"
    assert result.diagnostic.gate_codes == ["coach_model_answer_provider_unavailable"]


@pytest.mark.asyncio
async def test_model_answer_rejects_incomplete_star_output() -> None:
    client = MagicMock()
    client.complete_json = AsyncMock(
        return_value={
            "model_answer": "I reduced incident volume by 25%.",
            "star_breakdown": {"result": "Incident volume fell by 25%."},
        }
    )

    result = await ModelAnswerGeneratorService(client).generate(
        question="Tell me about an improvement.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary="Reduced incident volume by 25% through automation.",
    )

    assert result.model_answer == ""
    assert result.diagnostic.gate_codes == ["coach_model_answer_star_incomplete"]


@pytest.mark.asyncio
async def test_model_answer_rejects_unknown_evidence_id() -> None:
    candidate_summary = (
        "A service had recurring incidents. I needed to improve reliability. "
        "I automated the recurring remediation. Incident volume fell by 25%."
    )
    client = _client(
        "I reduced incident volume by 25% through automation.",
        "Incident volume fell by 25%.",
        candidate_summary,
    )
    client.complete_json.return_value["evidence_references"] = ["unknown-id"]

    result = await ModelAnswerGeneratorService(client).generate(
        question="Tell me about an improvement.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary=candidate_summary,
    )

    assert result.model_answer == ""
    assert result.diagnostic.gate_codes == [
        "coach_model_answer_unknown_evidence_id"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unsupported_answer",
    [
        "I built a payments platform.",
        "Alex drove the cloud migration.",
        "You delivered the customer portal.",
        "The customer portal was delivered by Alex.",
    ],
)
async def test_model_answer_withholds_unsupported_non_numeric_claims(
    unsupported_answer: str,
) -> None:
    candidate_summary = "I maintained a service and automated incident remediation."
    client = _client(
        unsupported_answer,
        "I maintained a service and automated incident remediation.",
        candidate_summary,
    )

    result = await ModelAnswerGeneratorService(client).generate(
        question="Tell me about a project.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary=candidate_summary,
    )

    assert result.model_answer == ""
    assert result.diagnostic.outcome == "invalid_output"
    assert result.diagnostic.gate_codes == ["coach_model_answer_unsupported_claim"]


@pytest.mark.asyncio
async def test_model_answer_requires_evidence_references() -> None:
    candidate_summary = (
        "A service had recurring incidents. I needed to improve reliability. "
        "I automated the recurring remediation. Incident volume fell by 25%."
    )
    client = _client(
        "I automated the recurring remediation.",
        "Incident volume fell by 25%.",
        candidate_summary,
    )
    client.complete_json.return_value["evidence_references"] = []

    result = await ModelAnswerGeneratorService(client).generate(
        question="Tell me about an improvement.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary=candidate_summary,
    )

    assert result.model_answer == ""
    assert result.diagnostic.gate_codes == ["coach_model_answer_unsupported_claim"]


@pytest.mark.asyncio
async def test_model_answer_rejects_cross_claim_word_recombination() -> None:
    candidate_summary = (
        "A service had recurring incidents. I needed to improve reliability. "
        "I automated the recurring remediation. I built a billing service at Acme. "
        "I worked on a migration at Beta. Incident volume fell by 25%."
    )
    client = _client(
        "I built the migration service at Acme.",
        "Incident volume fell by 25%.",
        candidate_summary,
    )

    result = await ModelAnswerGeneratorService(client).generate(
        question="Tell me about a project.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary=candidate_summary,
    )

    assert result.model_answer == ""
    assert result.diagnostic.gate_codes == ["coach_model_answer_unsupported_claim"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "inverted_answer",
    [
        "I led the migration from Beta to Acme.",
        "I led the migration to Acme from Beta.",
    ],
)
async def test_model_answer_rejects_relational_inversion(
    inverted_answer: str,
) -> None:
    candidate_summary = (
        "A service had recurring incidents. I needed to improve reliability. "
        "I automated the recurring remediation. "
        "I led the migration from Acme to Beta. Incident volume fell by 25%."
    )
    client = _client(
        inverted_answer,
        "Incident volume fell by 25%.",
        candidate_summary,
    )

    result = await ModelAnswerGeneratorService(client).generate(
        question="Tell me about a migration.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary=candidate_summary,
    )

    assert result.model_answer == ""
    assert result.diagnostic.gate_codes == ["coach_model_answer_unsupported_claim"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("evidence_claim", "unsupported_answer"),
    [
        ("I supported Alex managing the migration.", "I managed the migration."),
        ("I did not lead the migration.", "I did lead the migration."),
    ],
)
async def test_model_answer_rejects_meaning_changing_deletions(
    evidence_claim: str,
    unsupported_answer: str,
) -> None:
    candidate_summary = (
        "A service had recurring incidents. I needed to improve reliability. "
        f"I automated the recurring remediation. {evidence_claim} "
        "Incident volume fell by 25%."
    )
    client = _client(
        unsupported_answer,
        "Incident volume fell by 25%.",
        candidate_summary,
    )

    result = await ModelAnswerGeneratorService(client).generate(
        question="Tell me about a migration.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary=candidate_summary,
    )

    assert result.model_answer == ""
    assert result.diagnostic.gate_codes == ["coach_model_answer_unsupported_claim"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("evidence_claim", "unsupported_answer"),
    [
        ("We led the migration for Acme.", "I led the migration for Acme."),
        ("I designed policy systems.", "I designed police systems."),
    ],
)
async def test_model_answer_rejects_actor_and_lexeme_substitution(
    evidence_claim: str,
    unsupported_answer: str,
) -> None:
    candidate_summary = (
        "A service had recurring incidents. I needed to improve reliability. "
        f"I automated the recurring remediation. {evidence_claim} "
        "Incident volume fell by 25%."
    )
    client = _client(
        unsupported_answer,
        "Incident volume fell by 25%.",
        candidate_summary,
    )

    result = await ModelAnswerGeneratorService(client).generate(
        question="Tell me about a migration.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary=candidate_summary,
    )

    assert result.model_answer == ""
    assert result.diagnostic.gate_codes == ["coach_model_answer_unsupported_claim"]


@pytest.mark.asyncio
async def test_model_answer_preserves_unicode_entities_during_grounding() -> None:
    candidate_summary = (
        "A service had recurring incidents. I needed to improve reliability. "
        "I automated the recurring remediation. I worked at 東京. "
        "Incident volume fell by 25%."
    )
    client = _client(
        "I worked at 北京.",
        "Incident volume fell by 25%.",
        candidate_summary,
    )

    result = await ModelAnswerGeneratorService(client).generate(
        question="Tell me about your experience.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary=candidate_summary,
    )

    assert result.model_answer == ""
    assert result.diagnostic.gate_codes == ["coach_model_answer_unsupported_claim"]


@pytest.mark.asyncio
async def test_model_answer_rejects_duplicate_star_sections() -> None:
    claim = "Incident volume fell by 25%."
    candidate_summary = f"{claim}"
    client = _client(claim, claim, candidate_summary)
    client.complete_json.return_value["star_breakdown"] = {
        key: claim for key in ("situation", "task", "action", "result")
    }

    result = await ModelAnswerGeneratorService(client).generate(
        question="Tell me about an improvement.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary=candidate_summary,
    )

    assert result.model_answer == ""
    assert result.diagnostic.gate_codes == ["coach_model_answer_star_incomplete"]


@pytest.mark.asyncio
async def test_model_answer_rejects_star_sections_assigned_to_wrong_roles() -> None:
    candidate_summary = (
        "A service had recurring incidents. I needed to improve reliability. "
        "I automated the recurring remediation. Incident volume fell by 25%."
    )
    client = _client(
        "A service had recurring incidents. I needed to improve reliability. "
        "I automated the recurring remediation. Incident volume fell by 25%.",
        "Incident volume fell by 25%.",
        candidate_summary,
    )
    client.complete_json.return_value["star_breakdown"] = {
        "situation": "Incident volume fell by 25%.",
        "task": "I automated the recurring remediation.",
        "action": "A service had recurring incidents.",
        "result": "I needed to improve reliability.",
    }

    result = await ModelAnswerGeneratorService(client).generate(
        question="Tell me about an improvement.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary=candidate_summary,
    )

    assert result.model_answer == ""
    assert result.diagnostic.gate_codes == ["coach_model_answer_star_incomplete"]


@pytest.mark.asyncio
async def test_model_answer_rejects_overlapping_star_role_keywords() -> None:
    candidate_summary = (
        "In 2024, a service had recurring incidents. I needed to improve reliability. "
        "I automated the recurring remediation. Incident volume fell by 25%."
    )
    client = _client(
        candidate_summary,
        "Incident volume fell by 25%.",
        candidate_summary,
    )
    client.complete_json.return_value["star_breakdown"] = {
        "situation": "Incident volume fell by 25%.",
        "task": "I automated the recurring remediation.",
        "action": "I needed to improve reliability.",
        "result": "In 2024, a service had recurring incidents.",
    }

    result = await ModelAnswerGeneratorService(client).generate(
        question="Tell me about an improvement.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary=candidate_summary,
    )

    assert result.model_answer == ""
    assert result.diagnostic.gate_codes == ["coach_model_answer_star_incomplete"]


@pytest.mark.asyncio
async def test_model_answer_requires_exclusive_star_role_semantics() -> None:
    candidate_summary = (
        "I improved the service. We achieved the goal. "
        "We faced a service challenge. I needed to deliver an improved outcome."
    )
    client = _client(
        candidate_summary,
        "I needed to deliver an improved outcome.",
        candidate_summary,
    )
    client.complete_json.return_value["star_breakdown"] = {
        "situation": "I improved the service.",
        "task": "We achieved the goal.",
        "action": "We faced a service challenge.",
        "result": "I needed to deliver an improved outcome.",
    }

    result = await ModelAnswerGeneratorService(client).generate(
        question="Tell me about an improvement.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary=candidate_summary,
    )

    assert result.model_answer == ""
    assert result.diagnostic.gate_codes == ["coach_model_answer_star_incomplete"]


@pytest.mark.asyncio
async def test_model_answer_accepts_unambiguous_service_action_and_project_result() -> None:
    candidate_summary = (
        "A service had recurring incidents. I needed to improve reliability. "
        "I automated the service remediation. I delivered the project on time."
    )
    client = _client(
        candidate_summary,
        "I delivered the project on time.",
        candidate_summary,
    )
    client.complete_json.return_value["star_breakdown"]["action"] = (
        "I automated the service remediation."
    )

    result = await ModelAnswerGeneratorService(client).generate(
        question="Tell me about an improvement.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary=candidate_summary,
    )

    assert result.diagnostic.outcome == "completed"
    assert result.model_answer == candidate_summary


@pytest.mark.asyncio
async def test_model_answer_accepts_common_star_role_wording() -> None:
    candidate_summary = (
        "The production system suffered recurring incidents. "
        "My objective was to improve reliability. "
        "I automated the recurring remediation. Latency dropped by 25%."
    )
    client = _client(
        candidate_summary,
        "Latency dropped by 25%.",
        candidate_summary,
    )
    client.complete_json.return_value["star_breakdown"] = {
        "situation": "The production system suffered recurring incidents.",
        "task": "My objective was to improve reliability.",
        "action": "I automated the recurring remediation.",
        "result": "Latency dropped by 25%.",
    }

    result = await ModelAnswerGeneratorService(client).generate(
        question="Tell me about an improvement.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary=candidate_summary,
    )

    assert result.diagnostic.outcome == "completed"
    assert result.model_answer == candidate_summary


@pytest.mark.asyncio
async def test_model_answer_accepts_explicit_truthful_withholding() -> None:
    candidate_summary = "AWS. Terraform. Python. SQL."
    client = MagicMock()
    client.complete_json = AsyncMock(
        return_value={
            "model_answer": "",
            "star_breakdown": {key: "" for key in ("situation", "task", "action", "result")},
            "evidence_references": [],
        }
    )

    result = await ModelAnswerGeneratorService(client).generate(
        question="Tell me about a migration result.",
        category="Behavioural",
        difficulty="medium",
        company_name="Example",
        candidate_summary=candidate_summary,
    )

    assert result.model_answer == ""
    assert result.diagnostic.outcome == "withheld_insufficient_evidence"
    assert result.diagnostic.execution_mode == "llm"
    assert result.diagnostic.gate_codes == ["coach_model_answer_no_evidence"]


def test_candidate_evidence_removes_display_labels_from_atomic_claims() -> None:
    evidence = _build_candidate_evidence(
        "Summary: Led a platform migration.\nKey Skills: AWS; Terraform"
    )

    assert [item.text for item in evidence] == [
        "Led a platform migration.",
        "AWS",
        "Terraform",
    ]
