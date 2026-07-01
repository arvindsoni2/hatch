"""Build a safe read-only profile/master-CV summary with source warnings."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..services.master_cv_store import load_master_cv, resolve_master_cv_path
from ..services.profile_service import load_profile


def _normalised(values: list[str]) -> set[str]:
    return {value.strip().casefold() for value in values if value.strip()}


def _master_skills(master: dict[str, Any]) -> list[str]:
    output: list[str] = []
    groups = master.get("skills", [])
    iterable = groups.values() if isinstance(groups, dict) else groups
    for group in iterable:
        if isinstance(group, dict):
            output.extend(str(item) for item in group.get("items", []) if item)
    return list(dict.fromkeys(output))


def build_profile_summary() -> dict[str, Any]:
    warnings: list[dict[str, str]] = []
    try:
        profile = load_profile()
    except Exception:
        return {
            "identity": {"name": "", "title": ""},
            "target_roles": [],
            "skills": [],
            "unverified_skills": [],
            "domains": [],
            "certifications": [],
            "education": [],
            "proof_points": [],
            "master_cv": {"status": "invalid", "path": "", "last_validated_at": None, "last_updated_at": None},
            "warnings": [{"code": "profile_yaml_invalid", "message": "Profile YAML is invalid."}],
        }

    cv_path = resolve_master_cv_path()
    try:
        master = load_master_cv()
        cv_status = "present"
    except Exception:
        master = {}
        cv_status = "missing"
        warnings.append({"code": "master_cv_missing", "message": "No confirmed master CV found."})

    personal = master.get("personal", {}) if isinstance(master.get("personal"), dict) else {}
    identity = {
        "name": profile.candidate.name or personal.get("full_name", ""),
        "title": profile.candidate.title or personal.get("title", ""),
        "email": profile.candidate.email or personal.get("email", ""),
        "phone": profile.candidate.phone or personal.get("phone", ""),
    }
    profile_identity = [profile.candidate.name, profile.candidate.email, profile.candidate.phone]
    master_identity = [personal.get("full_name", ""), personal.get("email", ""), personal.get("phone", "")]
    if any(profile_identity) and any(master_identity) and _normalised(profile_identity) != _normalised(master_identity):
        warnings.append({"code": "identity_mismatch", "message": "Profile identity/contact details differ from master CV."})

    evidence_skills = _master_skills(master)
    declared = list(dict.fromkeys(profile.skills.primary + profile.skills.secondary))
    unverified = [skill for skill in declared if skill.casefold() not in _normalised(evidence_skills)]
    skills = list(dict.fromkeys(evidence_skills + declared))

    master_education = master.get("education", []) if isinstance(master.get("education"), list) else []
    master_certs = [str(item) for item in master.get("certifications", []) if item]
    certifications = master_certs or profile.skills.certifications
    if master_certs and profile.skills.certifications and _normalised(master_certs) != _normalised(profile.skills.certifications):
        warnings.append({"code": "certifications_mismatch", "message": "Certifications differ between profile and master CV."})

    if not profile.search.target_roles:
        warnings.append({"code": "target_roles_missing", "message": "No target roles configured."})
    if not profile.proof_points:
        warnings.append({"code": "proof_points_missing", "message": "No proof points configured."})
    if not skills:
        warnings.append({"code": "skills_missing", "message": "No skills configured."})
    if not master_education:
        warnings.append({"code": "education_missing", "message": "Education is missing or incomplete."})
    if not certifications:
        warnings.append({"code": "certifications_missing", "message": "No certifications configured."})

    meta_path = cv_path.with_suffix(".meta.json")
    meta: dict[str, Any] = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            pass
    updated = datetime.fromtimestamp(cv_path.stat().st_mtime).isoformat() if cv_path.exists() else None
    return {
        "identity": identity,
        "target_roles": profile.search.target_roles,
        "skills": skills,
        "unverified_skills": unverified,
        "domains": profile.domains.preferred,
        "certifications": certifications,
        "education": master_education,
        "proof_points": [point.model_dump() for point in profile.proof_points],
        "master_cv": {
            "status": cv_status,
            "path": str(Path(profile.master_cv_path)),
            "last_validated_at": meta.get("uploaded_at"),
            "last_updated_at": updated,
        },
        "warnings": warnings,
    }
