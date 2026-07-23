from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.agents.tools import perception_factory, profile_loader
from app.routers import coach as coach_router


@pytest.mark.asyncio
async def test_audio_preprocessing_is_inside_single_answer_workflow(
    monkeypatch,
) -> None:
    hierarchy: list[tuple[str, str | None]] = []
    stack: list[str] = []

    class Telemetry:
        @contextmanager
        def workflow_span(self, workflow, attributes=None):
            del attributes
            name = f"workflow:{workflow}"
            hierarchy.append((name, stack[-1] if stack else None))
            stack.append(name)
            try:
                yield SimpleNamespace()
            finally:
                stack.pop()

        @contextmanager
        def coach_stage_span(self, stage, attributes=None):
            del attributes
            hierarchy.append((stage, stack[-1] if stack else None))
            stack.append(stage)
            try:
                yield SimpleNamespace()
            finally:
                stack.pop()

    class Transcriber:
        def transcribe(self, _path):
            return SimpleNamespace(
                text="A concise answer",
                words=[SimpleNamespace(w="A", start=0.0, end=0.2)],
            )

    class Service:
        async def _submit_answer_impl(self, *_args, **_kwargs):
            hierarchy.append(("answer:implementation", stack[-1]))
            return SimpleNamespace(evaluation_state="completed")

    monkeypatch.setattr(coach_router, "get_telemetry", lambda: Telemetry())
    monkeypatch.setattr(coach_router, "CoachService", Service)
    monkeypatch.setattr(perception_factory, "get_transcriber", lambda: Transcriber())
    monkeypatch.setattr(
        profile_loader,
        "load_profile",
        lambda: SimpleNamespace(locale="en-GB"),
    )

    await coach_router._evaluate_audio_attempt(
        session_id="session-1",
        question_id="question-1",
        recording_id="recording-1",
        job_id="job-1",
        audio_path="relative.wav",
        face_summary=None,
        job_db=object(),
    )

    assert hierarchy == [
        ("workflow:coach_generation", None),
        ("coach.answer.submit", "workflow:coach_generation"),
        ("coach.audio.persist", "coach.answer.submit"),
        ("coach.transcription", "coach.answer.submit"),
        ("answer:implementation", "coach.answer.submit"),
    ]
