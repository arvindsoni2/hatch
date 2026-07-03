from app.services.cv_quality_gate import pre_generation_quality
from app.schemas.tailor import JDAnalysisResult, ATSKeywords, Requirements


def test_precheck_identifies_missing_required_evidence():
    analysis = JDAnalysisResult(
        role_title="Engineer", requirements=Requirements(must_have=["Python"]),
        ats_keywords=ATSKeywords(technical=["Python", "Docker"]),
    )
    result = pre_generation_quality(analysis, {"skills": ["Docker"]}, "ats_classic")
    assert result["status"] == "advisory"
    assert result["keyword_gaps"] == ["Python"]
    assert result["weak_requirements"][0]["severity"] == "high"
