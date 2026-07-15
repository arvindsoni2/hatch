from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from app.schemas.tailor import (
    ATSKeywords,
    CompanyContext,
    CoverLetterResult,
    JDAnalysisResult,
    Requirements,
    TailoredCVResult,
    TailoredEducation,
    TailoredExperience,
)
from benchmarks.contracts import BenchmarkCase, ExpectedFacts, ModelSpec, RoleFact
from benchmarks.scoring import score_pair


@pytest.fixture
def benchmark_case() -> BenchmarkCase:
    source_bullet = (
        "Led a cross-functional Scrum delivery team and managed the product backlog "
        "through planning, review, and retrospective ceremonies."
    )
    master = {
        "personal": {"full_name": "Alex Example"},
        "summary_variants": {
            "delivery": "Delivery Manager experienced in Scrum, Kanban, coaching, and hybrid delivery."
        },
        "skills": {
            "delivery": {
                "category": "Delivery & Leadership",
                "items": ["Scrum", "Kanban", "Product backlog", "Coaching"],
            }
        },
        "experience": [
            {
                "role": "Delivery Manager",
                "company": "Example Ltd",
                "period": "2020 - Present",
                "achievements": [{"text": source_bullet}],
            }
        ],
        "education": [
            {
                "qualification": "BSc Computing",
                "institution": "Example University",
                "year": "2010",
            }
        ],
        "certifications": ["PSM I"],
    }
    return BenchmarkCase(
        case_id="synthetic-delivery",
        source_dir=Path("/tmp/synthetic-delivery"),
        master_cv=master,
        job_description="Delivery Manager requiring Scrum, Kanban, coaching, and backlog management.",
        jd_analysis=JDAnalysisResult(
            role_title="Delivery Manager",
            requirements=Requirements(
                must_have=["Scrum", "Kanban", "product backlog", "coaching"]
            ),
            ats_keywords=ATSKeywords(
                methodologies=["Scrum", "Kanban"],
                soft_skills=["coaching"],
                domain=["product backlog"],
            ),
            company_context=CompanyContext(company_name="Target Ltd", sector="software"),
        ),
        expected_facts=ExpectedFacts(
            roles=[
                RoleFact(
                    role="Delivery Manager",
                    company="Example Ltd",
                    period="2020 - Present",
                    achievement_count=1,
                )
            ],
            education=[
                {
                    "qualification": "BSc Computing",
                    "institution": "Example University",
                    "year": "2010",
                }
            ],
            certifications=["PSM I"],
            allowed_numeric_tokens=["2020", "2010"],
        ),
        models=[
            ModelSpec(
                id="local",
                runtime="ollama",
                model="local",
                endpoint="http://127.0.0.1:11434",
                context_size=16384,
            )
        ],
        seeds=[11, 23, 41],
        cv_length_tolerance=0.1,
        input_hashes={},
    )


@pytest.fixture
def valid_cv(benchmark_case: BenchmarkCase) -> TailoredCVResult:
    master = benchmark_case.master_cv
    return TailoredCVResult(
        summary=master["summary_variants"]["delivery"],
        skills=[
            {
                "category": "Delivery & Leadership",
                "items": ["Scrum", "Kanban", "Product backlog", "Coaching"],
            }
        ],
        experience=[
            TailoredExperience(
                role="Delivery Manager",
                company="Example Ltd",
                period="2020 - Present",
                achievements=[master["experience"][0]["achievements"][0]["text"]],
            )
        ],
        education=[
            TailoredEducation(
                qualification="BSc Computing",
                institution="Example University",
                year="2010",
            )
        ],
        certifications=["PSM I"],
        ats_keywords_embedded=["Scrum", "Kanban", "product backlog", "coaching"],
    )


@pytest.fixture
def valid_cover_letter() -> CoverLetterResult:
    sentence = (
        "I offer grounded Delivery Manager experience using Scrum and Kanban to coach teams, "
        "manage the product backlog, and lead hybrid delivery for Example Ltd."
    )
    paragraphs = [" ".join([sentence] * 3) for _ in range(4)]
    body_words = len(" ".join(paragraphs).split())
    assert 250 <= body_words <= 350
    return CoverLetterResult(
        subject_line="Application: Delivery Manager - Target Ltd",
        greeting="Dear Hiring Manager,",
        body_paragraphs=paragraphs,
        sign_off="Kind regards,",
        word_count=body_words,
        key_keywords_used=["Scrum", "Kanban", "product backlog", "coaching"],
    )


def test_valid_pair_is_eligible_and_uses_60_40_weighting(
    benchmark_case: BenchmarkCase,
    valid_cv: TailoredCVResult,
    valid_cover_letter: CoverLetterResult,
) -> None:
    result = score_pair(benchmark_case, valid_cv, valid_cover_letter)

    assert result.eligible
    assert result.cv is not None
    assert result.cover_letter is not None
    assert result.combined == pytest.approx(
        result.cv.total * 0.6 + result.cover_letter.total * 0.4,
        abs=0.01,
    )
    assert set(result.cv.dimensions) == {
        "grounding",
        "jd_coverage",
        "structure",
        "evidence_relevance",
        "readability",
    }
    assert {name: item.weight for name, item in result.cv.dimensions.items()} == {
        "grounding": 0.30,
        "jd_coverage": 0.25,
        "structure": 0.20,
        "evidence_relevance": 0.15,
        "readability": 0.10,
    }
    assert {
        name: item.weight for name, item in result.cover_letter.dimensions.items()
    } == {
        "grounding": 0.35,
        "jd_coverage": 0.25,
        "structure": 0.15,
        "evidence_relevance": 0.15,
        "readability": 0.10,
    }


def test_unsupported_metric_is_a_blocking_gate(
    benchmark_case: BenchmarkCase,
    valid_cv: TailoredCVResult,
    valid_cover_letter: CoverLetterResult,
) -> None:
    valid_cover_letter.body_paragraphs[1] += " I improved throughput by 97%."

    result = score_pair(benchmark_case, valid_cv, valid_cover_letter)

    assert not result.eligible
    assert any(f.code == "unsupported_numeric_token" for f in result.gates)


def test_missing_role_is_a_blocking_gate(
    benchmark_case: BenchmarkCase,
    valid_cv: TailoredCVResult,
    valid_cover_letter: CoverLetterResult,
) -> None:
    valid_cv.experience.clear()

    result = score_pair(benchmark_case, valid_cv, valid_cover_letter)

    assert not result.eligible
    assert any(f.code == "role_structure_mismatch" for f in result.gates)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("placeholder", "prohibited_placeholder"),
        ("latex", "prohibited_latex"),
        ("certification", "certification_mismatch"),
        ("education", "education_mismatch"),
        ("bullet", "achievement_count_mismatch"),
    ],
)
def test_protected_content_gates(
    mutation: str,
    expected_code: str,
    benchmark_case: BenchmarkCase,
    valid_cv: TailoredCVResult,
    valid_cover_letter: CoverLetterResult,
) -> None:
    cv = deepcopy(valid_cv)
    letter = deepcopy(valid_cover_letter)
    if mutation == "placeholder":
        letter.body_paragraphs[0] += " [Company Name]"
    elif mutation == "latex":
        cv.summary += r" \textsterling 500"
    elif mutation == "certification":
        cv.certifications = ["Invented Certification"]
    elif mutation == "education":
        cv.education[0].institution = "Invented University"
    elif mutation == "bullet":
        cv.experience[0].achievements.append("Added achievement")

    result = score_pair(benchmark_case, cv, letter)

    assert not result.eligible
    assert any(f.code == expected_code for f in result.gates)


def test_cover_letter_uses_actual_word_count_for_gate(
    benchmark_case: BenchmarkCase,
    valid_cv: TailoredCVResult,
    valid_cover_letter: CoverLetterResult,
) -> None:
    valid_cover_letter.body_paragraphs = ["Too short."]
    valid_cover_letter.word_count = 300

    result = score_pair(benchmark_case, valid_cv, valid_cover_letter)

    assert not result.eligible
    assert any(f.code == "cover_letter_word_count" for f in result.gates)


def test_unsupported_jd_gap_is_not_counted_against_coverage(
    benchmark_case: BenchmarkCase,
    valid_cv: TailoredCVResult,
    valid_cover_letter: CoverLetterResult,
) -> None:
    benchmark_case.jd_analysis.ats_keywords.technical.append("COBOL")

    result = score_pair(benchmark_case, valid_cv, valid_cover_letter)

    assert result.eligible
    assert result.cv is not None
    assert result.cv.dimensions["jd_coverage"].score == 100
