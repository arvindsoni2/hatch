"""Stable ATS-safe resume template definitions and density rules."""
from __future__ import annotations

from typing import Any

TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "id": "ats_classic",
        "name": "ATS Classic",
        "description": "Conservative single-column layout optimised for reliable ATS parsing.",
        "best_for": ["Online ATS forms", "Conservative employers"],
        "layout": "single_column",
        "content_density": "standard",
        "style": {"accent": "1F4E79", "margin": 1080, "font_size": 20},
    },
    {
        "id": "professional_2_page",
        "name": "Professional 2-page",
        "description": "Detailed ATS-safe layout for experienced UK and European professionals.",
        "best_for": ["Experienced professionals", "Complex delivery histories"],
        "layout": "single_column",
        "content_density": "detailed",
        "style": {"accent": "17365D", "margin": 900, "font_size": 20},
    },
    {
        "id": "compact_one_page",
        "name": "Compact One-page",
        "description": "Denser, selective layout that retains complete employment chronology.",
        "best_for": ["Startups", "Quick applications"],
        "layout": "compact_single_column",
        "content_density": "compact",
        "style": {"accent": "263238", "margin": 720, "font_size": 18},
    },
    {
        "id": "career_switcher",
        "name": "Career Switcher",
        "description": "Skills-first layout highlighting grounded transferable experience.",
        "best_for": ["Adjacent role moves", "Cross-domain applications"],
        "layout": "skills_first",
        "content_density": "transferable",
        "style": {"accent": "365F5B", "margin": 900, "font_size": 19},
    },
)

_BY_ID = {template["id"]: template for template in TEMPLATES}


def resolve_template(template_id: str | None) -> tuple[dict[str, Any], str | None]:
    requested = template_id or "ats_classic"
    if requested in _BY_ID:
        return _BY_ID[requested], None
    return _BY_ID["ats_classic"], f"Unknown template '{requested}'; used ATS Classic."


def template_payload(default_template_id: str | None = None) -> dict[str, Any]:
    default, warning = resolve_template(default_template_id)
    return {
        "templates": [
            {key: value for key, value in item.items() if key != "style"}
            for item in TEMPLATES
        ],
        "default_template_id": default["id"],
        "warning": warning,
    }
