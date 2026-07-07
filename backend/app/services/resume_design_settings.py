"""Validation and persistence-compatible resolution for resume design controls."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel

from .resume_template_registry import ALIASES, require_template


class ResumeDesignSettings(BaseModel):
    template_id: str = "ats_classic"
    page_target: Literal["one_page", "two_page", "auto"] = "two_page"
    density: Literal["compact", "standard", "detailed", "transferable"] = "standard"
    section_order_preset: Literal["standard", "skills_first", "project_led", "leadership_first", "compact", "career_switcher"] = "standard"
    accent_color: Literal["navy", "slate", "teal", "indigo", "emerald", "charcoal"] = "navy"
    font_family: Literal["aptos", "calibri", "arial", "georgia"] = "aptos"

    def model_post_init(self, _context: Any) -> None:
        template = require_template(self.template_id)
        self.template_id = template["id"]


def controls_payload() -> dict[str, list[str]]:
    return {
        "page_targets": ["one_page", "two_page", "auto"],
        "densities": ["compact", "standard", "detailed", "transferable"],
        "section_order_presets": ["standard", "skills_first", "project_led", "leadership_first", "compact", "career_switcher"],
        "accent_colors": ["navy", "slate", "teal", "indigo", "emerald", "charcoal"],
        "font_families": ["aptos", "calibri", "arial", "georgia"],
    }


def repair_design_settings(value: dict[str, Any]) -> tuple[ResumeDesignSettings, list[str]]:
    warnings: list[str] = []
    clean = dict(value)
    if clean.get("template_id") in ALIASES:
        warnings.append(f"Legacy template '{clean['template_id']}' repaired.")
        clean["template_id"] = ALIASES[clean["template_id"]]
    try:
        return ResumeDesignSettings.model_validate(clean), warnings
    except Exception:
        warnings.append("Invalid persisted resume design settings repaired with safe defaults.")
        return ResumeDesignSettings(), warnings
