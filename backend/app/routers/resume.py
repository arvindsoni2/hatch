"""FastAPI router for master CV upload and management."""
from __future__ import annotations

import json
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from ..agents.tools.profile_loader import load_profile

router = APIRouter(prefix="/api/resume", tags=["resume"])


def _data_dir() -> Path:
    profile = load_profile()
    cv_path = Path(getattr(profile, "master_cv_path", "./data/master_cv.json"))
    if not cv_path.is_absolute():
        cv_path = Path("/app") / cv_path.relative_to(".")
    return cv_path.parent


def _cv_path() -> Path:
    profile = load_profile()
    cv_path = Path(getattr(profile, "master_cv_path", "./data/master_cv.json"))
    if not cv_path.is_absolute():
        cv_path = Path("/app") / cv_path.relative_to(".")
    return cv_path


def _meta_path() -> Path:
    return _cv_path().with_suffix(".meta.json")


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _extract_text_from_docx(path: str) -> str:
    from docx import Document  # type: ignore
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _extract_text_from_pdf(path: str) -> str:
    from pypdf import PdfReader  # type: ignore
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


_SECTION_ALIASES: dict[str, str] = {
    "professional experience": "experience",
    "work experience": "experience",
    "employment history": "experience",
    "employment": "experience",
    "technical skills and tools": "skills",
    "technical skills": "skills",
    "skills and tools": "skills",
    "key skills": "skills",
    "core competencies": "skills",
    "competencies": "skills",
    "awards & certifications": "certifications",
    "awards and certifications": "certifications",
    "certifications and awards": "certifications",
    "qualifications": "certifications",
    "professional summary": "summary",
    "career summary": "summary",
    "executive summary": "summary",
    "personal profile": "profile",
    "contact information": "contact",
    "contact details": "contact",
}

_SECTION_RE = re.compile(
    r"^(professional experience|work experience|employment history|employment|"
    r"technical skills and tools|technical skills|skills and tools|key skills|"
    r"core competencies|competencies|skills?|"
    r"awards? & certifications?|awards? and certifications?|certifications?|"
    r"professional summary|career summary|executive summary|summary|"
    r"profile|personal profile|objective|"
    r"education|qualifications|"
    r"projects?|achievements?|publications?|references?|"
    r"contact(?: information| details)?|personal|languages?)[\s:]*$",
    re.IGNORECASE,
)


def _normalize_heading(heading: str) -> str:
    key = heading.lower().rstrip(":").strip()
    return _SECTION_ALIASES.get(key, key)


def _parse_sections(text: str) -> dict[str, Any]:
    """Heuristic section splitter — groups lines under detected headings."""
    sections: dict[str, list[str]] = {}
    current = "header"
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _SECTION_RE.match(stripped):
            current = _normalize_heading(stripped)
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(stripped)
    return {k: "\n".join(v) for k, v in sections.items() if v}


def _extract_skills(text: str) -> list[str]:
    skills_section = ""
    in_skills = False
    skill_heading = re.compile(
        r"^(technical skills.*|skills?(?: and tools)?|key skills|core competencies|competencies)[\s:]*$",
        re.IGNORECASE,
    )
    stop_heading = re.compile(
        r"^(experience|professional experience|education|employment|certifications?|awards?|"
        r"summary|profile|projects?|references?)[\s:]*$",
        re.IGNORECASE,
    )
    for line in text.splitlines():
        stripped = line.strip()
        if skill_heading.match(stripped):
            in_skills = True
            continue
        if in_skills:
            if stop_heading.match(stripped):
                break
            skills_section += " " + stripped

    raw_skills: list[str] = []
    if skills_section:
        # Split on commas, bullets, pipes, newlines — also split "Category: item1, item2"
        for chunk in re.split(r"[,|•·\n]+", skills_section):
            # Strip category labels like "Agile Delivery Tools:"
            chunk = re.sub(r"^[^:]{3,30}:\s*", "", chunk.strip())
            chunk = chunk.strip(" •·-()")
            if chunk:
                raw_skills.append(chunk)

    return [s for s in raw_skills if 1 < len(s) < 60][:60]


def _count_experience_items(sections: dict[str, Any]) -> int:
    # Look in experience, profile (fallback if parser lumped experience there), or full text
    exp_text = (
        sections.get("experience")
        or sections.get("professional experience")
        or sections.get("work experience")
        or sections.get("employment")
        or sections.get("profile")  # pypdf sometimes lumps experience into profile
        or ""
    )
    if not exp_text:
        return 0
    # Count distinct year ranges (e.g. "2022 – Present", "07/2011 – 05/2022")
    dates = re.findall(r"\b(19|20)\d{2}\b", str(exp_text))
    # Divide by 2 (start/end per role) as a rough role count, minimum from unique years
    return max(len(set(dates)) - 1, len(dates) // 2)


# ── Schemas ───────────────────────────────────────────────────────────────────

class ResumeStatus(BaseModel):
    exists: bool
    filename: str | None = None
    uploaded_at: str | None = None
    parsed: bool = False
    sections: dict[str, bool] = {}
    skills_count: int = 0
    experience_count: int = 0
    proof_points_count: int = 0


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/status", response_model=ResumeStatus)
async def get_resume_status() -> ResumeStatus:
    """Return status of the currently stored master CV."""
    cv_path = _cv_path()
    meta_path = _meta_path()

    if not cv_path.exists():
        return ResumeStatus(exists=False)

    meta: dict[str, Any] = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            pass

    try:
        cv_data = json.loads(cv_path.read_text())
    except Exception:
        return ResumeStatus(exists=True, parsed=False, filename=meta.get("filename"))

    profile = load_profile()
    proof_count = len(profile.proof_points)

    sections_present: dict[str, bool] = {
        "personal": bool(cv_data.get("personal") or cv_data.get("contact") or cv_data.get("header")),
        "summary": bool(cv_data.get("summary") or cv_data.get("summary_variants") or cv_data.get("profile")),
        "experience": bool(cv_data.get("experience") or cv_data.get("employment") or cv_data.get("work_history")),
        "skills": bool(cv_data.get("skills")),
        "education": bool(cv_data.get("education")),
        "certifications": bool(cv_data.get("certifications")),
    }

    skills_count = 0
    skills = cv_data.get("skills", {})
    if isinstance(skills, dict):
        for v in skills.values():
            items = v.get("items", []) if isinstance(v, dict) else []
            skills_count += len(items)
    elif isinstance(skills, list):
        skills_count = len(skills)

    return ResumeStatus(
        exists=True,
        filename=meta.get("filename"),
        uploaded_at=meta.get("uploaded_at"),
        parsed=True,
        sections=sections_present,
        skills_count=skills_count,
        experience_count=meta.get("experience_count", 0),
        proof_points_count=proof_count,
    )


@router.post("/upload", response_model=ResumeStatus)
async def upload_resume(file: UploadFile = File(...)) -> ResumeStatus:
    """Upload a .docx or .pdf CV. Parses into structured JSON and stores at data/master_cv.json."""
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in (".docx", ".pdf"):
        raise HTTPException(status_code=422, detail="Only .docx and .pdf files are supported.")

    _data_dir().mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        if suffix == ".docx":
            text = _extract_text_from_docx(tmp_path)
        else:
            text = _extract_text_from_pdf(tmp_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse document: {exc}") from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    sections = _parse_sections(text)
    skills = _extract_skills(text)
    exp_count = _count_experience_items(sections)

    cv_json: dict[str, Any] = {
        "_source": filename,
        "_parsed_at": datetime.utcnow().isoformat(),
        "_raw_sections": sections,
        # Promote normalised sections to top-level so status checks find them
        **{k: v for k, v in sections.items() if not k.startswith("_")},
    }
    if skills:
        cv_json["skills"] = {"extracted": {"display_name": "Skills", "items": skills}}

    cv_path = _cv_path()
    cv_path.write_text(json.dumps(cv_json, indent=2, ensure_ascii=False))

    meta = {
        "filename": filename,
        "uploaded_at": datetime.utcnow().isoformat(),
        "experience_count": exp_count,
    }
    _meta_path().write_text(json.dumps(meta))

    # Persist plain resume text for semantic scoring
    try:
        from ..services.resume_store import save_resume_text
        save_resume_text(text)
    except Exception as _exc:
        import logging as _logging
        _logging.getLogger(__name__).warning("Could not save resume text for scoring: %s", _exc)

    sections_present: dict[str, bool] = {
        "personal": bool(sections.get("header") or sections.get("contact") or sections.get("personal")),
        "summary": bool(sections.get("summary") or sections.get("profile")),
        "experience": bool(sections.get("experience") or sections.get("employment")),
        "skills": bool(skills or sections.get("skills")),
        "education": bool(sections.get("education")),
        "certifications": bool(sections.get("certifications")),
    }

    return ResumeStatus(
        exists=True,
        filename=filename,
        uploaded_at=meta["uploaded_at"],
        parsed=True,
        sections=sections_present,
        skills_count=len(skills),
        experience_count=exp_count,
        proof_points_count=len(load_profile().proof_points),
    )


@router.get("/json")
async def get_resume_json() -> dict[str, Any]:
    """Return the raw parsed master CV JSON."""
    cv_path = _cv_path()
    if not cv_path.exists():
        raise HTTPException(status_code=404, detail="No master CV found. Upload one at /api/resume/upload.")
    try:
        return json.loads(cv_path.read_text())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read CV: {exc}") from exc
