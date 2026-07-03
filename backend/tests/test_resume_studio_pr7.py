from app.schemas.tailor import JDAnalysisResult
from app.services.resume_design_settings import ResumeDesignSettings, repair_design_settings
from app.services.resume_template_recommender import recommend_templates
from app.services.resume_template_registry import TEMPLATES, resolve_template, template_payload


def test_registry_has_ten_public_templates_and_hidden_aliases():
    payload = template_payload()
    assert len(TEMPLATES) == len(payload["templates"]) == 10
    assert "professional_2_page" not in {item["id"] for item in payload["templates"]}
    assert resolve_template("professional_2_page")[0]["id"] == "executive_uk_2_page"
    assert resolve_template("compact_one_page")[0]["id"] == "modern_compact"


def test_design_settings_validate_and_persisted_values_repair():
    assert ResumeDesignSettings(template_id="tech_product").template_id == "tech_product"
    settings, warnings = repair_design_settings({"font_family": "comic_sans"})
    assert settings.font_family == "aptos"
    assert warnings


def test_recommendations_are_deterministic():
    analysis = JDAnalysisResult(role_title="Senior Technical Programme Delivery Lead", seniority_level="senior")
    first = recommend_templates(analysis, {}, {"experience": [1, 2, 3, 4, 5, 6]})
    assert first == recommend_templates(analysis, {}, {"experience": [1, 2, 3, 4, 5, 6]})
    assert 1 <= len(first["recommendations"]) <= 2
