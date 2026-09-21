"""Contracts and deterministic validation for the R6 CV Tailor binding."""

from app.runtime.contracts import ExecutionResultCode
from app.runtime_bindings.tasks.cv_tailor import (
    CV_TAILOR_V1,
    CVTailorInput,
    CVTailorOutput,
    validate_cv_tailor_output,
)
from app.schemas.tailor import TailoredCVResult, TailoredExperience


def _output(**changes) -> CVTailorOutput:
    values = {
        "tailored_cv": TailoredCVResult(
            summary="Platform engineer with AWS delivery experience.",
            skills=[{"category": "Cloud", "items": ["AWS"]}],
            experience=[
                TailoredExperience(
                    role="Engineer",
                    company="Example Ltd",
                    period="2020-2024",
                    achievements=["Delivered AWS platform migrations."],
                )
            ],
        ),
        "artifact_ref": "artifact:cv-001",
        "artifact_bytes": 100,
        "source_claims": (
            "Platform engineer with AWS delivery experience.",
            "Delivered AWS platform migrations.",
            "AWS",
            "Engineer",
            "Example Ltd",
            "2020-2024",
        ),
    }
    values.update(changes)
    return CVTailorOutput(**values)


def test_cv_tailor_contract_declares_the_six_candidate_and_job_contexts() -> None:
    assert CV_TAILOR_V1.task_id == "cv.tailor"
    assert CV_TAILOR_V1.version == 1
    assert {item.capability for item in CV_TAILOR_V1.context_requirements} == {
        "candidate.verified_experience",
        "candidate.achievements",
        "candidate.skills",
        "candidate.resume_text",
        "job.requirements",
        "job.description",
    }
    assert (
        CVTailorInput(
            application_ref="application:synthetic-001",
            job_ref="job:synthetic-001",
        ).application_ref
        == "application:synthetic-001"
    )


def test_validator_rejects_an_unsupported_candidate_claim_before_artifact_commit() -> (
    None
):
    output = _output(
        tailored_cv=TailoredCVResult(
            summary="Platform engineer who led a 300% revenue increase.",
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
    )

    result = validate_cv_tailor_output(output)

    assert result.code is ExecutionResultCode.VALIDATION_FAILURE
    assert result.reason_code == "cv_tailor_unsupported_claim"


def test_validator_rejects_sparse_output_without_required_sections() -> None:
    result = validate_cv_tailor_output(
        _output(tailored_cv=TailoredCVResult(summary="", skills=[], experience=[]))
    )

    assert result.code is ExecutionResultCode.VALIDATION_FAILURE
    assert result.reason_code == "cv_tailor_required_section_missing"


def test_transient_source_claims_are_not_serialized_into_runtime_payloads() -> None:
    assert "source_claims" not in _output().model_dump()
