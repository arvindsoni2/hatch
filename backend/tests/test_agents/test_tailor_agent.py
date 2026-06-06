"""Tests for TailorAgent CV/cover letter generation flow."""
from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.job import JobPosting


def _insert_job(db_session, job_id: str) -> JobPosting:
    job = JobPosting(
        id=job_id,
        title="Senior Cloud Architect",
        company="FinTech Ltd",
        location="London, UK",
        rate_text="£700/day",
        rate_min=700.0,
        rate_max=700.0,
        currency="GBP",
        ir35_status="outside",
        description="Senior cloud architect role. Outside IR35. AWS, Terraform required.",
        url=f"https://example.com/{job_id}",
        source="reed",
        scraped_at=datetime.utcnow(),
        is_active=True,
        sync_status="pending",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    return job


def _make_shortlisted_event(job_id: str, score: float = 0.90) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "event_type": "job_shortlisted",
        "source_agent": "supervisor",
        "payload": {"job_id": job_id, "score": score},
        "created_at": "2025-01-01T00:00:00",
    }


class TestTailorAgent:

    async def test_run_generates_cv_and_cl_for_shortlisted_job(self, db_session):
        """TailorAgent calls generate_all for a shortlisted job above threshold."""
        job_id = str(uuid.uuid4())
        db_session.add(_insert_job(db_session, job_id))
        await db_session.commit()

        event = _make_shortlisted_event(job_id, score=0.90)
        mock_bus = AsyncMock()
        mock_bus.poll = AsyncMock(return_value=[event])
        mock_bus.emit = AsyncMock(return_value="evt-id")
        mock_bus.mark_processing = AsyncMock()
        mock_bus.mark_completed = AsyncMock()
        mock_bus.mark_failed = AsyncMock()

        mock_bundle = MagicMock()
        mock_bundle.cv_document_id = "cv-doc-1"
        mock_bundle.cl_document_id = "cl-doc-1"
        mock_bundle.ats_score = MagicMock(overall_score=0.82)

        mock_tailor_service = AsyncMock()
        mock_tailor_service.generate_all = AsyncMock(return_value=mock_bundle)

        mock_profile = MagicMock()
        mock_profile.scoring.shortlist_threshold = 0.75
        mock_profile.llm.primary_model = "claude-sonnet-4-6"

        with patch("app.agents.tailor_agent.TailorService", return_value=mock_tailor_service), \
             patch("app.agents.tailor_agent.load_profile", return_value=mock_profile), \
             patch("app.agents.tailor_agent.EventBus") as MockEB:
            MockEB.instance.return_value = mock_bus

            from app.agents.tailor_agent import TailorAgent
            agent = TailorAgent()
            agent._bus = mock_bus
            agent._tailor = mock_tailor_service

            result = await agent.run(db_session)

        mock_tailor_service.generate_all.assert_called_once()
        assert result["tailored"] == 1
        assert result["errors"] == 0

    async def test_run_skips_job_below_threshold(self, db_session):
        """TailorAgent skips generation if payload score < shortlist_threshold."""
        job_id = str(uuid.uuid4())
        db_session.add(_insert_job(db_session, job_id))
        await db_session.commit()

        # Score below threshold — should be skipped (no generate_all call)
        event = _make_shortlisted_event(job_id, score=0.50)
        mock_bus = AsyncMock()
        mock_bus.poll = AsyncMock(return_value=[event])
        mock_bus.emit = AsyncMock(return_value="evt-id")
        mock_bus.mark_processing = AsyncMock()
        mock_bus.mark_completed = AsyncMock()
        mock_bus.mark_failed = AsyncMock()

        mock_tailor_service = AsyncMock()
        mock_tailor_service.generate_all = AsyncMock()

        mock_profile = MagicMock()
        mock_profile.scoring.shortlist_threshold = 0.75
        mock_profile.llm.primary_model = "claude-sonnet-4-6"

        with patch("app.agents.tailor_agent.TailorService", return_value=mock_tailor_service), \
             patch("app.agents.tailor_agent.load_profile", return_value=mock_profile), \
             patch("app.agents.tailor_agent.EventBus") as MockEB:
            MockEB.instance.return_value = mock_bus

            from app.agents.tailor_agent import TailorAgent
            agent = TailorAgent()
            agent._bus = mock_bus
            agent._tailor = mock_tailor_service

            result = await agent.run(db_session)

        mock_tailor_service.generate_all.assert_not_called()
        # The event is still processed (tailored=1 counts it), but generate_all was skipped
        assert result["errors"] == 0

    async def test_run_emits_cv_tailored_event(self, db_session):
        """After tailoring, a cv_tailored event is emitted with job_id and document IDs."""
        job_id = str(uuid.uuid4())
        db_session.add(_insert_job(db_session, job_id))
        await db_session.commit()

        event = _make_shortlisted_event(job_id, score=0.90)
        mock_bus = AsyncMock()
        mock_bus.poll = AsyncMock(return_value=[event])
        mock_bus.emit = AsyncMock(return_value="evt-id")
        mock_bus.mark_processing = AsyncMock()
        mock_bus.mark_completed = AsyncMock()
        mock_bus.mark_failed = AsyncMock()

        mock_bundle = MagicMock()
        mock_bundle.cv_document_id = "cv-doc-2"
        mock_bundle.cl_document_id = "cl-doc-2"
        mock_bundle.ats_score = MagicMock(overall_score=0.85)

        mock_tailor_service = AsyncMock()
        mock_tailor_service.generate_all = AsyncMock(return_value=mock_bundle)

        mock_profile = MagicMock()
        mock_profile.scoring.shortlist_threshold = 0.75
        mock_profile.llm.primary_model = "claude-sonnet-4-6"

        with patch("app.agents.tailor_agent.TailorService", return_value=mock_tailor_service), \
             patch("app.agents.tailor_agent.load_profile", return_value=mock_profile), \
             patch("app.agents.tailor_agent.EventBus") as MockEB:
            MockEB.instance.return_value = mock_bus

            from app.agents.tailor_agent import TailorAgent
            agent = TailorAgent()
            agent._bus = mock_bus
            agent._tailor = mock_tailor_service

            await agent.run(db_session)

        emitted_types = [c.kwargs.get("event_type") or c.args[0] for c in mock_bus.emit.call_args_list]
        assert "cv_tailored" in emitted_types

        cv_call = next(c for c in mock_bus.emit.call_args_list
                       if (c.kwargs.get("event_type") or c.args[0]) == "cv_tailored")
        payload = cv_call.kwargs.get("payload") or cv_call.args[2]
        assert payload["job_id"] == job_id
        assert payload["cv_document_id"] == "cv-doc-2"
