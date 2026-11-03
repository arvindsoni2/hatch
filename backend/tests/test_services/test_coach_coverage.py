from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.application import Application
from app.models.coach_readiness import CoachCompetencyOverride
from app.models.job import JobPosting
from app.models.job_score import JobScore
from app.models.story import Story
from app.services.coach_readiness import coverage

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "coach_coverage" / "pairs.json"
)


def _competency(
    text: str = "budget ownership",
) -> coverage.Competency:
    return coverage.Competency(text=text, match_key=coverage.match_key(text))


def _story(
    *,
    story_id: str = "story-1",
    tags: list[str] | None = None,
    skills: list[str] | None = None,
    title: str = "Budget story",
    result: str | None = "Cut spend by 18 percent.",
    metrics: dict | None = None,
    strength_score: float = 5.0,
    is_active: bool = True,
) -> Story:
    return Story(
        id=story_id,
        title=title,
        slug=story_id,
        tags=tags,
        skills=skills,
        result=result,
        metrics=metrics,
        strength_score=strength_score,
        is_active=is_active,
    )


async def _seed_application(
    db: AsyncSession,
    *,
    app_id: str = "app-1",
    job_id: str = "job-1",
    status: str = "interview",
    misses: list[str] | None = None,
    matches: list[str] | None = None,
    skills: list[str] | None = None,
) -> None:
    db.add(
        JobPosting(
            id=job_id,
            title="Delivery Lead",
            company="Synthetic Co",
            url=f"https://example.test/{job_id}",
            source="synthetic",
            skills=skills or [],
        )
    )
    db.add(
        JobScore(
            job_id=job_id,
            overall_score=0.5,
            keyword_misses=misses or [],
            keyword_matches=matches or [],
        )
    )
    db.add(
        Application(
            id=app_id,
            job_id=job_id,
            status=status,
            priority="normal",
        )
    )
    await db.flush()


def test_competency_order_misses_then_matches_then_skills() -> None:
    items = coverage.competency_list(
        keyword_misses=["Budget ownership", "budget  ownership"],
        keyword_matches=["Stakeholder management"],
        skills=["Python", "Budget Ownership"],
    )
    assert [item.text for item in items] == [
        "Budget ownership",
        "Stakeholder management",
        "Python",
    ]

    capped = coverage.competency_list(
        keyword_misses=[],
        keyword_matches=[],
        skills=[f"skill {index}" for index in range(20)],
    )
    assert len(capped) == 12


def test_match_key_never_shown_original_text_kept() -> None:
    items = coverage.competency_list(
        keyword_misses=["Process"],
        keyword_matches=["process"],
        skills=[],
    )

    assert len(items) == 1
    assert items[0].text == "Process"
    assert items[0].match_key == "process"


def test_stopwords_copy_matches_benchmark_list() -> None:
    benchmark = (
        Path(__file__).resolve().parents[2]
        / "benchmarks"
        / "coach"
        / "fixtures"
        / "stopwords_en.txt"
    )
    copied = Path(coverage.__file__).with_name("stopwords_en.txt")

    assert copied.read_text(encoding="utf-8") == benchmark.read_text(encoding="utf-8")


def test_containment_one_word_competency_in_tags_scores_one() -> None:
    result = coverage.build_coverage(
        application_id="app-1",
        competencies=(_competency("python"),),
        stories=[_story(tags=["python"], result="Delivered a service.")],
        overrides={},
        covered_min=0.67,
        thin_min=0.34,
    )

    assert result.competencies[0].stories[0].score == 1.0
    assert result.competencies[0].status == "covered"


def test_story_without_result_is_never_covered() -> None:
    result = coverage.build_coverage(
        application_id="app-1",
        competencies=(_competency("budget ownership"),),
        stories=[_story(tags=["budget", "ownership"], result=None)],
        overrides={},
        covered_min=0.67,
        thin_min=0.34,
    )

    assert result.competencies[0].status == "thin"
    assert result.competencies[0].action == "strengthen"


@pytest.mark.asyncio
async def test_inactive_story_never_counts(db_session: AsyncSession) -> None:
    await _seed_application(db_session, misses=["Budget ownership"])
    db_session.add_all(
        [
            _story(story_id="active", tags=["budget", "ownership"]),
            _story(story_id="inactive", tags=["budget", "ownership"], is_active=False),
        ]
    )
    await db_session.flush()

    result = await coverage.coverage_for_application(db_session, "app-1")

    assert result is not None
    assert [item.story_id for item in result.competencies[0].stories] == ["active"]


def test_has_metric_is_information_only() -> None:
    competency = (_competency("budget ownership"),)
    without_metric = coverage.build_coverage(
        application_id="app-1",
        competencies=competency,
        stories=[_story(tags=["budget", "ownership"], metrics=None)],
        overrides={},
        covered_min=0.67,
        thin_min=0.34,
    )
    with_metric = coverage.build_coverage(
        application_id="app-1",
        competencies=competency,
        stories=[_story(tags=["budget", "ownership"], metrics={"saving": 18})],
        overrides={},
        covered_min=0.67,
        thin_min=0.34,
    )

    assert without_metric.competencies[0].status == "covered"
    assert with_metric.competencies[0].status == "covered"
    assert without_metric.competencies[0].stories[0].has_metric is False
    assert with_metric.competencies[0].stories[0].has_metric is True


@pytest.mark.asyncio
async def test_thresholds_come_from_config(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_application(db_session, misses=["budget ownership"])
    db_session.add(_story(tags=["budget"]))
    await db_session.flush()

    monkeypatch.setattr(settings, "HATCH_COACH_COVERAGE_COVERED_MIN", 0.4)
    covered = await coverage.coverage_for_application(db_session, "app-1")
    monkeypatch.setattr(settings, "HATCH_COACH_COVERAGE_COVERED_MIN", 0.6)
    thin = await coverage.coverage_for_application(db_session, "app-1")

    assert covered is not None and covered.competencies[0].status == "covered"
    assert thin is not None and thin.competencies[0].status == "thin"


@pytest.mark.asyncio
async def test_overrides_rename_and_hide(db_session: AsyncSession) -> None:
    await _seed_application(
        db_session,
        misses=["Budget Ownership", "Stakeholder management"],
    )
    db_session.add_all(
        [
            CoachCompetencyOverride(
                application_id="app-1",
                original="budget ownership",
                replacement="Budget accountability",
            ),
            CoachCompetencyOverride(
                application_id="app-1",
                original="Stakeholder Management",
                hidden=True,
            ),
        ]
    )
    await db_session.flush()

    result = await coverage.coverage_for_application(db_session, "app-1")

    assert result is not None
    assert [item.competency for item in result.competencies] == [
        "Budget accountability"
    ]


@pytest.mark.asyncio
async def test_overview_counts_gaps_across_interview_applications(
    db_session: AsyncSession,
) -> None:
    await _seed_application(
        db_session, app_id="app-1", job_id="job-1", misses=["Budget ownership"]
    )
    await _seed_application(
        db_session, app_id="app-2", job_id="job-2", misses=["Budget Ownership"]
    )
    await _seed_application(
        db_session,
        app_id="app-3",
        job_id="job-3",
        status="applied",
        misses=["Budget ownership"],
    )
    await db_session.flush()

    overview = await coverage.coverage_overview(db_session)

    assert overview.gaps == (
        coverage.CoverageGap(competency="Budget ownership", application_count=2),
    )


def test_calibration_fixtures_match_hand_labels() -> None:
    pairs = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    matched = 0
    total = 0
    for pair in pairs:
        items = coverage.competency_list(
            keyword_misses=pair["keyword_misses"],
            keyword_matches=pair["keyword_matches"],
            skills=pair["skills"],
        )
        stories = [
            _story(
                story_id=story["story_id"],
                tags=story.get("tags"),
                skills=story.get("skills"),
                result=story.get("result"),
                metrics=story.get("metrics"),
            )
            for story in pair["stories"]
        ]
        result = coverage.build_coverage(
            application_id=pair["pair_id"],
            competencies=items,
            stories=stories,
            overrides={},
            covered_min=0.67,
            thin_min=0.34,
        )
        observed = [item.status for item in result.competencies]
        total += len(observed)
        matched += sum(
            actual == expected
            for actual, expected in zip(observed, pair["expected_statuses"])
        )

    assert total == 20
    assert matched == total
