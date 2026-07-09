from __future__ import annotations

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.coach_session import InterviewSession, SessionQuestion
from app.models.job import JobPosting


def _question_bank_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": "interview_question",
        "title": "Tell me about a complex migration",
        "question": "Tell me about a complex migration you led.",
        "answer_draft": "I led a phased cloud migration across regulated workloads.",
        "situation": "A regulated client had ageing infrastructure.",
        "task": "Create a safe migration route.",
        "action": "I split workloads into waves and aligned stakeholders.",
        "result": "The team migrated the first wave without customer impact.",
        "skills": ["cloud architecture", "stakeholder management"],
        "tags": ["migration", "leadership"],
        "seniority": "senior",
        "role_family": "solutions_architect",
        "source": "manual",
        "confidence": "draft",
    }
    payload.update(overrides)
    return payload


async def _application(db_session: AsyncSession) -> Application:
    job = JobPosting(
        title="Solutions Architect",
        company="Example Cloud",
        location="London",
        url="https://example.com/jobs/question-bank",
        source="manual",
        scraped_at=datetime.utcnow(),
    )
    app = Application(job_id=job.id, status="interview", priority="normal")
    db_session.add_all([job, app])
    await db_session.commit()
    await db_session.refresh(app)
    return app


@pytest.mark.asyncio
async def test_question_bank_crud_search_filter_and_delete(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    app = await _application(db_session)

    create_response = await client.post(
        "/api/question-bank",
        json=_question_bank_payload(linked_applications=[app.id]),
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["title"] == "Tell me about a complex migration"
    assert created["linked_applications"] == [app.id]
    assert created["skills"] == ["cloud architecture", "stakeholder management"]

    await client.post(
        "/api/question-bank",
        json=_question_bank_payload(
            type="proof_point",
            title="Reduced handover time",
            question=None,
            answer_draft="Reduced handover time by 30%.",
            skills=["delivery"],
            tags=["metrics"],
            confidence="reviewed",
        ),
    )

    list_response = await client.get("/api/question-bank?search=migration&tag=leadership&type=interview_question")
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == created["id"]

    update_response = await client.patch(
        f"/api/question-bank/{created['id']}",
        json={"confidence": "final", "tags": ["migration", "leadership", "cloud"]},
    )
    assert update_response.status_code == 200
    assert update_response.json()["confidence"] == "final"
    assert update_response.json()["tags"] == ["migration", "leadership", "cloud"]

    delete_response = await client.delete(f"/api/question-bank/{created['id']}")
    assert delete_response.status_code == 204
    assert (await client.get("/api/question-bank")).json()["total"] == 1


@pytest.mark.asyncio
async def test_question_bank_save_from_interview_answer(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    app = await _application(db_session)
    session = InterviewSession(
        application_id=app.id,
        company_name="Example Cloud",
        role_title="Solutions Architect",
        status="active",
    )
    question = SessionQuestion(
        session=session,
        question_num=1,
        text="Describe a time you influenced senior stakeholders.",
        category="Behavioural",
        difficulty="medium",
        order_in_session=1,
    )
    db_session.add_all([session, question])
    await db_session.commit()
    await db_session.refresh(session)
    await db_session.refresh(question)

    response = await client.post(
        "/api/question-bank/from-interview-answer",
        json={
            "session_id": session.id,
            "question_id": question.id,
            "answer_draft": "I aligned the CFO, CTO, and delivery leads around a staged plan.",
            "title": "Influenced senior stakeholders on staged migration",
            "tags": ["stakeholders"],
            "skills": ["executive communication"],
            "confidence": "reviewed",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "interview_prep"
    assert body["question"] == question.text
    assert body["linked_applications"] == [app.id]
    assert body["source_session_id"] == session.id
    assert body["source_question_id"] == question.id
    assert body["answer_draft"].startswith("I aligned the CFO")
