"""Product reads resolve canonical scoring content without enriching stored events."""

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.scorer_agent import ScorerAgent
from app.agents.tools.event_bus import EventBus
from app.config import settings
from app.models.agent_event import AgentEvent
from app.runtime import RuntimeMode
from app.runtime.storage.sqlite import SQLiteRuntimeUnitOfWorkFactory
from job_score_test_support import install_profile, install_provider, job, profile


@pytest.mark.parametrize(
    "view", ["decisions", "activity", "skill-gaps", "skill-frequency", "list", "detail"]
)
@pytest.mark.parametrize("valid_reference", [True, False])
async def test_product_reads_score_reference_without_rewriting_event_payload(
    db_session, client, monkeypatch, view, valid_reference
):
    rationale = "Synthetic canonical scoring rationale"
    install_profile(monkeypatch, profile("llm"))
    install_provider(
        monkeypatch,
        [
            {
                "skill_match": 0.8,
                "experience_match": 0.8,
                "rate_match": 0.8,
                "location_match": 0.8,
                "overall_score": 0.8,
                "reasoning": rationale,
                "fit_reasoning": "Synthetic fit explanation",
                "strengths": ["Synthetic strength"],
                "score_gaps": ["Synthetic gap"],
                "keyword_matches": ["AWS"],
                "keyword_misses": ["Kubernetes"],
            }
        ],
    )
    monkeypatch.setattr(settings, "HATCH_RUNTIME_JOB_SCORE_MODE", RuntimeMode.NEW)
    factory = SQLiteRuntimeUnitOfWorkFactory(
        async_sessionmaker(
            bind=db_session.bind,
            expire_on_commit=False,
        )
    )
    scorer = ScorerAgent(runtime_factory=factory)
    scorer._bus = EventBus()
    posting = job()
    db_session.add(posting)
    await db_session.commit()
    await scorer._bus.emit(
        "job_discovered", "scout", {"job_id": posting.id}, db_session
    )
    assert await scorer.run(db_session) == {"scored": 1, "skipped": 0, "errors": 0}
    scored = await db_session.scalar(
        select(AgentEvent).where(AgentEvent.event_type == "job_scored")
    )
    if not valid_reference:
        # A score ID alone cannot authorize cross-job content resolution.
        unrelated = job()
        db_session.add(unrelated)
        await db_session.commit()
        payload = json.loads(scored.payload)
        payload["job_id"] = unrelated.id
        scored.payload = json.dumps(payload)
        await db_session.commit()
        posting = unrelated
    before = scored.payload
    paths = {
        "decisions": f"/api/jobs/{posting.id}/decisions",
        "activity": "/api/events/activity",
        "skill-gaps": "/api/analytics/skill-gaps",
        "skill-frequency": "/api/analytics/skill-frequency",
        "list": "/api/events?event_type=job_scored",
        "detail": f"/api/events/{scored.id}",
    }
    response = await client.get(paths[view])
    assert response.status_code == 200
    data = response.json()
    if view == "decisions":
        step = next(row for row in data["steps"] if row["event_type"] == "job_scored")
        assert step["reasoning"] == (rationale if valid_reference else None)
    elif view == "activity":
        activity = next(
            row for row in data["items"] if row["event_type"] == "job_scored"
        )
        assert activity["detail"] == (rationale if valid_reference else None)
    elif view in {"list", "detail"}:
        result = data["items"][0] if view == "list" else data
        payload = json.loads(result["payload"])
        assert payload["score"] == 0.8
        assert payload["scoring_method"] == "llm"
        assert payload["score_ref"] == json.loads(before)["score_ref"]
        content = {
            "reasoning": rationale,
            "fit_reasoning": "Synthetic fit explanation",
            "strengths": ["Synthetic strength"],
            "score_gaps": ["Synthetic gap"],
            "keyword_matches": ["AWS"],
            "keyword_misses": ["Kubernetes"],
        }
        if valid_reference:
            for field, expected in content.items():
                assert payload[field] == expected
        else:
            assert not payload.keys() & content.keys()
    else:
        expected = {("kubernetes", 1)} if valid_reference else set()
        if view == "skill-frequency" and valid_reference:
            expected.add(("aws", 1))
        assert {(row["skill"], row["count"]) for row in data["skills"]} == expected
    await db_session.commit()
    await db_session.refresh(scored)
    assert scored.payload == before
    assert rationale not in scored.payload
    assert "Kubernetes" not in scored.payload


@pytest.mark.parametrize("view", ["list", "detail"])
async def test_event_api_keeps_legacy_inline_payload_byte_for_byte(
    db_session, client, view
):
    payload = '{ "job_id": "legacy-job", "score": 0.8, "reasoning": "Synthetic legacy narrative" }'
    event = AgentEvent(
        event_type="job_scored",
        source_agent="scorer",
        payload=payload,
        status="pending",
    )
    db_session.add(event)
    await db_session.commit()
    path = "/api/events" if view == "list" else f"/api/events/{event.id}"
    response = await client.get(path)
    assert response.status_code == 200
    result = response.json()["items"][0] if view == "list" else response.json()
    assert result["payload"] == payload
    await db_session.commit()
    await db_session.refresh(event)
    assert event.payload == payload
