"""Real offline deterministic conformance; never a provider promotion gate."""

import json
import time
from collections import Counter

from sqlalchemy import select

from app.agents.scorer_agent import ScorerAgent
from app.agents.tools.event_bus import EventBus
from app.config import settings
from app.models.job_score import JobScore
from app.runtime import RuntimeMode
from app.runtime_bindings.migration.scoring import score_output
from app.schemas.profile import Profile
from job_score_test_support import job


def test_percentiles_use_nearest_rank_not_mean_or_max():
    from job_score_benchmark_support import percentile

    assert percentile(list(range(1, 21)), 50) == 10
    assert percentile(list(range(1, 21)), 95) == 19
    assert percentile([1, 2, 3, 4, 100], 50) == 3


async def test_r2_offline_conformance_executes_fifty_labelled_inputs(
    workflow_runtime, runtime_fixture, monkeypatch
):
    from job_score_benchmark_support import summarize

    cases = runtime_fixture("job_score_r2_cases.json")
    assert Counter(case["cohort"] for case in cases) == {
        "strong_fit": 20,
        "borderline": 15,
        "poor_fit": 15,
    }
    assert len({case["job"]["description"] for case in cases}) == 50
    _, factory = workflow_runtime
    measured = []
    for case in cases:
        candidate = Profile.model_validate(case["profile"])
        monkeypatch.setattr("app.agents.scorer_agent.load_profile", lambda: candidate)
        monkeypatch.setattr(
            "app.agents.tools.profile_loader.load_profile", lambda: candidate
        )
        monkeypatch.setattr(
            "app.services.resume_store.get_resume_text", lambda: case["resume"]
        )
        row = {
            "id": case["id"],
            "expected_shortlist": case["expected_shortlist"],
            "cohort": case["cohort"],
        }
        for mode in (RuntimeMode.LEGACY, RuntimeMode.NEW):
            monkeypatch.setattr(settings, "HATCH_RUNTIME_JOB_SCORE_MODE", mode)
            scorer = ScorerAgent(runtime_factory=factory)
            scorer._bus = EventBus()
            async with factory.session_factory() as session:
                posting = job(**case["job"])
                session.add(posting)
                await session.commit()
                await scorer._bus.emit(
                    "job_discovered", "scout", {"job_id": posting.id}, session
                )
                started = time.perf_counter()
                outcome = await scorer.run(session)
                row[f"{mode.value}_latency_ms"] = (time.perf_counter() - started) * 1000
                assert outcome == {"scored": 1, "skipped": 0, "errors": 0}, case["id"]
                durable = await session.scalar(
                    select(JobScore).where(JobScore.job_id == posting.id)
                )
                score = score_output(durable)
                row[f"{mode.value}_score"] = score.overall_score
                row[f"{mode.value}_shortlist"] = (
                    score.overall_score >= candidate.scoring.shortlist_threshold
                )
                if case["cohort"] == "borderline":
                    assert (
                        abs(score.overall_score - candidate.scoring.shortlist_threshold)
                        <= 0.1001
                    )
        measured.append(row)
    report = summarize(measured)
    print("R5_OFFLINE_MEASUREMENTS=" + json.dumps(report, sort_keys=True))
    assert report["legacy_accuracy"] >= 0.92
    assert report["new_accuracy"] >= 0.92
    assert report["new_accuracy"] >= report["legacy_accuracy"] - 0.02
    assert report["shortlist_agreement"] >= 0.95
    assert report["delta_within_tolerance"] >= 0.90
    assert report["provider_gate_completed"] is False
