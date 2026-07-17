from __future__ import annotations

import json

from app.schemas.tailor import JDAnalysisResult, Requirements
from app.services.writing_contracts import (
    COVER_LETTER_GENERATION_PROMPT,
    EvidenceItem,
    ValidationIssue,
    ValidationResult,
)
from app.services.writing_workflow import (
    AttemptDiagnostic,
    CoverLetterContentPlan,
    WorkflowDiagnostics,
    build_job_requirements,
    create_content_plan,
    select_evidence,
    select_repair_action,
    unused_evidence_ids,
    validate_content_plan,
)


def _evidence(
    evidence_id: str,
    evidence_type: str,
    source_path: str,
) -> EvidenceItem:
    return EvidenceItem(
        id=evidence_id,
        text=f"private evidence text for {evidence_id}",
        source_path=source_path,
        immutable_tokens=(),
        semantic_anchors=(),
        evidence_type=evidence_type,
    )


def test_content_plan_accepts_only_declared_ids():
    plan = CoverLetterContentPlan(
        opening_evidence_ids=("e1",),
        primary_evidence_ids=("e2",),
        secondary_evidence_ids=("e3",),
        alignment_job_requirement_ids=("r1",),
    )

    result = validate_content_plan(
        plan,
        allowed_evidence_ids=("e1", "e2", "e3"),
        allowed_requirement_ids=("r1",),
    )

    assert result.passed is True
    assert result.issues == ()


def test_content_plan_rejects_unknown_evidence_and_requirement_ids():
    plan = CoverLetterContentPlan(
        opening_evidence_ids=("unknown-evidence",),
        primary_evidence_ids=(),
        secondary_evidence_ids=(),
        alignment_job_requirement_ids=("unknown-requirement",),
    )

    result = validate_content_plan(
        plan,
        allowed_evidence_ids=("e1",),
        allowed_requirement_ids=("r1",),
    )

    assert result.passed is False
    assert [issue.code for issue in result.issues] == [
        "unknown_evidence_id",
        "unknown_job_requirement_id",
    ]
    assert all(issue.severity == "blocking" for issue in result.issues)
    assert "private evidence" not in json.dumps(result.metrics)


def test_evidence_selection_and_content_plan_are_deterministic():
    ledger = (
        _evidence("summary", "profile_summary", "summary"),
        _evidence("skill", "skill", "skills.0"),
        _evidence("achievement-1", "achievement", "experience.0.achievements.0"),
        _evidence("certification", "certification", "certifications.0"),
        _evidence("achievement-2", "achievement", "experience.1.achievements.0"),
        _evidence("responsibility", "role_responsibility", "experience.0.responsibilities.0"),
    )
    jd = JDAnalysisResult(
        role_title="Delivery Manager",
        requirements=Requirements(
            must_have=["Programme delivery", "Stakeholder leadership"],
            nice_to_have=["Cloud"],
        ),
    )

    selection_a = select_evidence(ledger)
    selection_b = select_evidence(ledger)
    requirements_a = build_job_requirements(jd)
    requirements_b = build_job_requirements(jd)
    plan_a = create_content_plan(selection_a, requirements_a)
    plan_b = create_content_plan(selection_b, requirements_b)

    assert selection_a == selection_b
    assert requirements_a == requirements_b
    assert plan_a == plan_b
    assert plan_a.primary_evidence_ids[:2] == (
        "achievement-1",
        "achievement-2",
    )
    assert set(unused_evidence_ids(selection_a, plan_a)) == {
        "skill",
        "certification",
    }


def test_repair_selection_uses_priority_allowed_actions_and_no_repeats():
    validation = ValidationResult(
        passed=False,
        issues=(
            ValidationIssue(
                gate="body_length",
                code="under_length",
                severity="blocking",
                message="too short",
            ),
            ValidationIssue(
                gate="numeric_fidelity",
                code="unsupported_numeric_token",
                severity="blocking",
                message="unsupported",
            ),
        ),
        metrics={},
    )
    allowed = ("unsupported_numeric_token", "under_length")

    assert select_repair_action(validation, allowed, ()) == "unsupported_numeric_token"
    assert (
        select_repair_action(
            validation,
            allowed,
            ("unsupported_numeric_token",),
        )
        == "under_length"
    )
    assert (
        select_repair_action(
            validation,
            ("over_length",),
            (),
        )
        is None
    )


def test_workflow_diagnostics_serialize_metadata_without_private_documents():
    validation = ValidationResult(passed=True, issues=(), metrics={"body_word_count": 300})
    diagnostic = WorkflowDiagnostics(
        run_id="run-123",
        task="cover_letter_generation",
        skill_id="cover-letter",
        skill_version="1.0.0",
        prompt_metadata=COVER_LETTER_GENERATION_PROMPT,
        model_id="local-model",
        attempts=(
            AttemptDiagnostic(
                attempt_number=1,
                repair_type=None,
                input_tokens=100,
                output_tokens=50,
                latency_ms=12.5,
                validation=validation,
                computed_body_count=300,
            ),
        ),
        final_state="passed",
    )

    payload = diagnostic.to_dict()
    serialized = json.dumps(payload)

    assert set(payload) == {
        "run_id",
        "task",
        "skill_id",
        "skill_version",
        "prompt_id",
        "prompt_version",
        "model_id",
        "attempts",
        "final_state",
    }
    assert payload["attempts"][0]["attempt_number"] == 1
    assert payload["attempts"][0]["validator_results"]["passed"] is True
    for private_value in (
        "secret-provider-key",
        "person@example.com",
        "+44 7000 000000",
        "private evidence text",
        "full cover letter body",
    ):
        assert private_value not in serialized
