from app.schemas.tailor import (
    ATSScoreResult,
    JDAnalysisResult,
    KeywordMatch,
    SkillMatchResult,
    TailoredCVResult,
)
from app.services.tailoring_review import build_review, latest_review, save_review


def _review() -> dict:
    return build_review(
        application_id="app-1",
        analysis=JDAnalysisResult(role_title="Programme Manager"),
        skill_match=SkillMatchResult(matched=["Agile"], missing=["Python"], match_pct=50),
        ats=ATSScoreResult(
            overall_score=80,
            keyword_matches=[
                KeywordMatch(keyword="Agile", found=True),
                KeywordMatch(keyword="Python", found=False),
            ],
        ),
        tailored=TailoredCVResult(summary="Grounded", tailoring_notes="Prioritised delivery evidence."),
        cv_document_id="cv-1",
        cl_document_id="cl-1",
        template_id="ats_classic",
        variant="A",
    )


def test_review_separates_evidence_from_unsupported_requirements() -> None:
    review = _review()
    assert review["evidence_used"][0]["requirement"] == "Agile"
    assert review["weak_or_unsupported_requirements"][0]["requirement"] == "Python"
    assert review["ats_keyword_coverage"]["coverage_pct"] == 50


async def test_review_persists_across_queries(db_session) -> None:
    # Foreign keys require backing application/documents in production; SQLite
    # test engine does not enforce them, allowing the persistence contract alone.
    review = _review()
    await save_review(db_session, review)
    await db_session.commit()
    assert await latest_review(db_session, "app-1") == review
