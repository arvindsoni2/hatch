"""Contract coverage for coach prompt templates."""
from __future__ import annotations

from app.prompts import render_prompt
from app.services.prompt_catalog import prompt_contract_block


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
