"""Grounding, provenance, and bounded-context checks for R6 CV Tailoring."""

from app.runtime.contracts import ExecutionResultCode
from app.runtime_bindings.tasks.cv_tailor import (
    CVTailorOutput,
    validate_cv_tailor_output,
)
from app.schemas.tailor import JDAnalysisResult, TailoredCVResult, TailoredExperience
from app.services.cv_tailor import CVTailor
from app.services.tailor_service import _tailoring_params
from app.services.writing_contracts import (
    CV_TAILORING_PROMPT,
    EVIDENCE_SCHEMA_VERSION,
    GenerationProvenance,
    ValidationResult,
)


def _cv(summary: str = "AWS engineer") -> TailoredCVResult:
    return TailoredCVResult(
        summary=summary,
        skills=[{"category": "Cloud", "items": ["AWS"]}],
        experience=[
            TailoredExperience(
                role="Engineer",
                company="Example Ltd",
                period="2020-2024",
                achievements=["Delivered AWS platform migrations."],
            )
        ],
    )


def test_conflicting_job_language_does_not_authorize_a_new_candidate_claim() -> None:
    result = validate_cv_tailor_output(
        CVTailorOutput(
            tailored_cv=_cv("AWS engineer who has Kubernetes experience"),
            artifact_ref="artifact:cv-001",
            artifact_bytes=100,
        ),
        source_claims=(
            "AWS engineer",
            "Delivered AWS platform migrations.",
            "Kubernetes required by the job",
        ),
    )

    assert result.code is ExecutionResultCode.VALIDATION_FAILURE
    assert result.reason_code == "cv_tailor_unsupported_claim"


def test_long_context_remains_reference_only_and_does_not_change_validation_order() -> (
    None
):
    long_resume = "synthetic evidence " * 20_000
    result = validate_cv_tailor_output(
        CVTailorOutput(
            tailored_cv=_cv(), artifact_ref="artifact:cv-001", artifact_bytes=100
        ),
        source_claims=(
            "AWS engineer",
            "Delivered AWS platform migrations.",
            long_resume,
        ),
    )

    assert result.code is ExecutionResultCode.SUCCESS
    assert result.reason_code == "cv_tailor_valid"


def test_empty_provenance_cannot_authorize_candidate_claims() -> None:
    cv = _cv()
    cv.generation_provenance = GenerationProvenance(
        prompt_metadata=CV_TAILORING_PROMPT,
        evidence_schema_version=EVIDENCE_SCHEMA_VERSION,
        source_evidence_ids=(),
        validation=ValidationResult(passed=True, issues=(), metrics={}),
        claims=(),
    )

    result = validate_cv_tailor_output(
        CVTailorOutput(
            tailored_cv=cv,
            artifact_ref="artifact:cv-001",
            artifact_bytes=100,
        )
    )

    assert result.code is ExecutionResultCode.VALIDATION_FAILURE
    assert result.reason_code == "cv_tailor_unsupported_claim"


async def test_live_cv_tailor_kubernetes_claim_is_withheld_against_aws_only_master() -> None:
    master = {
        "summary_variants": {"cloud": "AWS engineer"},
        "skills": {"cloud": {"items": ["AWS"]}},
        "experience": [
            {
                "role": "Engineer",
                "company": "Example Ltd",
                "period": "2020-2024",
                "achievements": [{"text": "Delivered AWS platform migrations."}],
            }
        ],
        "education": [],
        "certifications": [],
    }

    class Client:
        async def complete_json(self, *_args, **_kwargs):
            return {
                "summary": "AWS and Kubernetes engineer",
                "skills": [{"category": "Cloud", "items": ["AWS"]}],
                "experience": [
                    {
                        "role": "Engineer",
                        "company": "Example Ltd",
                        "period": "2020-2024",
                        "achievements": ["Delivered AWS platform migrations."],
                    }
                ],
            }

    generated = await CVTailor(Client(), master_cv_loader=lambda: master).tailor(
        JDAnalysisResult(role_title="Engineer")
    )
    result = validate_cv_tailor_output(
        CVTailorOutput(
            tailored_cv=generated,
            artifact_ref="artifact:cv-001",
            artifact_bytes=100,
        ),
        source_claims=("AWS engineer", "Delivered AWS platform migrations."),
    )

    assert result.code is ExecutionResultCode.VALIDATION_FAILURE
    assert result.reason_code == "cv_tailor_unsupported_claim"


def test_new_tailoring_metadata_sink_omits_generated_claim_text() -> None:
    rendered = _cv("AWS engineer")
    metadata = _tailoring_params(
        {"variant": "A", "runtime_mode": "new", "custom_instructions": "AWS engineer"},
        rendered,
    )

    assert "AWS engineer" not in metadata
    assert "custom_instructions_hash" in metadata
