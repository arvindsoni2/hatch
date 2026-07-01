from app.services.docx_cv_builder import _build_cv_spec
from app.services.resume_template_registry import TEMPLATES, resolve_template, template_payload
from app.schemas.tailor import JDAnalysisResult, TailoredCVResult, TailoredExperience


def _cv() -> TailoredCVResult:
    return TailoredCVResult(
        summary=" ".join(f"word{i}" for i in range(100)),
        experience=[
            TailoredExperience(
                role=f"Role {index}",
                company=f"Company {index}",
                period="2020 – Present",
                achievements=[f"Achievement {n}" for n in range(6)],
            )
            for index in range(3)
        ],
    )


def test_registry_has_exactly_four_stable_templates() -> None:
    assert [item["id"] for item in TEMPLATES] == [
        "ats_classic",
        "professional_2_page",
        "compact_one_page",
        "career_switcher",
    ]
    assert len(template_payload()["templates"]) == 4


def test_unknown_template_falls_back_with_warning() -> None:
    template, warning = resolve_template("unknown")
    assert template["id"] == "ats_classic"
    assert warning


def test_compact_template_reduces_bullets_but_preserves_chronology() -> None:
    compact = _build_cv_spec(
        _cv(), JDAnalysisResult(role_title="Programme Manager"), {}, "compact_one_page"
    )
    detailed = _build_cv_spec(
        _cv(), JDAnalysisResult(role_title="Programme Manager"), {}, "professional_2_page"
    )
    assert len(compact["experience"]) == len(detailed["experience"]) == 3
    assert sum(len(item["achievements"]) for item in compact["experience"]) < sum(
        len(item["achievements"]) for item in detailed["experience"]
    )
    assert len(compact["summary"].split()) == 70
