"""Contract coverage for coach prompt templates."""
from __future__ import annotations

from app.prompts import render_prompt
from app.services.prompt_catalog import prompt_contract_block


def test_question_repair_template_renders_targeted_contract_metadata() -> None:
    rendered = render_prompt(
        "question_generation_repair.j2",
        prompt_contract=prompt_contract_block("question_generation_repair"),
        additional_count=2,
        allowed_categories=["Technical", "Behavioural"],
        allowed_requirement_ids=["requirement-123"],
        findings=["coach_question_count_mismatch"],
        retained_question_hashes=["abc123"],
        role_title="Engineer",
        company_name="Example",
        company_research={},
        jd_text="Build systems",
        candidate_summary="Candidate",
        difficulty="medium",
    )

    assert '"prompt_id": "question_generation_repair"' in rendered
    assert '"prompt_version": "1.0.0"' in rendered
    assert "exactly 2 additional" in rendered
    assert "requirement-123" in rendered
    assert "abc123" in rendered


def test_all_coach_templates_render_metadata_and_claim_layers() -> None:
    cases = {
        "answer_evaluation.j2": {
            "prompt_id": "answer_evaluation",
            "question": "Question",
            "category": "Technical",
            "transcript": "Answer",
            "speech_metrics": {},
            "model_answer": "",
        },
        "follow_up.j2": {
            "prompt_id": "follow_up_question",
            "original_question": "Question",
            "transcript": "Answer",
            "weak_dimension": "relevance",
        },
        "session_report.j2": {
            "prompt_id": "session_report",
            "candidate_name": "Candidate",
            "role_title": "Role",
            "company_name": "Company",
            "session_date": "17 July 2026",
            "answered_count": 1,
            "total_questions": 1,
            "overall_score": 5,
            "category_scores": {},
            "question_summaries": [],
            "speech_summary": {},
        },
        "speech_feedback.j2": {
            "prompt_id": "speech_feedback",
            "speech_metrics": {},
            "transcript": "Answer",
        },
        "video_feedback.j2": {
            "prompt_id": "video_feedback",
            "video_metrics": {},
        },
    }

    for template, values in cases.items():
        prompt_id = values.pop("prompt_id")
        rendered = render_prompt(
            template,
            prompt_contract=prompt_contract_block(prompt_id),
            **values,
        )
        assert f'"prompt_id": "{prompt_id}"' in rendered
        assert "OBSERVATION" in rendered
        assert "INTERPRETATION" in rendered
        assert "RECOMMENDATION" in rendered
