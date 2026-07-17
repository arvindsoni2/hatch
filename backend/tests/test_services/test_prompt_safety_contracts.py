from __future__ import annotations

from app.services.prompt_catalog import (
    candidate_claim_contract,
    prompt_contract_block,
    research_claim_contract,
    source_contains,
    validate_candidate_output,
)
from app.services.writing_contracts import build_evidence_ledger


def test_prompt_contract_block_serializes_stable_metadata() -> None:
    block = prompt_contract_block("model_answer")

    assert "PROMPT METADATA:" in block
    assert '"prompt_id": "model_answer"' in block
    assert '"prompt_version": "1.0.0"' in block
    assert '"schema_version": "1.0.0"' in block


def test_candidate_contract_requires_ids_exact_numbers_and_safe_fallback() -> None:
    block = candidate_claim_contract("model_answer")

    assert "approved evidence ID" in block
    assert "Preserve numeric tokens exactly" in block
    assert "review_required" in block
    assert "Do not infer" in block


def test_research_contract_requires_provenance_and_not_verified() -> None:
    block = research_claim_contract("company_research")

    assert "source ID" in block
    assert "retrieval timestamp" in block
    assert "fact date" in block
    assert "verification state" in block
    assert "not_verified" in block


def test_source_contains_normalizes_case_and_whitespace() -> None:
    assert source_contains(
        "Outside   IR35",
        "This contract is explicitly OUTSIDE IR35.",
    )
    assert not source_contains("£700/day", "Competitive daily rate")


def test_candidate_output_rejects_unsupported_number() -> None:
    ledger = build_evidence_ledger(
        {"experience": [{"achievements": ["Improved throughput by 15%."]}]}
    )

    result = validate_candidate_output(
        ["Improved throughput by 99%."],
        ledger,
    )

    assert result.passed is False
    assert [issue.code for issue in result.issues] == [
        "unsupported_numeric_token"
    ]


def test_candidate_output_accepts_declared_employer_context_number() -> None:
    ledger = build_evidence_ledger(
        {"experience": [{"achievements": ["Led platform delivery."]}]}
    )

    result = validate_candidate_output(
        ["The employer operates across 40 locations."],
        ledger,
        employer_context=("The programme spans 40 locations.",),
    )

    assert result.passed is True
