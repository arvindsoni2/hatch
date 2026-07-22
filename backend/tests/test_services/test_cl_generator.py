"""Tests for CoverLetterGenerator — word count, keywords, paragraph regeneration."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.tailor import (
    ATSKeywords,
    CoverLetterResult,
    JDAnalysisResult,
    TailoredCVResult,
    TailoredExperience,
)
from app.services.cl_generator import CoverLetterGenerator, _parse_cover_letter
from app.services.writing_workflow import CoverLetterContentPlan

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PERSONAL = {
    "full_name": "Arvind Soni",
    "email": "arvind@example.com",
    "phone": "+44 7000 000000",
    "location": "United Kingdom",
}

JD_ANALYSIS = JDAnalysisResult(
    role_title="Solutions Architect",
    ats_keywords=ATSKeywords(
        technical=["AWS", "Terraform", "GenAI"],
        methodologies=["TOGAF"],
        soft_skills=[],
        domain=["energy"],
        certifications=[],
    ),
)

TAILORED_CV = TailoredCVResult(
    summary="Solutions Architect with 20+ years...",
    skills=[],
    experience=[
        TailoredExperience(
            role="Solutions Architect",
            company="Company A",
            period="2022–Present",
            achievements=["Led cloud migration saving £500K."],
        )
    ],
    certifications=["PMP"],
)

TAILORED_CV_WITH_120_PLUS = TailoredCVResult(
    summary="Delivery leader for complex estates.",
    skills=[],
    experience=[
        TailoredExperience(
            role="Delivery Manager",
            company="Company B",
            period="2020-Present",
            achievements=["Managed rollout across 120+ locations for critical services."],
        )
    ],
    certifications=[],
)

SHORT_CL_RESPONSE = {
    "subject_line": "Solutions Architect — Outside IR35",
    "greeting": "Dear Hiring Manager,",
    "body_paragraphs": [
        "I am writing to express my strong interest in the Solutions Architect position.",
        "With 20+ years of experience delivering enterprise-scale AWS and Terraform architectures, I bring a proven track record.",
        "My expertise in GenAI and TOGAF aligns closely with your requirements for cloud transformation leadership.",
        "I welcome the opportunity to discuss how my experience can contribute to your programme.",
    ],
    "sign_off": "Yours sincerely,",
    "word_count": 62,
    "key_keywords_used": ["AWS", "Terraform", "GenAI", "TOGAF"],
}

LONG_CL_RESPONSE = {
    **SHORT_CL_RESPONSE,
    "body_paragraphs": [
        " ".join(["word"] * 100),
        " ".join(["word"] * 100),
        " ".join(["word"] * 100),
        " ".join(["word"] * 100),
    ],
    "word_count": 400,
}


def cl_response_with_counts(counts: list[int], *, word: str = "body") -> dict:
    return {
        **SHORT_CL_RESPONSE,
        "body_paragraphs": [" ".join([word] * count) for count in counts],
        "word_count": 999,
    }


def make_mock_client(response_dict: dict) -> MagicMock:
    client = MagicMock()
    client.complete_json = AsyncMock(return_value=response_dict)
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_returns_cover_letter():
    client = make_mock_client(SHORT_CL_RESPONSE)
    gen = CoverLetterGenerator(client)
    result = await gen.generate(JD_ANALYSIS, TAILORED_CV, PERSONAL)

    assert isinstance(result, CoverLetterResult)
    assert result.subject_line != ""
    assert len(result.body_paragraphs) == 4
    assert result.word_count > 0
    assert result.generation_provenance is not None
    assert result.generation_provenance.prompt_metadata.prompt_version == "2.0.0"
    assert "generation_provenance" not in result.model_dump()


@pytest.mark.asyncio
async def test_word_count_within_range():
    client = make_mock_client(cl_response_with_counts([50, 75, 70, 45, 35]))
    gen = CoverLetterGenerator(client)
    result = await gen.generate(JD_ANALYSIS, TAILORED_CV, PERSONAL)

    assert result.word_count == 275
    assert client.complete_json.call_count == 1


@pytest.mark.asyncio
async def test_long_letter_triggers_trim_retry():
    """A letter > 350 words should trigger a second Claude call."""
    # First call returns too-long, second call returns short
    client = MagicMock()
    client.complete_json = AsyncMock(side_effect=[LONG_CL_RESPONSE, cl_response_with_counts([60] * 5)])
    gen = CoverLetterGenerator(client)

    result = await gen.generate(JD_ANALYSIS, TAILORED_CV, PERSONAL)

    # Should have called twice (initial + trim retry)
    assert client.complete_json.call_count == 2
    assert result.word_count == 300


@pytest.mark.asyncio
async def test_jd_keywords_present_in_result():
    client = make_mock_client(cl_response_with_counts([60] * 5))
    gen = CoverLetterGenerator(client)
    result = await gen.generate(JD_ANALYSIS, TAILORED_CV, PERSONAL)

    assert "AWS" in result.key_keywords_used


@pytest.mark.asyncio
async def test_initial_prompt_requests_five_paragraph_target_budget():
    client = make_mock_client(cl_response_with_counts([60] * 5))
    gen = CoverLetterGenerator(client)

    await gen.generate(JD_ANALYSIS, TAILORED_CV, PERSONAL)

    prompt = client.complete_json.call_args.args[1]
    assert "five body paragraphs" in prompt
    assert "285-315 body words" in prompt
    assert "STRUCTURE (5 paragraphs)" in prompt
    assert "CONTENT_PLAN" in prompt
    assert "opening_evidence_ids" in prompt
    assert "alignment_job_requirement_ids" in prompt


@pytest.mark.asyncio
async def test_cover_letter_flags_unsupported_metric():
    response = {
        **SHORT_CL_RESPONSE,
        "body_paragraphs": [
            "I reduced platform costs by 99% while delivering AWS architecture.",
            "I can bring that delivery focus to your programme.",
        ],
        "word_count": 18,
    }
    client = make_mock_client(response)
    gen = CoverLetterGenerator(client)

    result = await gen.generate(JD_ANALYSIS, TAILORED_CV, PERSONAL)

    assert result.grounding_issues
    assert "99%" in result.grounding_issues[0]


@pytest.mark.asyncio
async def test_regenerate_paragraph():
    client = make_mock_client({"paragraph": "Rewritten paragraph with AWS and Terraform focus."})
    gen = CoverLetterGenerator(client)

    current = CoverLetterResult(
        subject_line="Test",
        greeting="Dear Hiring Manager,",
        body_paragraphs=["Para 1", "Para 2", "Para 3", "Para 4"],
        sign_off="Sincerely,",
        word_count=8,
        key_keywords_used=[],
    )

    result = await gen.regenerate_paragraph(1, "Focus more on AWS experience", current, JD_ANALYSIS)

    assert result.body_paragraphs[1] == "Rewritten paragraph with AWS and Terraform focus."
    assert result.body_paragraphs[0] == "Para 1"  # Other paragraphs unchanged


@pytest.mark.asyncio
async def test_regenerate_paragraph_cannot_bypass_numeric_fidelity():
    client = make_mock_client({"paragraph": "Managed 120 locations."})
    gen = CoverLetterGenerator(client)
    current = CoverLetterResult(
        subject_line="Test",
        greeting="Dear Hiring Manager,",
        body_paragraphs=[
            "Managed 120+ locations.",
            "Delivered safely.",
        ],
        sign_off="Sincerely,",
        word_count=5,
    )

    result = await gen.regenerate_paragraph(
        0,
        "Rephrase this paragraph",
        current,
        JD_ANALYSIS,
    )

    assert any("120 locations" in issue for issue in result.grounding_issues)
    assert result.generation_provenance is not None
    assert (
        result.generation_provenance.prompt_metadata.prompt_id
        == "cover_letter_paragraph_regeneration"
    )
    prompt = " ".join(str(arg) for arg in client.complete_json.call_args.args)
    assert "SHARED FACTUALITY CONTRACT (v1.0.0)" in prompt
    assert "SHARED NUMERIC-FIDELITY CONTRACT (v1.0.0)" in prompt


def test_parse_cover_letter():
    result = _parse_cover_letter(SHORT_CL_RESPONSE)
    assert result.subject_line == "Solutions Architect — Outside IR35"
    assert len(result.body_paragraphs) == 4
    assert result.word_count == 59


def test_parse_cover_letter_counts_only_body_paragraphs():
    result = _parse_cover_letter(
        {
            "subject_line": "Application: Solutions Architect",
            "greeting": "Dear Hiring Manager,",
            "body_paragraphs": ["one two three"],
            "sign_off": "Kind regards,\nArvind Soni",
            "word_count": 999,
        }
    )

    assert result.word_count == 3


def test_parse_cover_letter_uses_canonical_body_tokenizer_examples():
    result = _parse_cover_letter(
        {
            "body_paragraphs": [
                "£2.5m budget 20+ years 120+ locations 15% improvement U.K. delivery",
                "candidate@example.com https://example.com/jobs/123 end-to-end design/architecture",
                "cloud—platform candidate’s experience and/or (120+) locations",
            ],
            "word_count": 999,
        }
    )

    assert result.word_count == 23


def test_model_reported_word_count_cannot_override_computed_body_count():
    result = _parse_cover_letter(
        {
            "body_paragraphs": [" ".join(["body"] * 249)],
            "word_count": 300,
        }
    )

    assert result.word_count == 249


@pytest.mark.asyncio
async def test_249_words_triggers_under_length_repair():
    client = MagicMock()
    client.complete_json = AsyncMock(
        side_effect=[
            cl_response_with_counts([49, 50, 50, 50, 50]),
            cl_response_with_counts([60, 60, 60, 60, 60]),
        ]
    )
    gen = CoverLetterGenerator(client)

    result = await gen.generate(JD_ANALYSIS, TAILORED_CV, PERSONAL)

    assert client.complete_json.call_count == 2
    assert result.word_count == 300
    repair_prompt = client.complete_json.call_args_list[1].args[1]
    assert "previous draft was 249 body words" in repair_prompt
    assert "target of 285-315 body words" in repair_prompt
    assert "UNUSED_APPROVED_EVIDENCE" in repair_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [250, 350])
async def test_boundary_word_counts_pass_without_repair(count: int):
    client = make_mock_client(cl_response_with_counts([count]))
    gen = CoverLetterGenerator(client)

    result = await gen.generate(JD_ANALYSIS, TAILORED_CV, PERSONAL)

    assert result.word_count == count
    assert client.complete_json.call_count == 1


@pytest.mark.asyncio
async def test_351_words_triggers_over_length_repair():
    client = MagicMock()
    client.complete_json = AsyncMock(
        side_effect=[
            cl_response_with_counts([351]),
            cl_response_with_counts([300]),
        ]
    )
    gen = CoverLetterGenerator(client)

    result = await gen.generate(JD_ANALYSIS, TAILORED_CV, PERSONAL)

    assert client.complete_json.call_count == 2
    assert result.word_count == 300
    repair_prompt = client.complete_json.call_args_list[1].args[1]
    assert "previous draft was 351 body words" in repair_prompt
    assert "compress" in repair_prompt


@pytest.mark.asyncio
async def test_retry_limit_stops_after_same_under_length_defect():
    client = MagicMock()
    client.complete_json = AsyncMock(
        side_effect=[
            cl_response_with_counts([249]),
            cl_response_with_counts([248]),
            cl_response_with_counts([300]),
        ]
    )
    gen = CoverLetterGenerator(client)

    result = await gen.generate(JD_ANALYSIS, TAILORED_CV, PERSONAL)

    assert client.complete_json.call_count == 2
    assert result.word_count == 248
    assert result.validation_status == "review_required"
    assert any("expected 250-350" in issue for issue in result.validation_issues)


@pytest.mark.asyncio
async def test_second_repair_allowed_for_different_remaining_length_defect():
    client = MagicMock()
    client.complete_json = AsyncMock(
        side_effect=[
            cl_response_with_counts([351]),
            cl_response_with_counts([249]),
            cl_response_with_counts([300]),
        ]
    )
    gen = CoverLetterGenerator(client)

    result = await gen.generate(JD_ANALYSIS, TAILORED_CV, PERSONAL)

    assert client.complete_json.call_count == 3
    assert result.word_count == 300
    assert result.validation_status == "repaired"


@pytest.mark.asyncio
async def test_mutated_candidate_numeric_token_blocks_and_repairs():
    client = MagicMock()
    client.complete_json = AsyncMock(
        side_effect=[
            {
                **cl_response_with_counts([60] * 5),
                "body_paragraphs": [
                    "I managed rollout across 120 locations for critical services. " + " ".join(["body"] * 52),
                    *cl_response_with_counts([60] * 4)["body_paragraphs"],
                ],
            },
            {
                **cl_response_with_counts([60] * 5),
                "body_paragraphs": [
                    "I managed rollout across 120+ locations for critical services. " + " ".join(["body"] * 52),
                    *cl_response_with_counts([60] * 4)["body_paragraphs"],
                ],
            },
        ]
    )
    gen = CoverLetterGenerator(client)

    result = await gen.generate(JD_ANALYSIS, TAILORED_CV_WITH_120_PLUS, PERSONAL)

    assert client.complete_json.call_count == 2
    assert result.validation_status == "repaired"
    repair_prompt = client.complete_json.call_args_list[1].args[1]
    assert "120+" in repair_prompt
    assert "120" in repair_prompt


@pytest.mark.asyncio
async def test_unsupported_numeric_token_returns_review_required_after_failed_repair():
    client = MagicMock()
    client.complete_json = AsyncMock(
        side_effect=[
            {
                **cl_response_with_counts([60] * 5),
                "body_paragraphs": [
                    "I improved platform reliability by 99%. " + " ".join(["body"] * 54),
                    *cl_response_with_counts([60] * 4)["body_paragraphs"],
                ],
            },
            {
                **cl_response_with_counts([60] * 5),
                "body_paragraphs": [
                    "I improved platform reliability by 99%. " + " ".join(["body"] * 54),
                    *cl_response_with_counts([60] * 4)["body_paragraphs"],
                ],
            },
        ]
    )
    gen = CoverLetterGenerator(client)

    result = await gen.generate(JD_ANALYSIS, TAILORED_CV, PERSONAL)

    assert client.complete_json.call_count == 2
    assert result.validation_status == "review_required"
    assert any("unsupported numeric token '99%'" in issue for issue in result.validation_issues)


@pytest.mark.asyncio
async def test_job_description_numeric_token_is_allowed_as_employer_context():
    client = make_mock_client(
        {
            **cl_response_with_counts([60] * 5),
            "body_paragraphs": [
                "Your programme spans 40 locations and needs pragmatic delivery leadership. "
                + " ".join(["body"] * 51),
                *cl_response_with_counts([60] * 4)["body_paragraphs"],
            ],
        }
    )
    gen = CoverLetterGenerator(client)

    result = await gen.generate(
        JD_ANALYSIS,
        TAILORED_CV,
        PERSONAL,
        jd_text="The role supports a programme spanning 40 locations.",
    )

    assert client.complete_json.call_count == 1
    assert result.validation_status == "passed"
    assert result.validation_issues == []


@pytest.mark.asyncio
async def test_unknown_content_plan_id_blocks_before_generation():
    class InvalidPlanGenerator(CoverLetterGenerator):
        def create_content_plan(self, stage_input):
            del stage_input
            return CoverLetterContentPlan(
                opening_evidence_ids=("unknown-evidence",),
                primary_evidence_ids=(),
                secondary_evidence_ids=(),
                alignment_job_requirement_ids=(),
            )

    client = make_mock_client(cl_response_with_counts([60] * 5))
    gen = InvalidPlanGenerator(client)

    result = await gen.generate(JD_ANALYSIS, TAILORED_CV, PERSONAL)

    client.complete_json.assert_not_called()
    assert result.validation_status == "review_required"
    assert any("unknown evidence ID" in issue for issue in result.validation_issues)
    assert result.generation_provenance is not None
    assert result.generation_provenance.workflow["attempts"] == []


@pytest.mark.asyncio
async def test_workflow_diagnostics_record_attempts_without_document_content():
    class Observation:
        prompt_tokens = 123
        completion_tokens = 45
        duration_ms = 67.0

    client = make_mock_client(cl_response_with_counts([60] * 5))
    client.spec = MagicMock(id="benchmark-model")
    client.observations = [Observation()]
    gen = CoverLetterGenerator(client)

    result = await gen.generate(JD_ANALYSIS, TAILORED_CV, PERSONAL)

    workflow = result.generation_provenance.workflow
    serialized = __import__("json").dumps(workflow)
    assert workflow["skill_id"] == "cover-letter"
    assert workflow["skill_version"] == "1.0.0"
    assert workflow["model_id"] == "benchmark-model"
    assert workflow["attempts"][0]["attempt_number"] == 1
    assert workflow["attempts"][0]["input_tokens"] == 123
    assert workflow["attempts"][0]["output_tokens"] == 45
    assert workflow["attempts"][0]["computed_body_count"] == 300
    assert workflow["final_state"] == "passed"
    assert "private evidence text" not in serialized
    assert "body body body" not in serialized
    assert PERSONAL["email"] not in serialized
