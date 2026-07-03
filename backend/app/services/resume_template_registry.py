"""Canonical ATS-safe resume templates and backward-compatible aliases."""
from __future__ import annotations

from typing import Any

_BASE = {
    "layout": "single_column",
    "ats_safety_notes": [
        "Single-column core content",
        "No icons, images, floating text boxes, or essential header content",
    ],
}


def _template(
    template_id: str, name: str, description: str, best_for: list[str],
    density: str, page: str, order: str, accent: str, margin: int, size: int,
) -> dict[str, Any]:
    return {
        **_BASE, "id": template_id, "name": name, "description": description,
        "best_for": best_for, "content_density": density,
        "default_page_target": page, "default_section_order": order,
        "style": {"accent": accent, "margin": margin, "font_size": size},
    }


TEMPLATES: tuple[dict[str, Any], ...] = (
    _template("ats_classic", "ATS Classic", "Conservative, highly compatible layout.",
              ["Online ATS forms", "Conservative employers"], "standard", "auto", "standard", "1F4E79", 1080, 20),
    _template("modern_compact", "Modern Compact", "Concise modern layout.",
              ["Modern roles", "Concise applications"], "compact", "one_page", "compact", "365F5B", 720, 18),
    _template("executive_uk_2_page", "Executive UK 2-page", "Senior UK and European leadership layout.",
              ["Senior professionals", "Leadership roles"], "detailed", "two_page", "leadership_first", "17365D", 900, 20),
    _template("consulting_clean", "Consulting Clean", "Clean client-facing delivery layout.",
              ["Consulting", "Advisory"], "standard", "two_page", "project_led", "334155", 900, 20),
    _template("project_delivery", "Project Delivery", "Outcomes-led project and transformation layout.",
              ["Project management", "Transformation"], "detailed", "two_page", "project_led", "0F766E", 900, 20),
    _template("contractor_freelance", "Contractor/Freelance", "Contract-focused outcomes layout.",
              ["Contract roles", "Freelance"], "standard", "two_page", "project_led", "374151", 900, 20),
    _template("tech_product", "Tech/Product", "Skills-forward technical and product layout.",
              ["Technology", "Product"], "standard", "auto", "skills_first", "4338CA", 900, 20),
    _template("career_switcher", "Career Switcher", "Transferable-evidence layout with full chronology.",
              ["Adjacent role moves", "Cross-domain applications"], "transferable", "auto", "career_switcher", "365F5B", 900, 19),
    _template("senior_leadership", "Senior Leadership", "Leadership-first programme layout.",
              ["Head-of roles", "Programme leadership"], "detailed", "two_page", "leadership_first", "1E3A5F", 900, 20),
    _template("minimal_one_page", "Minimal One-page", "Minimal recruiter-scan layout.",
              ["Startups", "Short applications"], "compact", "one_page", "compact", "263238", 720, 18),
)

ALIASES = {
    "professional_2_page": "executive_uk_2_page",
    "compact_one_page": "modern_compact",
}
_BY_ID = {template["id"]: template for template in TEMPLATES}


def resolve_template(template_id: str | None) -> tuple[dict[str, Any], str | None]:
    requested = template_id or "ats_classic"
    canonical = ALIASES.get(requested, requested)
    if canonical in _BY_ID:
        warning = f"Legacy template '{requested}' resolved to '{canonical}'." if requested in ALIASES else None
        return _BY_ID[canonical], warning
    return _BY_ID["ats_classic"], f"Unknown template '{requested}'; used ATS Classic."


def require_template(template_id: str) -> dict[str, Any]:
    canonical = ALIASES.get(template_id, template_id)
    if canonical not in _BY_ID:
        raise ValueError(f"Unknown template '{template_id}'")
    return _BY_ID[canonical]


def template_payload(default_design_settings: dict[str, Any] | None = None) -> dict[str, Any]:
    from .resume_design_settings import controls_payload, repair_design_settings
    defaults, warnings = repair_design_settings(default_design_settings or {})
    return {
        "templates": [{k: v for k, v in item.items() if k != "style"} for item in TEMPLATES],
        "default_template_id": defaults.template_id,
        "default_design_settings": defaults.model_dump(),
        "controls": controls_payload(),
        "warnings": warnings,
    }
