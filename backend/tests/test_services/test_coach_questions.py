from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.coach_session import InterviewSession, SessionQuestion
from app.models.question_bank import QuestionBankItem
from app.services.coach_readiness.questions import likely_questions


@pytest.mark.asyncio
async def test_likely_questions_order_and_archived_excluded(
    db_session: AsyncSession,
) -> None:
    db_session.add(Application(id="app-1", status="interview", priority="normal"))
    db_session.add(
        InterviewSession(
            id="session-1",
            application_id="app-1",
            company_name="Synthetic Ltd",
            role_title="Delivery Lead",
            config={},
            experience_version="conversational_v1",
            status="active",
            conversation_state="asking",
            compatibility_key="synthetic-key",
            session_plan_json={"role": {"role_family": "delivery"}},
        )
    )
    db_session.add_all(
        [
            QuestionBankItem(
                id="qb-linked",
                type="interview_question",
                question="Linked question?",
                title="Linked",
                answer_draft="",
                linked_applications=["app-1"],
                updated_at=datetime(2026, 11, 3, 10, 0),
            ),
            QuestionBankItem(
                id="qb-role",
                type="interview_question",
                question="Role family question?",
                title="Role",
                answer_draft="",
                role_family="delivery",
                updated_at=datetime(2026, 11, 3, 11, 0),
            ),
            QuestionBankItem(
                id="qb-archived",
                type="interview_question",
                question="Archived question?",
                title="Archived",
                answer_draft="",
                linked_applications=["app-1"],
                archived_at=datetime(2026, 11, 3, 12, 0),
                updated_at=datetime(2026, 11, 3, 12, 0),
            ),
            SessionQuestion(
                id="sq-1",
                session_id="session-1",
                question_num=1,
                text="Session plan question?",
                category="Behavioural",
                order_in_session=1,
            ),
        ]
    )
    await db_session.flush()

    questions = await likely_questions(db_session, "app-1")

    assert [item.text for item in questions] == [
        "Linked question?",
        "Role family question?",
        "Session plan question?",
    ]
    assert questions[0].source_ref == {
        "kind": "question_bank_item",
        "id": "qb-linked",
    }
