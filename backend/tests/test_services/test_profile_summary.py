from pathlib import Path
from unittest.mock import patch

from app.schemas.profile import Profile
from app.services.profile_summary import build_profile_summary


def test_profile_summary_uses_profile_identity_and_master_facts(tmp_path: Path) -> None:
    cv_path = tmp_path / "master_cv.json"
    cv_path.write_text("{}")
    profile = Profile.model_validate({
        "candidate": {"name": "Curated Name", "title": "Programme Manager"},
        "search": {"target_roles": ["Programme Director"]},
        "skills": {"primary": ["Agile", "Unverified Skill"], "certifications": ["Old Cert"]},
        "domains": {"preferred": ["Energy"]},
        "proof_points": [{"id": "p1", "summary": "Delivered transformation"}],
    })
    master = {
        "personal": {"full_name": "Parsed Name"},
        "skills": [{"category": "Delivery", "items": ["Agile"]}],
        "education": [{"qualification": "BEng"}],
        "certifications": ["PMP"],
    }
    with (
        patch("app.services.profile_summary.load_profile", return_value=profile),
        patch("app.services.profile_summary.load_master_cv", return_value=master),
        patch("app.services.profile_summary.resolve_master_cv_path", return_value=cv_path),
    ):
        result = build_profile_summary()

    assert result["identity"]["name"] == "Curated Name"
    assert result["education"] == [{"qualification": "BEng"}]
    assert result["certifications"] == ["PMP"]
    assert result["unverified_skills"] == ["Unverified Skill"]
    assert {item["code"] for item in result["warnings"]} >= {
        "identity_mismatch",
        "certifications_mismatch",
    }
